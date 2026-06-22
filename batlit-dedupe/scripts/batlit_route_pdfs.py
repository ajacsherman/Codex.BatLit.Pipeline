#!/usr/bin/env python3
import argparse
import csv
import shutil
from collections import Counter
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


def main():
    parser = argparse.ArgumentParser(description="Route incoming PDFs into processed review folders.")
    parser.add_argument("--base", default=".", help="batlit-dedupe folder; defaults to current directory")
    parser.add_argument("--report", default="reports/dedupe_report.csv", help="dedupe CSV relative to base")
    parser.add_argument("--copy", action="store_true", help="copy files into processed folders")
    parser.add_argument("--move", action="store_true", help="move files into processed folders")
    parser.add_argument("--include-duplicates", action="store_true", help="route duplicate files too")
    args = parser.parse_args()

    if args.copy and args.move:
        raise SystemExit("Choose only one: --copy or --move")

    base = Path(args.base).resolve()
    incoming_dir = base / "incoming"
    processed_dir = base / "processed"
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
                destination_path = unique_destination(folder, row["file"])
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
                "md5": row.get("md5", ""),
                "incoming_title": row.get("incoming_title", ""),
                "front_matter_dois": row.get("front_matter_dois", ""),
                "batlit_title": row.get("batlit_title", ""),
            })

    routing_report_path.parent.mkdir(parents=True, exist_ok=True)
    with routing_report_path.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = [
            "action",
            "status",
            "decision",
            "decision_reason",
            "file",
            "routed_folder",
            "destination",
            "md5",
            "incoming_title",
            "front_matter_dois",
            "batlit_title",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows_out)

    print(f"Routing action: {action}")
    print(f"Routing report: {routing_report_path}")
    for key, value in sorted(counts.items()):
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
