#!/usr/bin/env python3
import argparse
import csv
import re
from datetime import datetime
from pathlib import Path


OUTPUT_FIELDS = [
    "diff_status",
    "match_key",
    "before_id",
    "after_id",
    "before_title",
    "after_title",
    "before_authors",
    "after_authors",
    "before_date",
    "after_date",
    "before_doi",
    "after_doi",
    "changed_fields",
]


def normalize_text(value):
    value = (value or "").casefold()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_doi(value):
    value = (value or "").strip().lower()
    value = re.sub(r"^https?://(dx\.)?doi\.org/", "", value)
    value = re.sub(r"^doi:\s*", "", value)
    return value.rstrip(").,;]")


def first_present(row, names):
    lower_map = {key.lower(): key for key in row.keys()}
    for name in names:
        key = lower_map.get(name.lower())
        if key and row.get(key):
            return row.get(key, "").strip()
    return ""


def canonical_row(row):
    title = first_present(row, ["title", "Title", "Publication Title"])
    authors = first_present(row, ["authors", "creators", "author", "Author"])
    date = first_present(row, ["date", "year", "publicationYear", "Date"])
    doi = normalize_doi(first_present(row, ["doi", "DOI"]))
    zotero_id = first_present(row, ["id", "key", "Key", "zotero_item_id", "batlit_zotero_id"])
    year_match = re.search(r"\b(18|19|20)\d{2}\b", date)
    year = year_match.group(0) if year_match else ""

    if zotero_id:
        match_key = f"id:{zotero_id}"
    elif doi:
        match_key = f"doi:{doi}"
    else:
        match_key = f"title-year:{normalize_text(title)}:{year}"

    return {
        "match_key": match_key,
        "id": zotero_id,
        "title": title,
        "authors": authors,
        "date": date,
        "doi": doi,
    }


def read_rows(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [canonical_row(row) for row in csv.DictReader(handle)]


def index_rows(rows):
    indexed = {}
    for row in rows:
        indexed.setdefault(row["match_key"], []).append(row)
    return indexed


def changed_fields(before, after):
    fields = []
    for name in ["title", "authors", "date", "doi"]:
        if (before.get(name) or "") != (after.get(name) or ""):
            fields.append(name)
    return fields


def diff_rows(before_rows, after_rows):
    before_index = index_rows(before_rows)
    after_index = index_rows(after_rows)
    keys = sorted(set(before_index) | set(after_index))
    output = []

    for key in keys:
        before = before_index.get(key, [])
        after = after_index.get(key, [])
        max_len = max(len(before), len(after))
        for index in range(max_len):
            b = before[index] if index < len(before) else None
            a = after[index] if index < len(after) else None

            if b and a:
                changed = changed_fields(b, a)
                status = "changed" if changed else "unchanged"
            elif a:
                changed = []
                status = "added"
            else:
                changed = []
                status = "removed"

            output.append({
                "diff_status": status,
                "match_key": key,
                "before_id": b.get("id", "") if b else "",
                "after_id": a.get("id", "") if a else "",
                "before_title": b.get("title", "") if b else "",
                "after_title": a.get("title", "") if a else "",
                "before_authors": b.get("authors", "") if b else "",
                "after_authors": a.get("authors", "") if a else "",
                "before_date": b.get("date", "") if b else "",
                "after_date": a.get("date", "") if a else "",
                "before_doi": b.get("doi", "") if b else "",
                "after_doi": a.get("doi", "") if a else "",
                "changed_fields": " | ".join(changed),
            })

    return output


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description="Diff before/after Zotero collection CSV exports.")
    parser.add_argument("--base", default=".", help="batlit-dedupe folder; defaults to current directory")
    parser.add_argument("--before", required=True, help="before Zotero/BatLit CSV export")
    parser.add_argument("--after", required=True, help="after Zotero/BatLit CSV export")
    parser.add_argument("--label", default="zotero-diff", help="short label for the diff folder")
    args = parser.parse_args()

    base = Path(args.base).resolve()
    before_path = Path(args.before).resolve()
    after_path = Path(args.after).resolve()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    label = re.sub(r"[^a-z0-9]+", "-", args.label.lower()).strip("-") or "zotero-diff"
    out_dir = base / "zotero_diffs" / f"{stamp}_{label}"

    before_rows = read_rows(before_path)
    after_rows = read_rows(after_path)
    rows = diff_rows(before_rows, after_rows)

    write_csv(out_dir / "zotero_collection_diff.csv", rows)
    for status in ["added", "removed", "changed", "unchanged"]:
        write_csv(out_dir / f"{status}.csv", [row for row in rows if row["diff_status"] == status])

    counts = {status: sum(1 for row in rows if row["diff_status"] == status) for status in ["added", "removed", "changed", "unchanged"]}
    summary = [
        f"Zotero diff: {out_dir.name}",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"Before: {before_path}",
        f"After: {after_path}",
        "",
        f"Before rows: {len(before_rows)}",
        f"After rows: {len(after_rows)}",
        f"Added: {counts['added']}",
        f"Removed: {counts['removed']}",
        f"Changed: {counts['changed']}",
        f"Unchanged: {counts['unchanged']}",
    ]
    (out_dir / "summary.txt").write_text("\n".join(summary) + "\n", encoding="utf-8")

    print(out_dir)
    print("\n".join(summary))


if __name__ == "__main__":
    main()
