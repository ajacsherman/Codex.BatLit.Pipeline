#!/usr/bin/env python3
import argparse
import csv
import re
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path


DECISION_TO_FOLDER = {
    "duplicate": "duplicates",
    "likely_duplicate": "likely_duplicates",
    "new_literature": "new_literature",
    "manual_review": "manual_review",
    "non_bat_review": "non_bat_review",
    "failed_processing": "failed_processing",
}


def unique_destination(folder, filename):
    destination = folder / filename
    if not destination.exists():
        return destination

    stem = destination.stem
    suffix = destination.suffix
    counter = 2
    while True:
        candidate = folder / f"{stem}__{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def clean_filename_part(value, fallback):
    value = (value or "").strip()
    value = re.sub(r'[<>:"/\\|?*]+', " ", value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    return value or fallback


def first_author_last_name(value):
    value = (value or "").strip()
    if not value:
        return "Unknown"

    if "|" in value:
        first = value.split("|", 1)[0]
    elif ";" in value:
        first = value.split(";", 1)[0]
    elif "," in value and not re.search(r"\b(and|&)\b", value, re.IGNORECASE):
        first = value.split(",", 1)[0]
    else:
        first = re.split(r"\s+(?:and|&)\s+", value, flags=re.IGNORECASE)[0]

    first = re.sub(r"\*", "", first)
    first = re.sub(r"\d+", "", first)
    first = re.sub(r"\b[A-Z]\.?\b", "", first).strip(" ,.")
    pieces = [piece for piece in re.split(r"\s+", first) if piece]
    if not pieces:
        return "Unknown"
    return clean_filename_part(pieces[-1].title(), "Unknown")


def filename_author_last_name(value):
    stem = Path(value or "").stem
    stem = re.sub(r"^\s*[A-Za-z]?\d+[A-Za-z]?[.)_-]*\s*", "", stem)
    stem = re.sub(r"^\s*[A-Z]\d+[A-Za-z]?[.)_-]*\s*", "", stem)
    stem = stem.replace("_", " ")
    stem = re.split(r"\b(?:18|19|20)\d{2}\b", stem, maxsplit=1)[0]
    stem = re.split(r"\bet\s+al\b", stem, maxsplit=1, flags=re.IGNORECASE)[0]
    stem = re.split(r"\s+(?:and|&)\s+", stem, maxsplit=1, flags=re.IGNORECASE)[0]
    stem = re.sub(r"[^A-Za-zÀ-ÖØ-öø-ÿ' -]+", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip(" -.,")
    if not stem:
        return "Unknown"

    generic = {
        "abstract", "acta", "african", "american", "annual", "article", "bat",
        "bats", "biological", "biology", "book", "chapter", "cover", "ecology",
        "journal", "mammal", "mammals", "map", "myanmar", "natural", "paper",
        "report", "reports", "science", "scientific", "supplement", "the", "web",
        "zoo", "zookeys", "zootaxa",
    }
    pieces = [piece for piece in stem.split() if piece]
    if not pieces or pieces[0].lower() in generic:
        return "Unknown"
    return clean_filename_part(pieces[-1].title() if len(pieces) == 1 else pieces[0].title(), "Unknown")


def publication_year(value):
    match = re.search(r"\b(18|19|20)\d{2}\b", value or "")
    return match.group(0) if match else "undated"


def citation_filename(row):
    if row.get("batlit_authors"):
        author = first_author_last_name(row.get("batlit_authors"))
    else:
        filename_author = filename_author_last_name(row.get("file"))
        extracted_author = first_author_last_name(row.get("incoming_authors"))
        author = filename_author if filename_author != "Unknown" else extracted_author

    date = row.get("batlit_year_or_date") or row.get("incoming_year_guess") or row.get("file") or ""
    year = publication_year(date)
    return f"{author}, {year}.pdf"


def main():
    parser = argparse.ArgumentParser(description="Route incoming PDFs into processed review folders.")
    parser.add_argument("--base", default=".", help="batlit-dedupe folder; defaults to current directory")
    parser.add_argument("--report", default="reports/dedupe_report.csv", help="dedupe CSV relative to base")
    parser.add_argument("--copy", action="store_true", help="copy files into processed folders")
    parser.add_argument("--move", action="store_true", help="move files into processed folders")
    parser.add_argument("--include-duplicates", action="store_true", help="route duplicate files too")
    parser.add_argument("--rename-citation", action="store_true", help='rename routed PDFs as "FirstAuthorLastName, Year.pdf"')
    parser.add_argument("--run-folder", default="", help="route into processed_runs/RUN_FOLDER instead of processed/")
    args = parser.parse_args()

    if args.copy and args.move:
        raise SystemExit("Choose only one: --copy or --move")

    base = Path(args.base).resolve()
    incoming_dir = base / "incoming"
    run_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    processed_dir = base / "processed_runs" / (args.run_folder or run_stamp) if args.run_folder is not None and args.run_folder != "" else base / "processed"
    report_path = base / args.report
    routing_report_path = base / "reports" / "routing_report.csv"

    if not report_path.exists():
        raise SystemExit(f"Missing report: {report_path}")

    action = "copy" if args.copy else "move" if args.move else "dry_run"
    rows_out = []
    counts = Counter()

    with report_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            decision = row.get("decision", "").strip()
            if decision == "duplicate" and not args.include_duplicates:
                routed_folder = "duplicates"
                status = "skipped_duplicate"
                destination = ""
            else:
                routed_folder = DECISION_TO_FOLDER.get(decision, "manual_review")
                source = incoming_dir / row["file"]
                folder = processed_dir / routed_folder
                filename = citation_filename(row) if args.rename_citation else row["file"]
                destination_path = unique_destination(folder, filename)
                destination = str(destination_path)

                if not source.exists():
                    status = "missing_source"
                elif action == "dry_run":
                    status = "would_route"
                else:
                    folder.mkdir(parents=True, exist_ok=True)
                    if action == "copy":
                        shutil.copy2(source, destination_path)
                    else:
                        shutil.move(source, destination_path)
                    status = action

            counts[f"{routed_folder}:{status}"] += 1
            rows_out.append({
                "action": action,
                "status": status,
                "decision": decision,
                "decision_reason": row.get("decision_reason", ""),
                "file": row.get("file", ""),
                "routed_folder": routed_folder,
                "destination": destination,
                "routed_filename": Path(destination).name if destination else "",
                "md5": row.get("md5", ""),
                "incoming_title": row.get("incoming_title", ""),
                "front_matter_dois": row.get("front_matter_dois", ""),
                "batlit_title": row.get("batlit_title", ""),
            })

    fieldnames = [
            "action",
            "status",
            "decision",
            "decision_reason",
            "file",
            "routed_folder",
            "destination",
            "routed_filename",
            "md5",
            "incoming_title",
            "front_matter_dois",
            "batlit_title",
    ]
    routing_report_path.parent.mkdir(parents=True, exist_ok=True)
    with routing_report_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows_out)

    stamp = run_stamp
    timestamped_report_path = routing_report_path.with_name(f"{stamp}_routing_report.csv")
    with timestamped_report_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows_out)

    print(f"Routing action: {action}")
    print(f"Routing report: {routing_report_path}")
    print(f"Timestamped routing report: {timestamped_report_path}")
    for key, value in sorted(counts.items()):
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
