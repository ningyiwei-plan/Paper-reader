"""Build a self-contained bilingual paper reader from a JSON manuscript."""

import argparse
import base64
import hashlib
import html
import json
from pathlib import Path
import re


def escape(value):
    return html.escape(value, quote=True)


def required(data, key):
    value = data[key]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be nonempty text")
    return escape(value.strip())


def image_markup(block, root):
    path = (root / block["image"]).resolve()
    mime_types = {".png": "image/png", ".jpeg": "image/jpeg", ".jpg": "image/jpeg", ".webp": "image/webp"}
    if not path.is_relative_to(root) or path.suffix.lower() not in mime_types:
        raise ValueError(f"Image must be a PNG/JPEG/WebP under the manuscript directory: {path}")
    graphic = path.read_bytes()
    encoded = base64.b64encode(graphic).decode("ascii")
    dimensions = ""
    if graphic.startswith(b"\x89PNG\r\n\x1a\n") and len(graphic) >= 24:
        width, height = (int.from_bytes(graphic[offset:offset + 4], "big") for offset in (16, 20))
        dimensions = f' width="{width}" height="{height}"'
    elif graphic.startswith(b"RIFF") and graphic[8:16] == b"WEBPVP8L" and len(graphic) >= 25:
        bits = int.from_bytes(graphic[21:25], "little")
        dimensions = f' width="{1 + (bits & 0x3fff)}" height="{1 + ((bits >> 14) & 0x3fff)}"'
    alt = required(block, "alt")
    return (f'<button class="figure-trigger" type="button" aria-label="放大：{alt}">'
            f'<img src="data:{mime_types[path.suffix.lower()]};base64,{encoded}" alt="{alt}"{dimensions} '
            'loading="lazy" decoding="async">'
            '<span>点击放大</span></button>')


def build(manuscript, template, source_pdf=None, appendix="summary", detailed_appendices=()):
    root = manuscript.resolve().parent
    raw = manuscript.read_text(encoding="utf-8-sig")
    paper = json.loads(raw)
    ids = set()
    toc, sections = [], []

    def anchor(data):
        value = data["id"]
        if not re.fullmatch(r"[a-z][a-z0-9-]*", value) or value in ids:
            raise ValueError(f"Invalid or duplicate ID: {value}")
        ids.add(value)
        return value

    appendix_ids = {section["id"] for section in paper["sections"] if section.get("appendix")}
    unknown = set(detailed_appendices) - appendix_ids
    if unknown:
        raise ValueError(f"Unknown appendix sections: {', '.join(sorted(unknown))}")
    for section in paper["sections"]:
        is_appendix = section.get("appendix", False)
        is_detailed = not is_appendix or appendix == "full" or section["id"] in detailed_appendices
        if is_appendix and appendix == "omit" and not is_detailed:
            continue
        section_id = anchor(section)
        title = required(section, "title")
        toc.append(f'<a href="#{section_id}">{title}</a>')
        units = []
        blocks = section["blocks"]
        if not is_detailed:
            blocks = [dict(section["summary"], summary_only=True)]
            blocks.extend(block for block in section["blocks"] if block.get("show_in_summary"))
        for block in blocks:
            block_id = anchor(block)
            pages = required(block, "pages")
            zh = required(block, "summary_zh" if not is_detailed and "summary_zh" in block else "zh")
            explanation = required(block, "explain")
            label = escape(block.get("label", ""))
            original = escape(block.get("original", "").strip())
            summary_only = block.get("summary_only", False)
            if "image" in block:
                original = image_markup(block, root) + (f'<figcaption class="markable" data-part="orig" lang="en">{original}</figcaption>' if original else "")
                original = f'<figure>{original}</figure>'
            elif original:
                original = f'<p class="original markable" data-part="orig" lang="en">{original}</p>'
            elif not summary_only:
                raise ValueError(f"{block_id} has neither original text nor an image")
            heading = f'<h3>{label}</h3>' if label else ""
            source_label = "附录提要" if summary_only else "原文"
            zh_label = "中文图表说明" if not is_detailed and "image" in block else "中文翻译"
            translation = (f'<p class="markable" data-part="zh">{zh}</p>' if summary_only else
                           f'<span class="eyebrow">{zh_label}</span><p class="markable" data-part="zh">{zh}</p>')
            units.append(f'''<div class="unit" id="{block_id}">
  <article class="reading" aria-label="原文与译文">
    <div class="source-line"><span>{source_label}</span><a href="#{block_id}" title="打开本段链接">{pages}</a></div>
    {heading}{original}
    <div class="{'summary-text' if summary_only else 'translation'}">{translation}</div>
  </article>
  <aside class="annotation" aria-label="本段释义与笔记">
    <div class="insight"><span class="eyebrow">释义</span><p class="markable" data-part="explain">{explanation}</p></div>
    <details class="note" data-note="{block_id}">
      <summary>我的笔记<span class="note-state"></span></summary>
      <label class="visually-hidden" for="note-{block_id}">本段笔记</label>
      <textarea id="note-{block_id}" placeholder="记下疑问、思路或待验证的想法…" rows="3"></textarea>
      <button class="new-judgment" type="button">记下本段判断</button>
    </details>
  </aside>
</div>''')
        if not units:
            raise ValueError(f"Empty section: {section_id}")
        sections.append(f'''<section class="chapter" id="{section_id}">
<div class="chapter-heading"><h2>{title}</h2><span>{escape(section.get("subtitle", ""))}</span></div>
{"".join(units)}
</section>''')
    if not sections:
        raise ValueError("No sections")

    pdf_data = ""
    pdf_button = ""
    if source_pdf is not None:
        pdf_bytes = source_pdf.read_bytes()
        if not pdf_bytes.startswith(b"%PDF-"):
            raise ValueError("The embedded source must be a PDF")
        pdf_data = '<script type="application/octet-stream" id="source-pdf">' + base64.b64encode(pdf_bytes).decode("ascii") + '</script>'
        pdf_button = f'<button type="button" id="download-source" data-name="{escape(source_pdf.name)}">原始 PDF</button>'
    assets = Path(__file__).resolve().parents[1] / "assets"
    values = {
        "TITLE": required(paper, "title"),
        "ORIGINAL_TITLE": required(paper, "original_title"),
        "AUTHORS": escape(paper.get("authors", "")),
        "CITATION": escape(paper.get("citation", "")),
        "SCOPE": escape(paper.get("scope", "")),
        "TOC": "".join(toc),
        "SECTIONS": "".join(sections),
        "DOC_ID": hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24],
        "PDF_DATA": pdf_data,
        "PDF_BUTTON": pdf_button,
        "MARKS_SCRIPT": (assets / "marks.js").read_text(encoding="utf-8"),
        "JUDGMENTS_SCRIPT": (assets / "judgments.js").read_text(encoding="utf-8"),
        "APPEARANCE_STYLE": (assets / "appearance.css").read_text(encoding="utf-8"),
    }
    return re.sub(r"@@([A-Z_]+)@@", lambda match: values[match[1]], template)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manuscript", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--source-pdf", type=Path)
    parser.add_argument("--appendix", choices=("summary", "full", "omit"), default="summary")
    parser.add_argument("--appendix-detail", action="append", default=[], metavar="SECTION_ID")
    args = parser.parse_args()
    template = Path(__file__).resolve().parents[1] / "assets" / "reader.html"
    output = build(args.manuscript, template.read_text(encoding="utf-8"), args.source_pdf,
                   args.appendix, args.appendix_detail)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(output, encoding="utf-8")


if __name__ == "__main__":
    main()
