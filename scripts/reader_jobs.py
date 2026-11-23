"""Queue bounded editing batches and merge ID-keyed reader edits."""

import argparse
import json
from pathlib import Path

from draft_translation import read_json, write_json


def sample_appendix(blocks, limit=5000):
    sources = [block["original"] for block in blocks if block.get("original")]
    if sum(map(len, sources)) + 2 * len(sources) <= limit:
        return "\n\n".join(sources), False
    indices = sorted({round((len(sources) - 1) * index / 7) for index in range(8)})
    budget = (limit - 2 * len(indices)) // len(indices)
    return "\n\n".join(text if len(text) <= budget else text[:budget - 1] + "…"
                       for index in indices if (text := sources[index])), True


def jobs(paper, review, appendix, detailed):
    if not any("\u3400" <= character <= "\u9fff" for character in paper["title"]):
        yield {"id": "paper", "title": paper["original_title"], "task": "translate-title"}
    for section in paper["sections"]:
        if section.get("bibliography"):
            continue
        short = section.get("appendix") and appendix != "full" and section["id"] not in detailed
        if short and appendix == "omit":
            continue
        if short:
            summary = section["summary"]
            if not summary.get("zh", "").strip():
                evidence, sampled = sample_appendix(section["blocks"])
                yield {"id": summary["id"], "section": section["title"], "pages": summary["pages"],
                       "task": "summarize-appendix", "excerpts": evidence, "sampled": sampled}
        for block in section["blocks"]:
            if short and not block.get("show_in_summary"):
                continue
            zh = block.get("summary_zh") if short and block.get("summary_zh") else block.get("zh")
            reasons = review.get(block["id"], [])
            if zh and not reasons:
                continue
            job = {"id": block["id"], "section": section["title"],
                   "task": "review" if zh else "translate", "original": block.get("original", "")}
            if block.get("label"):
                job["label"] = block["label"]
            if zh:
                job.update(zh=zh, reasons=reasons)
            yield job


def write_batches(items, directory, budget):
    directory.mkdir(parents=True, exist_ok=True)
    batch, paths, size, total = [], [], 0, 0

    def save():
        path = directory / f"batch-{len(paths) + 1:03}.json"
        write_json(path, batch)
        paths.append(path)

    for item in items:
        char_count = len(json.dumps(item, ensure_ascii=False))
        if batch and size + char_count > budget:
            save()
            batch, size = [], 0
        batch.append(item)
        size += char_count
        total += 1
    if batch:
        save()
    print(f"{total} jobs in {len(paths)} batches.")
    for path in paths:
        print(path)


def merge(paper, patch_files):
    targets = {"paper": (paper, {"title", "scope"})}
    for section in paper["sections"]:
        for block in section["blocks"]:
            targets[block["id"]] = (block, {"zh", "explain", "summary_zh", "alt"} if block.get("image")
                                   else {"zh", "explain"})
        if "summary" in section:
            summary = section["summary"]
            targets[summary["id"]] = (summary, {"zh", "explain"})
    fields = set()
    for path in patch_files:
        edits = read_json(path)
        if not isinstance(edits, dict):
            raise ValueError(f"{path}: expected a JSON object keyed by ID.")
        for target, changes in edits.items():
            if target not in targets or not isinstance(changes, dict) or not changes:
                raise ValueError(f"{path}: invalid patch entry {target}.")
            item, allowed = targets[target]
            for key, value in changes.items():
                if key not in allowed or not isinstance(value, str) or not value.strip():
                    raise ValueError(f"{path}: invalid field {target}.{key}.")
                if (target, key) in fields:
                    raise ValueError(f"{path}: duplicate edit for {target}.{key}.")
                fields.add((target, key))
                item[key] = value.strip()
    return len(fields)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    queue = sub.add_parser("queue")
    queue.add_argument("manuscript", type=Path)
    queue.add_argument("directory", type=Path)
    queue.add_argument("--review", type=Path)
    queue.add_argument("--batch-chars", type=int, default=12000)
    queue.add_argument("--appendix", choices=("summary", "full", "omit"), default="summary")
    queue.add_argument("--appendix-detail", action="append", default=[])
    apply = sub.add_parser("merge")
    apply.add_argument("manuscript", type=Path)
    apply.add_argument("output", type=Path)
    apply.add_argument("patch", type=Path, nargs="+", help="JSON files or directories containing patch-*.json files")
    args = parser.parse_args()
    try:
        paper = read_json(args.manuscript)
        if args.command == "queue":
            if args.batch_chars < 1:
                raise ValueError("--batch-chars must be positive.")
            detailed = set(args.appendix_detail)
            unknown = detailed - {section["id"] for section in paper["sections"] if section.get("appendix")}
            if unknown:
                raise ValueError(f"Unknown appendix sections: {', '.join(sorted(unknown))}")
            review = ({row["id"]: row["reasons"] for row in read_json(args.review)["flagged"]}
                      if args.review else {})
            write_batches(jobs(paper, review, args.appendix, detailed), args.directory, args.batch_chars)
        else:
            paths = [file for path in args.patch
                     for file in (sorted(path.glob("patch-*.json")) if path.is_dir() else [path])]
            if not paths:
                raise ValueError("No patch files found.")
            count = merge(paper, paths)
            write_json(args.output, paper)
            print(f"Merged {count} fields from {len(paths)} patches.")
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f"{error}\n")


if __name__ == "__main__":
    main()
