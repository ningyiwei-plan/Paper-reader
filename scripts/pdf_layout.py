"""Inspect a PDF or crop its original figures, tables, and equations."""

import argparse
import json
from pathlib import Path


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
    for job in jobs:
        number, name = job["page"], job["file"]
        if type(number) is not int or not 1 <= number <= len(pdf.pages):
            raise ValueError(f"Invalid page number: {number}")
        suffix = Path(name).suffix.lower()
        if Path(name).name != name or suffix not in {".png", ".webp"}:
            raise ValueError(f"Expected a PNG or WebP filename: {name}")
        page = pdf.pages[number - 1]
        box = checked_box(job["box"], page)
        image = page.crop(box).to_image(resolution=dpi, antialias=True).original
        if suffix == ".webp":
            image.save(directory / name, lossless=True, method=3)
        else:
            image.save(directory / name, optimize=True)
        page.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name, dpi in (("inspect", 108), ("crop", 360)):
        command = sub.add_parser(name)
        command.add_argument("pdf", type=Path)
        if name == "crop":
            command.add_argument("manifest", type=Path)
        command.add_argument("directory", type=Path)
        command.add_argument("--dpi", type=int, default=dpi)
    args = parser.parse_args()
    if not 72 <= args.dpi <= 600:
        parser.error("--dpi must be between 72 and 600")
    try:
        import pdfplumber
    except ImportError:
        parser.exit(2, "PDF layout requires pdfplumber. Use the bundled Python or install pdfplumber.\n")
    with pdfplumber.open(args.pdf) as pdf:
        if args.command == "inspect":
            inspect(pdf, args.directory, args.dpi)
        else:
            crop(pdf, args.manifest, args.directory, args.dpi)


if __name__ == "__main__":
    main()
