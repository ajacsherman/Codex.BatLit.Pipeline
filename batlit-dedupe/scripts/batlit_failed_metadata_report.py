#!/usr/bin/env python3
import argparse
import csv
import re
from datetime import datetime
from pathlib import Path


FIELDNAMES = [
    "review_reason",
    "file",
    "decision",
    "decision_reason",
    "incoming_title",
    "incoming_authors",
    "incoming_year_guess",
    "front_matter_dois",
    "text_error",
    "md5",
    "sha256",
]


def has_alpha(value):
    return bool(re.search(r"[A-Za-z]", value or ""))


def bad_title(value):
    value = (value or "").strip()
    if not value:
        return True
    if len(value) < 12:
        return True
    if not has_alpha(value):
        return True
    if value.count("~") >= 1 or value.count("_") >= 3:
        return True
    return False


def bad_authors(value):
    value = (value or "").strip()
    if not value:
        return True
    if value.lower() in {"unknown", "none", "n/a"}:
        return True
    if len(value) < 3:
        return True
    if value.count("~") >= 1:
        return True
    if not has_alpha(value):
        return True
    return False


def bad_year(value):
    return not bool(re.search(r"\b(18|19|20)\d{2}\b", value or ""))


def review_reason(row):
    reasons = []
    if row.get("text_error"):
        reasons.append("text_extraction_failed")
    if bad_title(row.get("incoming_title")):
        reasons.append("missing_or_suspicious_title")
    if bad_authors(row.get("incoming_authors")):
        reasons.append("missing_or_suspicious_authors")
    if bad_year(row.get("incoming_year_guess")):
        reasons.append("missing_year")
    return " | ".join(reasons)


def main():
    parser = argparse.ArgumentParser(description="Create a CSV of PDFs needing OCR or manual citation search.")
    parser.add_argument("--base", default=".", help="batlit-dedupe folder; defaults to current directory")
    parser.add_argument("--report", default="reports/dedupe_report.csv", help="dedupe CSV relative to base")
    args = parser.parse_args()

    base = Path(args.base).resolve()
    report_path = base / args.report
    failed_dir = base / "processed" / "failed_processing"
    failed_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stable_path = failed_dir / "metadata_failed_processing.csv"
    timestamped_path = failed_dir / f"{stamp}_metadata_failed_processing.csv"

    rows = []
    with report_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            reason = review_reason(row)
            if reason:
                rows.append({
                    "review_reason": reason,
                    "file": row.get("file", ""),
                    "decision": row.get("decision", ""),
                    "decision_reason": row.get("decision_reason", ""),
                    "incoming_title": row.get("incoming_title", ""),
                    "incoming_authors": row.get("incoming_authors", ""),
                    "incoming_year_guess": row.get("incoming_year_guess", ""),
                    "front_matter_dois": row.get("front_matter_dois", ""),
                    "text_error": row.get("text_error", ""),
                    "md5": row.get("md5", ""),
                    "sha256": row.get("sha256", ""),
                })

    for path in [stable_path, timestamped_path]:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows)

    print(f"Metadata/OCR review rows: {len(rows)}")
    print(stable_path)
    print(timestamped_path)


if __name__ == "__main__":
    main()
