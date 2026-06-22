#!/usr/bin/env python3
import argparse
import csv
import re
from pathlib import Path


def escape_ris(value):
    return re.sub(r"\s+", " ", (value or "").strip())


def split_authors(value):
    value = value or ""
    if "|" in value:
        parts = value.split("|")
    elif ";" in value:
        parts = value.split(";")
    else:
        parts = value.split(",")
    return [escape_ris(part) for part in parts if escape_ris(part)]


def wsl_path_to_file_uri(path):
    text = str(path)
    if text.startswith("/mnt/") and len(text) > 6:
        drive = text[5].upper()
        rest = text[6:]
        return "file:///" + drive + ":" + rest.replace(" ", "%20")
    return Path(path).resolve().as_uri()


def write_line(handle, tag, value):
    value = escape_ris(value)
    if value:
        handle.write(f"{tag}  - {value}\n")


def main():
    parser = argparse.ArgumentParser(description="Create a Zotero-readable RIS staging file from dedupe_report.csv.")
    parser.add_argument("--base", default=".", help="batlit-dedupe folder; defaults to current directory")
    parser.add_argument("--decisions", default="new_literature", help="comma-separated decisions to include")
    args = parser.parse_args()

    base = Path(args.base).resolve()
    report_path = base / "reports" / "dedupe_report.csv"
    incoming_dir = base / "incoming"
    out_path = base / "reports" / "zotero_import_staging.ris"
    include_decisions = {item.strip() for item in args.decisions.split(",") if item.strip()}

    with report_path.open(newline="", encoding="utf-8") as source, out_path.open("w", encoding="utf-8") as out:
        rows = csv.DictReader(source)
        count = 0
        for row in rows:
            if row.get("decision") not in include_decisions:
                continue

            count += 1
            pdf_path = incoming_dir / row["file"]
            out.write("TY  - JOUR\n")
            write_line(out, "TI", row.get("incoming_title"))
            for author in split_authors(row.get("incoming_authors")):
                write_line(out, "AU", author)
            write_line(out, "PY", row.get("incoming_year_guess"))
            doi = (row.get("front_matter_dois") or "").split("|")[0].strip()
            write_line(out, "DO", doi)
            write_line(out, "KW", "batlit-prezotero")
            write_line(out, "KW", row.get("decision"))
            write_line(out, "N1", f"pre_zotero_decision={row.get('decision')}; reason={row.get('decision_reason')}; md5={row.get('md5')}")
            write_line(out, "L1", wsl_path_to_file_uri(pdf_path))
            out.write("ER  - \n\n")

    print(f"{out_path} ({count} records)")


if __name__ == "__main__":
    main()
