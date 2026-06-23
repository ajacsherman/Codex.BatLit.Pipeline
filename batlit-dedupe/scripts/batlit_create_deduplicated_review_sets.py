#!/usr/bin/env python3
import argparse
import csv
import re
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


def normalize_doi(value):
    value = (value or "").strip().lower()
    value = re.sub(r"^https?://(dx\.)?doi\.org/", "", value)
    value = re.sub(r"^doi:\s*", "", value)
    return value.rstrip(").,;]")


def normalize_text(value):
    value = (value or "").casefold()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def load_batlit_reference_links(base):
    refs_path = base / "index" / "refs.csv"
    by_zotero_id = {}
    by_doi = {}
    by_title = {}
    if not refs_path.exists():
        return by_zotero_id, by_doi, by_title

    with refs_path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            link_row = {
                "possible_duplicate_zenodo_link": row.get("alternativeDoiUrl", ""),
                "possible_duplicate_zenodo_doi": row.get("alternativeDoi", ""),
                "possible_duplicate_zotero_link": row.get("id", ""),
                "possible_duplicate_batlit_title": row.get("title", ""),
                "possible_duplicate_batlit_doi": row.get("doi", ""),
                "possible_duplicate_batlit_attachment_id": row.get("attachmentId", ""),
            }
            zotero_id = row.get("id", "")
            if zotero_id:
                by_zotero_id[zotero_id] = link_row
            for doi_field in ("doi", "alternativeDoi"):
                doi = normalize_doi(row.get(doi_field))
                if doi:
                    by_doi[doi] = link_row
            title = normalize_text(row.get("title"))
            if title:
                by_title.setdefault(title, link_row)
    return by_zotero_id, by_doi, by_title


def duplicate_links(source_row, by_zotero_id, by_doi, by_title):
    if source_row.get("batlit_match_scope") != "batlit_corpus":
        return {
            "possible_duplicate_zenodo_link": "",
            "possible_duplicate_zenodo_doi": "",
            "possible_duplicate_zotero_link": "",
            "possible_duplicate_batlit_title": "",
            "possible_duplicate_batlit_doi": "",
            "possible_duplicate_batlit_attachment_id": "",
        }

    zotero_id = source_row.get("batlit_zotero_id", "")
    if zotero_id and zotero_id in by_zotero_id:
        return by_zotero_id[zotero_id]

    for doi_field in ("batlit_doi", "doi"):
        doi = normalize_doi(source_row.get(doi_field))
        if doi and doi in by_doi:
            return by_doi[doi]

    title = normalize_text(source_row.get("batlit_title") or source_row.get("title"))
    if title and title in by_title:
        return by_title[title]

    return {
        "possible_duplicate_zenodo_link": "",
        "possible_duplicate_zenodo_doi": "",
        "possible_duplicate_zotero_link": source_row.get("batlit_zotero_id", ""),
        "possible_duplicate_batlit_title": source_row.get("batlit_title", ""),
        "possible_duplicate_batlit_doi": source_row.get("batlit_doi", ""),
        "possible_duplicate_batlit_attachment_id": source_row.get("batlit_attachment_id", ""),
    }


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
    by_zotero_id, by_doi, by_title = load_batlit_reference_links(base)

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
            link_fields = duplicate_links(source_row, by_zotero_id, by_doi, by_title)
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
                "incoming_batch_duplicate_reason": source_row.get("incoming_batch_duplicate_reason", ""),
                "incoming_batch_primary_file": source_row.get("incoming_batch_primary_file", ""),
                "incoming_batch_match_files": source_row.get("incoming_batch_match_files", ""),
                **link_fields,
                "title": source_row.get("title", ""),
                "authors": source_row.get("authors", ""),
                "year": source_row.get("year", ""),
                "doi": source_row.get("doi", ""),
                "md5": source_row.get("md5", ""),
                "sha256": source_row.get("sha256", ""),
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
            "incoming_batch_duplicate_reason",
            "incoming_batch_primary_file",
            "incoming_batch_match_files",
            "possible_duplicate_zenodo_link",
            "possible_duplicate_zenodo_doi",
            "possible_duplicate_zotero_link",
            "possible_duplicate_batlit_title",
            "possible_duplicate_batlit_doi",
            "possible_duplicate_batlit_attachment_id",
            "title",
            "authors",
            "year",
            "doi",
            "md5",
            "sha256",
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
