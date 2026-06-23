#!/usr/bin/env python3
import argparse
import csv
import re
from datetime import datetime
from pathlib import Path


YEAR_RE = re.compile(r"\b(18|19|20)\d{2}\b")
MD5_RE = re.compile(r"hash://md5/([a-f0-9]{32})", re.IGNORECASE)


def normalize_doi(value):
    value = (value or "").strip().lower()
    value = re.sub(r"^https?://(dx\.)?doi\.org/", "", value)
    value = re.sub(r"^doi:\s*", "", value)
    return value.rstrip(").,;]")


def normalize_text(value):
    value = (value or "").casefold()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def year_from_date(value):
    match = YEAR_RE.search(value or "")
    return match.group(0) if match else ""


def first_author(value):
    value = (value or "").strip()
    if not value:
        return ""
    if "|" in value:
        first = value.split("|", 1)[0]
    elif ";" in value:
        first = value.split(";", 1)[0]
    else:
        first = re.split(r"\s+(?:and|&)\s+", value, maxsplit=1, flags=re.IGNORECASE)[0]
    return re.sub(r"\s+", " ", first).strip(" ,.")


def extract_md5s(row):
    values = []
    for field in ("attachmentId", "corpusId", "zenodoResponseCorpusId"):
        values.extend(MD5_RE.findall(row.get(field, "") or ""))
    return sorted(set(value.lower() for value in values))


def write_csv(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description="Build a lightweight BatLit literature fingerprint index.")
    parser.add_argument("--base", default=".", help="batlit-dedupe folder.")
    parser.add_argument("--refs", default="index/refs.csv", help="BatLit refs.csv relative to base.")
    parser.add_argument("--output", default="index/literature_fingerprint_index.csv", help="Output CSV relative to base.")
    args = parser.parse_args()

    base = Path(args.base).resolve()
    refs_path = base / args.refs
    output_path = base / args.output
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    timestamped_output = output_path.with_name(f"{stamp}_{output_path.name}")

    rows = []
    with refs_path.open(newline="", encoding="utf-8-sig") as handle:
        for source_row in csv.DictReader(handle):
            title = source_row.get("title", "")
            authors = source_row.get("authors", "")
            doi = normalize_doi(source_row.get("doi"))
            alt_doi = normalize_doi(source_row.get("alternativeDoi"))
            md5s = extract_md5s(source_row)
            rows.append({
                "index_created": stamp,
                "source": "batlit_refs_csv",
                "zotero_item_id": source_row.get("id", ""),
                "attachment_api_url": source_row.get("attachment", ""),
                "attachment_id": source_row.get("attachmentId", ""),
                "doi": doi,
                "alternative_doi": alt_doi,
                "title": title,
                "normalized_title": normalize_text(title),
                "authors": authors,
                "normalized_authors": normalize_text(authors),
                "first_author": first_author(authors),
                "normalized_first_author": normalize_text(first_author(authors)),
                "year": year_from_date(source_row.get("date", "")),
                "date": source_row.get("date", ""),
                "journal": source_row.get("journal", ""),
                "item_type": source_row.get("type", ""),
                "volume": source_row.get("volume", ""),
                "issue": source_row.get("issue", ""),
                "pages": source_row.get("pages", ""),
                "md5": " | ".join(md5s),
                "page_count": "",
                "first_page_text_fingerprint": "",
                "first_3_pages_text_fingerprint": "",
                "batlit_url_or_source": source_row.get("id", ""),
            })

    fields = [
        "index_created",
        "source",
        "zotero_item_id",
        "attachment_api_url",
        "attachment_id",
        "doi",
        "alternative_doi",
        "title",
        "normalized_title",
        "authors",
        "normalized_authors",
        "first_author",
        "normalized_first_author",
        "year",
        "date",
        "journal",
        "item_type",
        "volume",
        "issue",
        "pages",
        "md5",
        "page_count",
        "first_page_text_fingerprint",
        "first_3_pages_text_fingerprint",
        "batlit_url_or_source",
    ]
    write_csv(output_path, fields, rows)
    write_csv(timestamped_output, fields, rows)
    print(f"Fingerprint records: {len(rows)}")
    print(output_path)
    print(timestamped_output)


if __name__ == "__main__":
    main()
