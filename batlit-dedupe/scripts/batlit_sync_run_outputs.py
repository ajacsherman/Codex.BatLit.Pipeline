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


def copy_file(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def copy_pdfs(source, destination):
    destination.mkdir(parents=True, exist_ok=True)
    copied = 0
    for pdf in sorted(source.glob("*.pdf")):
        copy_file(pdf, destination / pdf.name)
        copied += 1
    return copied


def copy_if_exists(source, destination):
    if source.exists():
        copy_file(source, destination)
        return True
    return False


def read_csv(path):
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


def manifest_from_bibliography(rows, source_folder, destination_folder, collection_name, run_folder, stamp):
    out = []
    for row in rows:
        filename = row.get("routed_filename") or row.get("filename") or ""
        if not filename:
            continue
        out.append({
            "created": stamp,
            "collection_name": collection_name,
            "run_folder": run_folder,
            "deduplicated_folder": destination_folder,
            "source_folder": source_folder,
            "filename": filename,
            "decision": row.get("decision", ""),
            "decision_reason": row.get("decision_reason", ""),
            "batlit_match_scope": row.get("batlit_match_scope", ""),
            "incoming_batch_duplicate_status": row.get("incoming_batch_duplicate_status", ""),
            "incoming_batch_duplicate_reason": row.get("incoming_batch_duplicate_reason", ""),
            "incoming_batch_primary_file": row.get("incoming_batch_primary_file", ""),
            "incoming_batch_match_files": row.get("incoming_batch_match_files", ""),
            "title": row.get("title", ""),
            "authors": row.get("authors", ""),
            "year": row.get("year", ""),
            "doi": row.get("doi", ""),
            "md5": row.get("md5", ""),
            "sha256": row.get("sha256", ""),
        })
    return out


def main():
    parser = argparse.ArgumentParser(description="Synchronize derived run folders after metadata improvements.")
    parser.add_argument("--base", default=".", help="batlit-dedupe folder.")
    parser.add_argument("--run-folder", required=True, help="Folder under processed_runs.")
    parser.add_argument("--collection-name", default="", help="Collection label.")
    parser.add_argument("--make-upload-folder", action="store_true", help="Create a fresh timestamped upload-ready folder from new_literature.")
    args = parser.parse_args()

    base = Path(args.base).resolve()
    run_dir = base / "processed_runs" / args.run_folder
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    sync_dir = run_dir / "sync_runs" / f"{stamp}_sync_run_outputs"
    sync_dir.mkdir(parents=True, exist_ok=True)

    sync_rows = []
    combined_manifest = []
    manifest_fields = [
        "created", "collection_name", "run_folder", "deduplicated_folder", "source_folder",
        "filename", "decision", "decision_reason", "batlit_match_scope",
        "incoming_batch_duplicate_status", "incoming_batch_duplicate_reason",
        "incoming_batch_primary_file", "incoming_batch_match_files", "title", "authors",
        "year", "doi", "md5", "sha256",
    ]

    for source_name, destination_name in FOLDER_PAIRS:
        source = run_dir / source_name
        destination = run_dir / destination_name
        if not source.exists():
            sync_rows.append({"item": destination_name, "status": "skipped_missing_source", "details": str(source)})
            continue

        copied_pdfs = copy_pdfs(source, destination)
        sync_rows.append({"item": destination_name, "status": "pdfs_synced", "details": str(copied_pdfs)})

        for filename in ["bibliography.csv", "bibliography.xlsx"]:
            copied = copy_if_exists(source / filename, destination / filename)
            sync_rows.append({"item": f"{destination_name}/{filename}", "status": "copied" if copied else "missing", "details": str(source / filename)})
            if copied and filename == "bibliography.csv":
                copy_file(destination / filename, destination / f"{stamp}_bibliography.csv")

        bib_rows = read_csv(destination / "bibliography.csv")
        manifest_rows = manifest_from_bibliography(
            bib_rows, source_name, destination_name, args.collection_name, args.run_folder, stamp
        )
        combined_manifest.extend(manifest_rows)
        if manifest_rows:
            write_csv(destination / "deduplicated_review_manifest.csv", manifest_fields, manifest_rows)
            write_csv(destination / f"{stamp}_deduplicated_review_manifest.csv", manifest_fields, manifest_rows)
            sync_rows.append({"item": f"{destination_name}/deduplicated_review_manifest.csv", "status": "written", "details": str(len(manifest_rows))})

    if combined_manifest:
        write_csv(run_dir / "deduplicated_review_manifest.csv", manifest_fields, combined_manifest)
        write_csv(run_dir / f"{stamp}_deduplicated_review_manifest.csv", manifest_fields, combined_manifest)
        sync_rows.append({"item": "run/deduplicated_review_manifest.csv", "status": "written", "details": str(len(combined_manifest))})

    if args.make_upload_folder:
        source = run_dir / "new_literature"
        upload = run_dir / f"{stamp}_zotero_upload"
        copied = copy_pdfs(source, upload)
        for filename in ["bibliography.csv", "metadata_fallback_report.csv"]:
            copy_if_exists(source / filename, upload / filename)
        sync_rows.append({"item": upload.name, "status": "upload_folder_created", "details": str(copied)})

    sync_fields = ["item", "status", "details"]
    write_csv(sync_dir / "sync_report.csv", sync_fields, sync_rows)
    (sync_dir / "README.txt").write_text(
        "\n".join([
            f"Sync created: {stamp}",
            f"Run folder: {args.run_folder}",
            "Purpose: refresh derived folders and manifests after metadata improvements.",
            "The source routing decisions were not changed by this sync.",
        ]) + "\n",
        encoding="utf-8",
    )

    for row in sync_rows:
        print(f"{row['status']}: {row['item']} {row['details']}")
    print(sync_dir)


if __name__ == "__main__":
    main()
