"""Inspect a PDF or crop its original figures, tables, and equations."""

import argparse
import json
from pathlib import Path
from collections import defaultdict
from math import ceil, floor


def checked_box(value, page):
    if len(value) != 4:
        raise ValueError("A box needs four coordinates: x0, top, x1, bottom")
    x0, top, x1, bottom = value
    if not (0 <= x0 < x1 <= page.width + 0.1 and 0 <= top < bottom <= page.height + 0.1):
        raise ValueError(f"Box {value} is outside page {page.page_number}")
    return value


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
    (directory / "layout.json").write_text(
        json.dumps(pages, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def crop(pdf, manifest, directory, dpi):
    jobs = json.loads(manifest.read_text(encoding="utf-8-sig"))
    directory.mkdir(parents=True, exist_ok=True)
    pages = defaultdict(list)
    filenames = set()
    for job in jobs:
        number, name = job["page"], job["file"]
        if type(number) is not int or not 1 <= number <= len(pdf.pages):
            raise ValueError(f"Invalid page number: {number}")
        suffix = Path(name).suffix.lower()
        if Path(name).name != name or suffix not in {".png", ".webp"} or name in filenames:
            raise ValueError(f"Expected a PNG or WebP filename: {name}")
        filenames.add(name)
        pages[number].append((name, checked_box(job["box"], pdf.pages[number - 1])))
    for number, items in pages.items():
        page = pdf.pages[number - 1]
        rendered = page.to_image(resolution=dpi, antialias=True) if page.bbox == page.cropbox else None
        for name, box in items:
            # Pdfplumber renders the full page even when given a cropped page.
            # Keep the render once per page and round the crop outwards.
            x0, y0, x1, y1 = box
            if rendered:
                left, top, _, _ = rendered.bbox
                scale = rendered.scale
                image = rendered.original.crop((floor((x0 - left) * scale), floor((y0 - top) * scale),
                                                ceil((x1 - left) * scale), ceil((y1 - top) * scale)))
            else:
                image = page.crop(box).to_image(resolution=dpi, antialias=True).original
            if Path(name).suffix.lower() == ".webp":
                image.save(directory / name, lossless=True, method=3)
            else:
                image.save(directory / name, optimize=True)
        page.close()


def contact(pdf, directory, numbers, dpi):
    from PIL import Image, ImageDraw

    if not numbers or any(number < 1 or number > len(pdf.pages) for number in numbers):
        raise ValueError("Select valid PDF page numbers.")
    directory.mkdir(parents=True, exist_ok=True)
    for offset in range(0, len(numbers), 6):
        selected = numbers[offset:offset + 6]
        frames = []
        for number in selected:
            page = pdf.pages[number - 1]
            rendered = page.to_image(resolution=dpi, antialias=True)
            frames.append(rendered.original.convert("RGB"))
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
        import pdfplumber
    except ImportError:
        parser.exit(2, "PDF layout requires pdfplumber. Use the bundled Python or install pdfplumber.\n")
    try:
        with pdfplumber.open(args.pdf) as pdf:
            if args.command == "inspect":
                inspect(pdf, args.directory, args.dpi)
            elif args.command == "contact":
                numbers = list(dict.fromkeys(int(value) for value in args.pages.split(",")))
                contact(pdf, args.directory, numbers, args.dpi)
            else:
                crop(pdf, args.manifest, args.directory, args.dpi)
                print(f"Cropped {len(json.loads(args.manifest.read_text(encoding='utf-8-sig')))} assets at {args.dpi} DPI.")
    except (OSError, ValueError, KeyError) as error:
        parser.exit(2, f"{error}\n")


if __name__ == "__main__":
    main()
