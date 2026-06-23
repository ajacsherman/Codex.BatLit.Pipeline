#!/usr/bin/env python3
import argparse
import csv
import shutil
from datetime import datetime
from pathlib import Path


FOLDER_PAIRS = [
    ("new_literature", "Deduplicated_new_literature"),
    ("likely_duplicates", "Deduplicated_likely_duplicates"),
]


def copy_folder_files(source, destination):
    destination.mkdir(parents=True, exist_ok=True)
    copied = []
    for path in sorted(source.iterdir()):
        if not path.is_file():
            continue
        target = destination / path.name
        shutil.copy2(path, target)
        copied.append(target)
    return copied


def read_bibliography(folder):
    path = folder / "bibliography.csv"
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description="Create duplicate-omitted review sets for a routed BatLit collection.")
    parser.add_argument("--base", default=".", help="batlit-dedupe folder.")
    parser.add_argument("--run-folder", required=True, help="Folder name under processed_runs.")
    parser.add_argument("--collection-name", default="", help="Human-readable collection label.")
    args = parser.parse_args()

    base = Path(args.base).resolve()
    run_dir = base / "processed_runs" / args.run_folder
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    all_manifest_rows = []

    for source_name, destination_name in FOLDER_PAIRS:
        source = run_dir / source_name
        destination = run_dir / destination_name
        if not source.exists():
            continue

        copied = copy_folder_files(source, destination)
        bibliography_rows = read_bibliography(source)
        by_routed_filename = {
            row.get("routed_filename", ""): row
            for row in bibliography_rows
        }
        manifest_rows = []
        for copied_path in copied:
            if copied_path.suffix.lower() != ".pdf":
                continue
            source_row = by_routed_filename.get(copied_path.name, {})
            row = {
                "created": stamp,
                "collection_name": args.collection_name,
                "run_folder": args.run_folder,
                "deduplicated_folder": destination_name,
                "source_folder": source_name,
                "filename": copied_path.name,
                "decision": source_row.get("decision", ""),
                "decision_reason": source_row.get("decision_reason", ""),
                "batlit_match_scope": source_row.get("batlit_match_scope", ""),
                "incoming_batch_duplicate_status": source_row.get("incoming_batch_duplicate_status", ""),
                "incoming_batch_primary_file": source_row.get("incoming_batch_primary_file", ""),
                "title": source_row.get("title", ""),
                "authors": source_row.get("authors", ""),
                "year": source_row.get("year", ""),
                "doi": source_row.get("doi", ""),
                "md5": source_row.get("md5", ""),
            }
            manifest_rows.append(row)
            all_manifest_rows.append(row)

        fields = [
            "created",
            "collection_name",
            "run_folder",
            "deduplicated_folder",
            "source_folder",
            "filename",
            "decision",
            "decision_reason",
            "batlit_match_scope",
            "incoming_batch_duplicate_status",
            "incoming_batch_primary_file",
            "title",
            "authors",
            "year",
            "doi",
            "md5",
        ]
        write_csv(destination / "deduplicated_review_manifest.csv", fields, manifest_rows)
        write_csv(destination / f"{stamp}_deduplicated_review_manifest.csv", fields, manifest_rows)
        print(f"{destination_name}: {len([p for p in copied if p.suffix.lower() == '.pdf'])} PDFs")

    if all_manifest_rows:
        fields = list(all_manifest_rows[0].keys())
        write_csv(run_dir / "deduplicated_review_manifest.csv", fields, all_manifest_rows)
        write_csv(run_dir / f"{stamp}_deduplicated_review_manifest.csv", fields, all_manifest_rows)
        print(f"Combined manifest: {len(all_manifest_rows)} PDFs")


if __name__ == "__main__":
    main()
