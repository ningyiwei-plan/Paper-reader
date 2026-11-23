"""Inspect a PDF or crop its original figures, tables, and equations."""

import argparse
from collections import defaultdict
from contextlib import ExitStack
import hashlib
from math import ceil, floor, isfinite
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import perf_counter

from draft_translation import read_json, write_json


def pdf_digest(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def checked_box(value, width, height, number):
    if len(value) != 4 or not all(type(point) in (int, float) and isfinite(point) for point in value):
        raise ValueError("A box needs four coordinates: x0, top, x1, bottom")
    x0, top, x1, bottom = value
    if not (0 <= x0 < min(x1, width) and x1 <= width + 0.1
            and 0 <= top < min(bottom, height) and bottom <= height + 0.1):
        raise ValueError(f"Box {value} is outside page {number}")
    return x0, top, min(x1, width), min(bottom, height)


def inspect(pdf, directory, dpi):
    directory.mkdir(parents=True, exist_ok=True)
    pages = []
    for page in pdf.pages:
        lines = page.extract_text_lines(x_tolerance=1, return_chars=False)
        pages.append({
            "page": page.page_number,
            "width": page.width,
            "height": page.height,
            "lines": lines,
            "raster_images": [
                [img[key] for key in ("x0", "top", "x1", "bottom")]
                for img in page.images
            ],
        })
        page.to_image(resolution=dpi, antialias=True).original.save(directory / f"page-{page.page_number:03}.png")
        page.close()
    write_json(directory / "layout.json", pages)


def save_crop(image, path):
    with NamedTemporaryFile(dir=path.parent, suffix=path.suffix, delete=False) as stream:
        temporary = Path(stream.name)
    try:
        if path.suffix.lower() == ".webp":
            image.save(temporary, format="WEBP", lossless=True, method=3)
        else:
            image.save(temporary, format="PNG", optimize=True)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def crop(pdf_path, jobs, directory, dpi, digest=None):
    started = perf_counter()
    directory.mkdir(parents=True, exist_ok=True)
    state = directory / ".crop-cache.json"
    cache_key = {"version": 1, "pdf": digest or pdf_digest(pdf_path), "dpi": dpi}
    cached = {}
    if state.exists():
        try:
            cache = read_json(state)
            if cache.get("key") == cache_key:
                cached = cache["crops"]
        except (AttributeError, KeyError, OSError, ValueError):
            pass
    pages = defaultdict(list)
    reused = {}
    seen = set()
    for job in jobs:
        number, name = job["page"], job["file"]
        if type(number) is not int or number < 1:
            raise ValueError(f"Invalid page number: {number}")
        suffix = Path(name).suffix.lower()
        if Path(name).name != name or suffix not in {".png", ".webp"} or name.casefold() in seen:
            raise ValueError(f"Expected a PNG or WebP filename: {name}")
        seen.add(name.casefold())
        path = directory / name
        previous = cached.get(name, {})
        if (previous.get("page") == number and previous.get("box") == job["box"]
                and path.is_file() and path.stat().st_size == previous.get("bytes")):
            reused[name] = previous
        else:
            pages[number].append(job)
    results = dict(reused)
    if pages:
        import pypdfium2 as pdfium

        with ExitStack() as stack:
            pdf = stack.enter_context(pdfium.PdfDocument(pdf_path))
            legacy = None
            for number, items in pages.items():
                if number > len(pdf):
                    raise ValueError(f"Invalid page number: {number}")
                page = pdf[number - 1]
                width, height = page.get_size()
                origin = (0, 0, width, height)
                if page.get_mediabox() != origin or page.get_cropbox() != origin:
                    if legacy is None:
                        import pdfplumber
                        legacy = stack.enter_context(pdfplumber.open(pdf_path))
                    source = legacy.pages[number - 1]
                    for job in items:
                        box = checked_box(job["box"], source.width, source.height, number)
                        image = source.crop(box).to_image(resolution=dpi, antialias=True).original
                        save_crop(image, directory / job["file"])
                    source.close()
                else:
                    scale = dpi / 72
                    bitmap = page.render(scale=scale)
                    try:
                        image = bitmap.to_pil()
                        for job in items:
                            x0, y0, x1, y1 = checked_box(job["box"], width, height, number)
                            bounds = (floor(x0 * scale), floor(y0 * scale), ceil(x1 * scale), ceil(y1 * scale))
                            save_crop(image.crop(bounds), directory / job["file"])
                    finally:
                        bitmap.close()
                page.close()
                for job in items:
                    name = job["file"]
                    results[name] = {"page": number, "box": job["box"], "bytes": (directory / name).stat().st_size}
        write_json(state, {"key": cache_key, "crops": results})
    print(f"Crops: {len(results) - len(reused)} rendered, {len(reused)} reused at {dpi} DPI "
          f"({perf_counter() - started:.2f}s).")


def contact(pdf, directory, numbers, dpi):
    from PIL import Image, ImageDraw

    if not numbers or any(number < 1 or number > len(pdf) for number in numbers):
        raise ValueError("Select valid PDF page numbers.")
    directory.mkdir(parents=True, exist_ok=True)
    for offset in range(0, len(numbers), 6):
        selected = numbers[offset:offset + 6]
        frames = []
        for number in selected:
            page = pdf[number - 1]
            bitmap = page.render(scale=dpi / 72)
            try:
                frames.append(bitmap.to_pil().convert("RGB"))
            finally:
                bitmap.close()
            page.close()
        width = max(frame.width for frame in frames) + 12
        height = max(frame.height for frame in frames) + 31
        columns = min(3, len(frames))
        sheet = Image.new("RGB", (width * columns, height * ((len(frames) + 2) // 3)), "#e4e8ed")
        draw = ImageDraw.Draw(sheet)
        for i, (number, frame) in enumerate(zip(selected, frames)):
            x, y = i % 3 * width + 6, i // 3 * height
            sheet.paste(frame, (x, y + 23))
            draw.text((x, y + 5), f"PDF page {number}", fill="#172844")
        target = directory / f"contact-{offset // 6 + 1:02}.jpg"
        sheet.save(target, quality=86)
        print(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name, dpi in (("inspect", 108), ("crop", 360), ("contact", 72)):
        command = sub.add_parser(name)
        command.add_argument("pdf", type=Path)
        if name == "crop":
            command.add_argument("manifest", type=Path)
        if name == "contact":
            command.add_argument("--pages", required=True, help="Comma-separated PDF page numbers")
        command.add_argument("directory", type=Path)
        command.add_argument("--dpi", type=int, default=dpi)
    args = parser.parse_args()
    if not 72 <= args.dpi <= 600:
        parser.error("--dpi must be between 72 and 600")
    try:
        if args.command == "inspect":
            import pdfplumber
            with pdfplumber.open(args.pdf) as pdf:
                inspect(pdf, args.directory, args.dpi)
        elif args.command == "contact":
            import pypdfium2 as pdfium
            with pdfium.PdfDocument(args.pdf) as pdf:
                numbers = list(dict.fromkeys(int(value) for value in args.pages.split(",")))
                contact(pdf, args.directory, numbers, args.dpi)
        else:
            crop(args.pdf, read_json(args.manifest), args.directory, args.dpi)
    except (ImportError, OSError, ValueError, KeyError) as error:
        parser.exit(2, f"{error}\n")


if __name__ == "__main__":
    main()
