"""Extract a compact layout plan and assemble an untranslated reader manuscript."""

import argparse
from collections import Counter, defaultdict
from pathlib import Path
import re
from time import perf_counter

from draft_translation import read_json, write_json
from pdf_layout import checked_box, crop, pdf_digest


CAPTION = re.compile(r"^(fig(?:ure)?\.?|table)\s+(\d+[a-z]?)\s*([:.])(?:\s|$)", re.I)
NAMED_HEADINGS = {
    "abstract", "introduction", "conclusion", "conclusions", "references", "bibliography",
    "acknowledgments", "acknowledgements", "ethics statement", "limitations",
}


def bbox(line):
    return [round(line[key], 1) for key in ("x0", "top", "x1", "bottom")]


def line_info(region, find_gutter=False):
    from pdfplumber.utils import extract_text

    result = []
    middle = sum(region.bbox[::2]) / 2
    band = region.width * 0.045
    for line in region.extract_text_lines(x_tolerance=1, return_chars=True):
        chars = [char for char in line["chars"] if char["text"].strip()]
        if not chars:
            continue
        sizes = Counter(round(char["size"], 1) for char in chars)
        bold = sum(bool(re.search(r"bold|black|heavy|demi|semibold|[-+]bx", char["fontname"], re.I)) for char in chars)
        entry = {"text": line["text"], "box": bbox(line), "size": sizes.most_common(1)[0][0],
                 "bold": bold >= len(chars) * 0.65}
        if find_gutter:
            ordered = sorted(chars, key=lambda char: char["x0"])
            gaps = [(right["x0"] - left["x1"], index)
                    for index, (left, right) in enumerate(zip(ordered, ordered[1:]), start=1)
                    if left["x1"] < middle + band and right["x0"] > middle - band]
            gap, index = max(gaps, default=(0, 0))
            if gap >= max(7, entry["size"] * 0.72) and min(index, len(ordered) - index) > 5:
                entry["parts"] = [
                    {"text": extract_text(segment, x_tolerance=1).replace("\n", " "),
                     "box": [round(boundary(char[key] for char in segment), 1)
                             for key, boundary in zip(("x0", "top", "x1", "bottom"), (min, min, max, max))],
                     "size": entry["size"], "bold": False}
                    for segment in (ordered[:index], ordered[index:])
                ]
        result.append(entry)
    return result


def detect_columns(page, lines):
    mid = (page.bbox[0] + page.bbox[2]) / 2
    left = sum(line["box"][2] <= mid - 3 and len(line["text"]) > 22 for line in lines)
    right = sum(line["box"][0] >= mid + 3 and len(line["text"]) > 22 for line in lines)
    if min(left, right) >= 8:
        return mid
    # Some extractors merge horizontally aligned lines across the gutter.
    bands = defaultdict(lambda: [False, False, False])
    for word in page.extract_words(x_tolerance=1):
        if not page.height * 0.09 <= word["top"] <= page.height * 0.93:
            continue
        band = bands[round(word["top"] / 4)]
        side = 0 if word["x1"] <= mid - 4 else 1 if word["x0"] >= mid + 4 else 2
        band[side] = True
    paired = sum(left and right and not middle for left, right, middle in bands.values())
    crossing = sum(middle for _, _, middle in bands.values())
    return mid if paired >= 14 and paired >= 3 * max(crossing, 1) else None


def order_columns(page, lines, split):
    if split is None:
        return lines
    x0, top, x1, bottom = page.bbox
    # Full-width text with ink in the gutter divides the columns into bands.
    crossing = {round(word["top"]) for word in page.extract_words(x_tolerance=1)
                if word["x0"] < split + 3 and word["x1"] > split - 3}
    wide = [line for line in lines if line["box"][0] < split - 8 and line["box"][2] > split + 8
            and any(y in crossing for y in range(round(line["box"][1]) - 3, round(line["box"][3]) + 1))]
    left = line_info(page.within_bbox((x0, top, split, bottom)))
    right = line_info(page.within_bbox((split, top, x1, bottom)))
    ordered, previous = [], top
    for line in [*wide, {"box": [0, bottom + 1, 0, bottom + 1]}]:
        begin, end = line["box"][1], line["box"][3]
        for group in (left, right):
            ordered.extend(item for item in group if previous <= item["box"][1] < begin - 1)
        if "text" in line:
            ordered.append(line)
        previous = end - 1
    return ordered


def caption_id(line):
    match = CAPTION.match(line["text"])
    if not match or (match[3] == "." and not line["bold"]):
        return None
    return ("table-" if match[1].lower() == "table" else "fig-") + match[2].lower()


def scan(pdf, columns):
    pages, candidates = [], []
    for page in pdf.pages:
        lines = line_info(page, find_gutter=True)
        split = None
        if columns == "two":
            split = sum(page.bbox[::2]) / 2
        elif columns == "auto":
            split = detect_columns(page, lines)
        lines = order_columns(page, lines, split)
        captions = [
            {"id": name, "box": fragment["box"], "text": fragment["text"]}
            for line in lines for fragment in [line, *line.get("parts", [])]
            if (name := caption_id(fragment))
        ]
        captions = list({(item["id"], round(item["box"][1] / 3)): item for item in captions}.values())
        rules = sorted({
            tuple(bbox(edge)) for edge in page.horizontal_edges
            if edge["x1"] - edge["x0"] > page.width * 0.22
            and page.height * 0.08 < edge["top"] < page.height * 0.93
        }, key=lambda box: (box[1], box[0]))
        images = [bbox(image) for image in page.images
                  if (image["x1"] - image["x0"]) * (image["bottom"] - image["top"]) > 250]
        # Vector illustrations can have no raster images or separate caption line.
        vector = len(page.curves) >= 14 or len(page.rects) >= 12
        if captions or vector or (page.page_number != 1 and (images or len(rules) >= 2)):
            candidates.append({"page": page.page_number, "captions": captions, "horizontal_rules": rules,
                               "images": images, "vector_graphics": vector})
        pages.append({"page": page.page_number, "height": round(page.height, 1),
                      "width": round(page.width, 1), "columns": 2 if split else 1, "lines": lines})
        page.close()
    return {"pages": pages, "title": str(pdf.metadata.get("Title") or "").strip(),
            "authors": str(pdf.metadata.get("Author") or "").strip()}, candidates


def scan_summary(layout, candidates, reused, elapsed):
    pages = layout["pages"]
    warnings = [page["page"] for page in pages if not page["lines"]]
    source = "cache" if reused else "pdfplumber"
    print(f"{len(pages)} pages, {sum(p['columns'] == 2 for p in pages)} two-column, "
          f"{len(candidates)} with figure/table candidates ({source}: {elapsed:.2f}s).")
    if warnings:
        print("Pages without text; check OCR: " + ", ".join(map(str, warnings)))
    if candidates:
        labels = [
            f"{page['page']}:" + (",".join(dict.fromkeys(caption["id"] for caption in page["captions"])) or "?")
            for page in candidates
        ]
        print("Figure candidates (page:label, ? = geometry only): " + "  ".join(labels[:60]))
        if len(labels) > 60:
            print(f"{len(labels) - 60} additional candidate pages. Use probe --pages for the relevant range.")


def probe(work, numbers, box, limit):
    layout = read_json(work / "layout.json")
    if box is None:
        figures = layout.get("figure_candidates")
        if figures is None:
            figures = read_json(work / "figure-plan.json")
        for page in figures:
            if page["page"] not in numbers:
                continue
            for caption in page["captions"][:limit]:
                print(f'p. {page["page"]} {caption["id"]} {caption["box"]} {caption["text"][:160]}')
            rules = page["horizontal_rules"][:limit]
            if rules:
                print(f'p. {page["page"]} horizontal rules [x0,y,x1]: {[rule[:3] for rule in rules]}')
            images = page["images"][:limit]
            if images or page["vector_graphics"]:
                print(f'p. {page["page"]} images {images}; vectors={page["vector_graphics"]}')
        return
    for page in layout["pages"]:
        number = page["page"]
        if number not in numbers:
            continue
        checked_box(box, page["width"], page["height"], number)
        for line in page["lines"]:
            for item in line.get("parts", [line]):
                if not overlaps(item, box):
                    continue
                print(f'p. {number} {item["box"]} {item["text"]}')
                limit -= 1
                if not limit:
                    return


def running_margins(pages):
    seen = Counter()
    for page in pages:
        seen.update({line["text"] for line in page["lines"]
                     if line["box"][1] < page["height"] * 0.11 or line["box"][3] > page["height"] * 0.92})
    return {text for text, count in seen.items() if count >= max(2, min(4, (len(pages) + 2) // 3))}


def heading_kind(line, body_size, in_appendix):
    text = line["text"].strip().rstrip(":").strip()
    if len(text) > 125 or caption_id(line):
        return None
    if text.casefold() in NAMED_HEADINGS and (line["bold"] or line["size"] > body_size):
        return "section"
    if line["bold"] and re.match(r"^\d+\s+\S", text):
        return "section"
    if not line["bold"] and line["size"] < body_size + 0.9:
        return None
    if line["size"] >= body_size + 0.7 and (
        re.match(r"^(?:Appendix\b|[A-Z][.:]?\s+[A-Z])", text)
        and (in_appendix or bool(re.match(r"^(?:Appendix\b|A[.:]?\s)", text)))
    ):
        return "appendix"
    if re.match(r"^(?:\d+|[A-Z])(?:\.\d+)+\s+\S", text):
        return "subheading"
    if line["size"] >= body_size + 0.7 and len(text.split()) <= 16 and not text.endswith((".", ",", ";", "?")):
        return "section"
    return None


def overlaps(line, box):
    left, top, right, bottom = line["box"]
    x0, y0, x1, y1 = box
    return x0 <= (left + right) / 2 <= x1 and y0 <= (top + bottom) / 2 <= y1


def is_paragraph_break(previous, line, size):
    last, current = previous["box"], line["box"]
    gap = current[1] - last[3]
    return (gap < -size or gap > 0.65 * size
            or (last[0] + size * 0.65 < current[0] and previous["text"].endswith((".", ":", "?", "!")))
            or bool(re.match(r"^(?:[•▪]\s|\d+[.)]\s)", line["text"])))


def join_lines(lines):
    text = lines[0]["text"]
    for line in lines[1:]:
        next_text = line["text"]
        if text.endswith("\u00ad"):
            text = text[:-1] + next_text
        else:
            # Preserve printed hyphens so copy/paste retains compound terms.
            text += ("" if re.search(r"[a-z]-$", text) and re.match(r"^[a-z]", next_text) else " ") + next_text
    return text


def page_label(first, last):
    return f"p. {first}" if first == last else f"pp. {first}–{last}"


def draft(layout, crops, output):
    pages = layout["pages"]
    margins = running_margins(pages)
    sizes = Counter(line["size"] for page in pages for line in page["lines"]
                    if len(line["text"]) > 40)
    if not sizes:
        raise ValueError("No readable text found. OCR the PDF and scan it again.")
    body_size = sizes.most_common(1)[0][0]
    sections = []
    current = None
    appendix = False
    paragraph, label = [], ""
    jobs = defaultdict(list)
    for item in crops:
        jobs[item["page"]].append(item)
    title = layout["title"]
    if not title:
        first = pages[0]["lines"]
        title_size = max((line["size"] for line in first if len(line["text"]) > 10), default=0)
        title = " ".join(line["text"] for line in first if line["size"] == title_size).strip()

    def section(text, kind="section"):
        nonlocal current, appendix, label
        text = text.strip()
        id_builder = re.sub(r"[^a-z0-9]+", "-", text.casefold()).strip("-")
        section_id = id_builder if id_builder in {"abstract", "references", "bibliography", "conclusion", "conclusions"} else f"s-{len(sections) + 1:02}"
        if any(s["id"] == section_id for s in sections):
            section_id = f"s-{len(sections) + 1:02}"
        appendix = appendix or kind == "appendix"
        current = {"id": section_id, "title": text, "blocks": []}
        if appendix:
            current["appendix"] = True
        elif text.casefold() in {"references", "bibliography"}:
            current["bibliography"] = True
        sections.append(current)
        label = ""

    def block(text, first, last, **extra):
        nonlocal label
        if current is None:
            section("正文")
        items = current["blocks"]
        item = {"id": f'{current["id"]}-{len(items) + 1:03}', "pages": page_label(first, last),
                "original": text, **extra}
        if label and not item.get("label"):
            item["label"] = label
            label = ""
        items.append(item)

    def flush():
        if paragraph:
            block(join_lines([line for _, line in paragraph]), paragraph[0][0], paragraph[-1][0])
            paragraph.clear()

    first_page = pages[0]["lines"]
    abstract_top = next((line["box"][1] for line in first_page if line["text"].strip().casefold() == "abstract"), None)
    for page in pages:
        number = page["page"]
        lines = []
        floats = [item["box"] for item in jobs[number] if item["box"][2] - item["box"][0] < page["width"] * 0.48]
        for line in page["lines"]:
            # Split neighboring prose from side figures only in their vertical band.
            near_float = any(box[1] - 85 <= line["box"][1] <= box[3] + 85 for box in floats)
            lines.extend(line.get("parts", [line]) if near_float else [line])
        source = [line for line in lines if not (
            (line["box"][1] < page["height"] * 0.11 or line["box"][3] > page["height"] * 0.92)
            and (line["text"] in margins or re.fullmatch(r"\d+", line["text"])))
            and not (number == 1 and abstract_top is not None and line["box"][1] < abstract_top)]
        insertions, omitted = defaultdict(list), set()
        for item in jobs[number]:
            name = Path(item["file"]).stem
            canonical_name = name.replace("tbl-", "table-", 1) if name.startswith("tbl-") else name
            spaces = [i for i, line in enumerate(source) if overlaps(line, item["box"])
                      and line["text"].strip().casefold() not in NAMED_HEADINGS]
            caption = next((i for i, line in enumerate(source) if caption_id(line) == canonical_name), None)
            caption_lines = []
            if caption is not None:
                caption_lines.append(caption)
                side_caption = source[caption]["box"][0] > page["width"] * 0.43
                for index in range(caption + 1, len(source)):
                    line = source[index]
                    if side_caption and line["box"][0] < page["width"] * 0.43:
                        continue
                    if (index in spaces or is_paragraph_break(source[caption_lines[-1]], line, body_size)
                            or caption_id(line) or heading_kind(line, body_size, appendix)):
                        break
                    caption_lines.append(index)
                omitted.update(caption_lines)
            fallback = next((i for i, line in enumerate(source) if line["box"][1] >= item["box"][1]), len(source))
            indexes = spaces + ([caption] if caption is not None else [])
            target = min(indexes, default=fallback)
            text = item.get("caption") or (join_lines([source[i] for i in caption_lines]) if caption_lines else "")
            display = item.get("label") or canonical_name.replace("fig-", "Figure ").replace("table-", "Table ")
            insertions[target].append((item, text, display))
            omitted.update(spaces)
        for i in range(len(source) + 1):
            for item, text, display in insertions[i]:
                flush()
                extra = {"label": display, "alt": display, "image": "media/" + item["file"]}
                if item.get("show_in_summary"):
                    extra["show_in_summary"] = True
                block(text, number, number, **extra)
            if i == len(source) or i in omitted:
                continue
            line = source[i]
            kind = heading_kind(line, body_size, appendix)
            if kind:
                flush()
                if kind == "subheading" and current:
                    label = line["text"]
                else:
                    section(line["text"], kind)
                continue
            if paragraph:
                last_page, last_line = paragraph[-1]
                new_page_break = last_page != number and bool(re.search(r"[.?!:]\s*$", last_line["text"]))
                if new_page_break or (last_page == number and is_paragraph_break(last_line, line, body_size)):
                    flush()
            paragraph.append((number, line))
    flush()
    sections = [s for s in sections if s["blocks"]]
    if not sections:
        raise ValueError("No reading blocks found. Check the extracted layout.")
    for entry in sections:
        if entry.get("appendix"):
            first = int(re.findall(r"\d+", entry["blocks"][0]["pages"])[0])
            last = int(re.findall(r"\d+", entry["blocks"][-1]["pages"])[-1])
            entry["summary"] = {"id": entry["id"] + "-summary", "pages": page_label(first, last)}
    paper = {"title": title or output.parent.name, "original_title": title or output.parent.name,
             "authors": layout["authors"], "citation": f"PDF · {len(pages)} pp.", "sections": sections}
    write_json(output, paper)
    print(f"{len(sections)} sections, {sum(len(s['blocks']) for s in sections)} blocks, {len(crops)} placed figures.")
    for entry in sections:
        first, last = entry["blocks"][0]["pages"], entry["blocks"][-1]["pages"]
        print(f'{entry["id"]} | {first} to {last} | {len(entry["blocks"])} | {entry["title"]}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("scan", "draft"):
        command = sub.add_parser(name)
        command.add_argument("pdf", type=Path)
        command.add_argument("work", type=Path)
        if name == "scan":
            command.add_argument("--columns", choices=("auto", "one", "two"), default="auto")
            command.add_argument("--refresh", action="store_true")
        command.add_argument("--crops", type=Path)
    probe_command = sub.add_parser("probe")
    probe_command.add_argument("work", type=Path)
    probe_command.add_argument("--pages", required=True, help="Comma-separated PDF page numbers")
    probe_command.add_argument("--box", nargs=4, type=float, metavar=("X0", "TOP", "X1", "BOTTOM"))
    probe_command.add_argument("--limit", type=int, default=12, help="Limit each geometry list or the total text lines")
    args = parser.parse_args()
    try:
        if args.command == "probe":
            numbers = {int(number) for number in args.pages.split(",")}
            if min(numbers) < 1 or args.limit < 1:
                raise ValueError("Page numbers and --limit must be positive.")
            probe(args.work, numbers, args.box, args.limit)
            return
        started = perf_counter()
        digest = pdf_digest(args.pdf)
        layout_path, plan_path = (args.work / name for name in ("layout.json", "figure-plan.json"))
        if args.command == "scan":
            key = {"version": 2, "pdf": digest, "columns": args.columns}
            layout = {}
            candidates = []
            if not args.refresh and layout_path.is_file() and plan_path.is_file():
                try:
                    layout = read_json(layout_path)
                except (OSError, ValueError):
                    layout = {}
            reused = isinstance(layout, dict) and layout.get("scan") == key and "figure_candidates" in layout
            if reused:
                candidates = layout["figure_candidates"]
            else:
                import pdfplumber
                with pdfplumber.open(args.pdf) as pdf:
                    layout, candidates = scan(pdf, args.columns)
                layout["scan"] = key
                layout["figure_candidates"] = candidates
                write_json(plan_path, candidates)
                write_json(layout_path, layout)
            scan_summary(layout, candidates, reused, perf_counter() - started)
            if not args.crops:
                return
        else:
            layout = read_json(layout_path)
            if layout.get("scan", {}).get("pdf", digest) != digest:
                raise ValueError("The cached layout belongs to another PDF. Run scan first.")
        items = read_json(args.crops) if args.crops else []
        if items:
            crop(args.pdf, items, args.work / "media", 360, digest=digest)
        started = perf_counter()
        draft(layout, items, args.work / "manuscript.json")
        print(f"Manuscript: {perf_counter() - started:.2f}s.")
    except (ImportError, OSError, ValueError, KeyError) as error:
        parser.exit(2, f"{error}\n")


if __name__ == "__main__":
    main()
