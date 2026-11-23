"""Fill draft translations with a local engine and list blocks needing review."""

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import unicodedata
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as file:
        temporary = Path(file.name)
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def make_engine(args):
    if args.engine == "argos":
        try:
            from argostranslate import translate
        except ImportError as error:
            raise ValueError("Install argostranslate and a local source-to-Chinese model, or use --engine libre.") from error
        languages = {language.code: language for language in translate.get_installed_languages()}
        if args.source not in languages or args.target not in languages:
            raise ValueError(f"Install a local Argos {args.source} → {args.target} model first.")
        pair = languages[args.source].get_translation(languages[args.target])
        if pair is None:
            raise ValueError(f"No local Argos translation for {args.source} → {args.target}.")
        return lambda texts: [pair.translate(item) for item in texts]

    url = urlsplit(args.endpoint)
    if (url.scheme != "http" or url.hostname not in {"localhost", "127.0.0.1", "::1"}
            or url.username or url.password or url.fragment):
        raise ValueError("Use a loopback LibreTranslate URL, such as http://127.0.0.1:5000/translate.")
    client = build_opener(ProxyHandler({}), NoRedirect())

    def translate_batch(texts):
        payload = {"q": texts, "source": args.source, "target": args.target, "format": "text"}
        request = Request(args.endpoint, json.dumps(payload).encode("utf-8"),
                          headers={"Content-Type": "application/json"})
        with client.open(request, timeout=args.timeout) as response:
            return json.load(response)["translatedText"]

    return translate_batch


def batches(items, count, size):
    batch, used = [], 0
    for item in items:
        chars = len(item[1])
        if batch and (len(batch) >= count or used + chars > size):
            yield batch
            batch, used = [], 0
        batch.append(item)
        used += chars
    if batch:
        yield batch


def normalized(text):
    return unicodedata.normalize("NFKC", text).replace("−", "-")


def numbers(text):
    # Author-year citations are checked as text, since many are repeated in a paragraph.
    text = re.sub(r"\((?=[^()\n]{0,240}\b(?:19|20)\d{2}[a-z]?\b)"
                  r"(?=[^()\n]{0,240}(?:et al\.|[A-Za-z]{3,}\s*,))[^()\n]+\)", "", normalized(text))
    return Counter(number.replace(",", "").lstrip("+") for number in re.findall(
        r"(?:(?<![\w.])[-+])?\d+(?:,\d{3})*(?:\.\d+)?", text
    ))


def review_reasons(section, block, glossary):
    source = block["original"]
    zh = block.get("zh", "")
    reasons = []
    if not zh.strip():
        return ["needs-translation"]
    if zh.strip() == source.strip() or not re.search(r"[\u3400-\u9fff]", zh):
        reasons.append("missing-chinese")
    if numbers(source) != numbers(zh):
        reasons.append("check-numbers")
    if re.search(r"[∑∈∪⊂∀∃≤≥±]|\b(p\s*[<>=]|95\s*%\s*(?:CI|confidence))", source, flags=re.I):
        reasons.append("equation-or-statistics")
    has_condition = re.search(r"\b(unless|only if|only when|except (?:for|when)|not significant\w*|no evidence)\b",
                              source, flags=re.I)
    dropped_negation = (re.search(r"\bnot\b(?!\s+only)", source, flags=re.I)
                        and not re.search(r"[不未无非没勿]", zh))
    if has_condition or dropped_negation:
        reasons.append("negation-or-conditions")
    if re.search(r"abstract|conclusion", section["id"], flags=re.I):
        reasons.append("key-section")
    if any(re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", source, flags=re.I) and expected not in zh
           for term, expected in glossary.items()):
        reasons.append("terminology")
    if block.get("review"):
        reasons.append("manual-flag")
    return reasons


def selected_sections(manuscript, appendix, detailed):
    return [section for section in manuscript["sections"] if not section.get("appendix")
            or appendix == "full" or section["id"] in detailed]


def fill(sections, args):
    if args.engine == "review":
        return 0, 0
    pending, reused = {}, 0
    namespace = [args.engine, args.endpoint if args.engine == "libre" else "", args.source, args.target, args.revision]
    for section in sections:
        for block in section["blocks"]:
            source = block.get("original", "").strip()
            if not source or block.get("zh", "").strip():
                continue
            key = hashlib.sha256(json.dumps(namespace + [source], ensure_ascii=False).encode("utf-8")).hexdigest()
            path = args.cache / (key + ".json")
            if path.exists():
                cached = read_json(path)
                if not isinstance(cached, str) or not cached.strip():
                    raise ValueError(f"Invalid cached translation: {path}")
                block["zh"] = cached
                reused += 1
            else:
                pending.setdefault(key, (source, []))[1].append(block)
    if not pending:
        return 0, reused
    engine = make_engine(args)
    items = ((key, source, blocks) for key, (source, blocks) in pending.items())
    translated = 0
    for batch in batches(items, args.batch_size, args.batch_chars):
        results = engine([source for _, source, _ in batch])
        if isinstance(results, str) and len(batch) == 1:
            results = [results]
        if (not isinstance(results, list) or len(results) != len(batch)
                or any(not isinstance(item, str) or not item.strip() for item in results)):
            raise ValueError("Translation batch did not return one nonempty result per input. Check the engine and retry.")
        for (key, _, blocks), result in zip(batch, results):
            result = result.strip()
            write_json(args.cache / (key + ".json"), result)
            for block in blocks:
                block["zh"] = result
                translated += 1
    return translated, reused


def make_report(sections, glossary):
    flagged, total = [], 0
    for section in sections:
        sampled = False
        for block in section["blocks"]:
            if not block.get("original", "").strip():
                continue
            total += 1
            reasons = review_reasons(section, block, glossary)
            if not reasons and not sampled:
                reasons = ["spot-check"]
                sampled = True
            if reasons:
                flagged.append({"id": block["id"], "section": section["id"], "reasons": reasons})
    return {"text_blocks": total, "flagged": flagged}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manuscript", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--engine", choices=("argos", "libre", "review"), default="review")
    parser.add_argument("--endpoint", default="http://127.0.0.1:5000/translate")
    parser.add_argument("--source", default="en")
    parser.add_argument("--target", default="zh")
    parser.add_argument("--revision", default="default", help="Change to invalidate cache when replacing the engine or model.")
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--batch-size", type=int, default=24)
    parser.add_argument("--batch-chars", type=int, default=12000)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--glossary", type=Path)
    parser.add_argument("--appendix", choices=("summary", "full", "omit"), default="summary")
    parser.add_argument("--appendix-detail", action="append", default=[])
    args = parser.parse_args()
    if min(args.batch_size, args.batch_chars, args.timeout) < 1:
        parser.error("Batch limits and timeout must be positive.")
    if args.output.resolve() in {args.report.resolve(), args.manuscript.resolve()} or args.report.resolve() == args.manuscript.resolve():
        parser.error("Manuscript, output, and report must be separate files.")
    args.cache = args.cache or args.output.parent / ".translation-cache"
    try:
        manuscript = read_json(args.manuscript)
        glossary = read_json(args.glossary) if args.glossary else {}
        if not isinstance(glossary, dict) or any(not key or not isinstance(value, str) or not value for key, value in glossary.items()):
            raise ValueError("Glossary must map nonempty source terms to nonempty Chinese terms.")
        sections = selected_sections(manuscript, args.appendix, set(args.appendix_detail))
        translated, cached = fill(sections, args)
        report = make_report(sections, glossary)
        report.update(translated=translated, reused_from_cache=cached)
        write_json(args.output, manuscript)
        write_json(args.report, report)
        print(f"{translated} drafted, {cached} reused, {len(report['flagged'])}/{report['text_blocks']} queued for review.")
    except (OSError, ValueError, KeyError) as error:
        parser.exit(2, f"{error}\n")


if __name__ == "__main__":
    main()
