#!/usr/bin/env python3
import argparse
import csv
import re
from datetime import datetime
from pathlib import Path

from pypdf import PdfReader, PdfWriter


YEAR_RE = re.compile(r"\b(18|19|20)\d{2}\b")

CURATED = {
    "Dwyer, 1966.pdf": {
        "title": "Observations on Chalinolobus dwyeri in Australia",
        "authors": "Dwyer",
        "year": "1966",
        "source": "curated_from_original_filename",
    },
    "Dobson, 1875.pdf": {
        "title": "Description of new or little-known species of the genus Vesperugo",
        "authors": "Dobson",
        "year": "1875",
        "source": "curated_from_original_filename",
    },
    "Geoffroy, 1803.pdf": {
        "title": "Catalogue des mammiferes du Museum National d'Histoire Naturelle",
        "authors": "Geoffroy Saint-Hilaire",
        "year": "1803",
        "source": "curated_from_original_filename",
    },
    "Ghose, 1981.pdf": {
        "title": "Taxonomic review of Petaurista magnificus",
        "authors": "Ghose | Saha",
        "year": "1981",
        "source": "curated_from_original_filename",
    },
    "Hayman, 1951.pdf": {
        "title": "A new African molossid bat",
        "authors": "Hayman",
        "year": "1951",
        "source": "curated_from_original_filename",
    },
}


def normalize_space(value):
    return re.sub(r"\s+", " ", value or "").strip()


def missing(value):
    value = normalize_space(value)
    return not value or value.lower() in {"unknown", "n/a", "none"}


def clean_title(value):
    value = Path(value or "").stem
    value = value.replace("_", " ")
    value = re.sub(r"\bpp?\.?\s*\d+.*$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\bpages?\s*\d+.*$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*,\s*$", "", value)
    return normalize_space(value.strip(" .,-_"))


def clean_author(value):
    value = normalize_space(value)
    value = re.sub(r"^\d+[.)_-]*\s*", "", value)
    value = value.replace("_", " ")
    value = re.sub(r"\bet\s+al\b\.?", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*&\s*", " | ", value)
    value = re.sub(r"\s+and\s+", " | ", value, flags=re.IGNORECASE)
    return normalize_space(value.strip(" .,-_"))


def fallback_from_original_file(original_file):
    stem = Path(original_file or "").stem.replace("_", " ")
    stem = re.sub(r"^\d+[.)_-]*\s*", "", stem)
    match = YEAR_RE.search(stem)
    if not match:
        return {}
    author_part = clean_author(stem[: match.start()])
    title_part = clean_title(stem[match.end():])
    if not title_part:
        return {}
    return {
        "title": title_part,
        "authors": author_part,
        "year": match.group(0),
        "source": "parsed_original_filename",
    }


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, fieldnames, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def embed_pdf_metadata(pdf_path, row, fallback):
    reader = PdfReader(str(pdf_path))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)

    existing = dict(reader.metadata or {})
    metadata = {
        key: str(value)
        for key, value in existing.items()
        if key.startswith("/")
    }
    metadata.update({
        "/Title": fallback["title"],
        "/Author": fallback["authors"],
        "/Subject": "BatLit pre-Zotero metadata fallback",
        "/Keywords": "; ".join(filter(None, [
            "BatLit",
            "metadata-fallback",
            row.get("decision", ""),
            row.get("doi", ""),
        ])),
        "/Creator": "BatLit pre-Zotero deduplication pipeline",
        "/BatLitMetadataFallbackSource": fallback["source"],
        "/BatLitYear": fallback["year"],
        "/BatLitOriginalFile": row.get("original_file", ""),
        "/BatLitDecision": row.get("decision", ""),
        "/DOI": row.get("doi", ""),
    })
    writer.add_metadata(metadata)

    temp_path = pdf_path.with_suffix(pdf_path.suffix + ".tmp")
    with temp_path.open("wb") as handle:
        writer.write(handle)
    temp_path.replace(pdf_path)


def main():
    parser = argparse.ArgumentParser(description="Apply filename/curated metadata fallbacks and embed them into routed PDFs.")
    parser.add_argument("--base", default=".", help="batlit-dedupe folder.")
    parser.add_argument("--run-folder", required=True, help="Folder under processed_runs.")
    parser.add_argument("--folder", default="new_literature", help="Routed folder inside the run folder.")
    parser.add_argument("--apply", action="store_true", help="Actually update CSV and PDF metadata.")
    args = parser.parse_args()

    base = Path(args.base).resolve()
    folder = base / "processed_runs" / args.run_folder / args.folder
    bibliography_path = folder / "bibliography.csv"
    rows = read_csv(bibliography_path)
    original_rows = [dict(row) for row in rows]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    report_rows = []
    updated_rows = []
    fieldnames = list(rows[0].keys()) if rows else []
    for row in rows:
        routed_filename = row.get("routed_filename", "")
        pdf_path = folder / routed_filename
        fallback = CURATED.get(routed_filename) or fallback_from_original_file(row.get("original_file", ""))
        should_update = bool(fallback) and (missing(row.get("title")) or missing(row.get("authors")))
        status = "would_update" if should_update and not args.apply else "updated" if should_update else "skipped"
        error = ""

        if should_update:
            row["title"] = row.get("title") or fallback["title"]
            row["authors"] = row.get("authors") or fallback["authors"]
            row["year"] = row.get("year") or fallback["year"]
            if args.apply:
                try:
                    embed_pdf_metadata(pdf_path, row, fallback)
                except Exception as exc:
                    status = "failed"
                    error = f"{type(exc).__name__}: {exc}"

        updated_rows.append(row)
        report_rows.append({
            "status": status,
            "routed_filename": routed_filename,
            "original_file": row.get("original_file", ""),
            "fallback_title": fallback.get("title", "") if fallback else "",
            "fallback_authors": fallback.get("authors", "") if fallback else "",
            "fallback_year": fallback.get("year", "") if fallback else "",
            "fallback_source": fallback.get("source", "") if fallback else "",
            "error": error,
        })

    report_fields = [
        "status",
        "routed_filename",
        "original_file",
        "fallback_title",
        "fallback_authors",
        "fallback_year",
        "fallback_source",
        "error",
    ]
    report_path = folder / "metadata_fallback_report.csv"
    timestamped_report_path = folder / f"{stamp}_metadata_fallback_report.csv"
    write_csv(report_path, report_fields, report_rows)
    write_csv(timestamped_report_path, report_fields, report_rows)

    if args.apply and rows:
        backup_path = folder / f"{stamp}_bibliography_before_metadata_fallback.csv"
        write_csv(backup_path, fieldnames, original_rows)
        write_csv(bibliography_path, fieldnames, updated_rows)

    counts = {}
    for row in report_rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    for key, value in sorted(counts.items()):
        print(f"{key}: {value}")
    print(report_path)
    print(timestamped_report_path)


if __name__ == "__main__":
    main()
