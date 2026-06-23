#!/usr/bin/env python3
import argparse
import csv
import re
from collections import Counter
from datetime import datetime
from pathlib import Path


def slugify(value):
    value = re.sub(r"[^A-Za-z0-9]+", "_", value.strip())
    return re.sub(r"_+", "_", value).strip("_") or "collection"


def import_recommendation(row):
    decision = row.get("decision", "")
    if decision == "new_literature":
        return "candidate_for_zotero_import"
    if decision == "manual_review":
        return "manual_review_before_zotero"
    if decision == "non_bat_review":
        return "review_scope_before_import"
    if decision == "likely_duplicate":
        return "review_duplicate_match_before_import"
    if decision == "duplicate":
        return "do_not_import_known_duplicate"
    return "review"


def action_taken(row):
    status = row.get("status", "")
    folder = row.get("routed_folder", "")
    if status in {"copy", "move"}:
        return f"{status}_to_{folder}"
    if status == "skipped_duplicate":
        return "not_copied_duplicate"
    if status == "missing_source":
        return "source_missing"
    return status or "unknown"


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description="Create a collection-level action log from a BatLit routing report.")
    parser.add_argument("--base", default=".", help="batlit-dedupe folder.")
    parser.add_argument("--collection-name", required=True, help="Human-readable collection label.")
    parser.add_argument("--project-name", default="BatLit pre-Zotero deduplication pipeline")
    parser.add_argument("--run-folder", default="", help="processed_runs folder name used for this collection.")
    parser.add_argument("--routing-report", default="reports/routing_report.csv")
    parser.add_argument("--output-root", default="collection_tracking")
    args = parser.parse_args()

    base = Path(args.base).resolve()
    routing_path = base / args.routing_report
    rows = read_csv(routing_path)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    collection_slug = slugify(args.collection_name)
    output_dir = base / args.output_root / collection_slug

    out_rows = []
    for row in rows:
        duplicate_reference = (
            row.get("incoming_batch_primary_file")
            or row.get("batlit_title")
            or row.get("batlit_zotero_id")
            or row.get("batlit_doi")
            or ""
        )
        out_rows.append({
            "log_timestamp": stamp,
            "project_name": args.project_name,
            "collection_name": args.collection_name,
            "run_folder": args.run_folder,
            "original_file": row.get("file", ""),
            "action_taken": action_taken(row),
            "routed_folder": row.get("routed_folder", ""),
            "routed_filename": row.get("routed_filename", ""),
            "destination": row.get("destination", ""),
            "decision": row.get("decision", ""),
            "decision_reason": row.get("decision_reason", ""),
            "import_recommendation": import_recommendation(row),
            "batlit_match_scope": row.get("batlit_match_scope", ""),
            "duplicate_reference": duplicate_reference,
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
            "batlit_title": row.get("batlit_title", ""),
            "batlit_authors": row.get("batlit_authors", ""),
            "batlit_year_or_date": row.get("batlit_year_or_date", ""),
            "batlit_doi": row.get("batlit_doi", ""),
            "batlit_zotero_id": row.get("batlit_zotero_id", ""),
            "bat_relevance_status": row.get("bat_relevance_status", ""),
            "bat_relevance_reason": row.get("bat_relevance_reason", ""),
        })

    fields = [
        "log_timestamp",
        "project_name",
        "collection_name",
        "run_folder",
        "original_file",
        "action_taken",
        "routed_folder",
        "routed_filename",
        "destination",
        "decision",
        "decision_reason",
        "import_recommendation",
        "batlit_match_scope",
        "duplicate_reference",
        "incoming_batch_duplicate_status",
        "incoming_batch_duplicate_reason",
        "incoming_batch_primary_file",
        "incoming_batch_match_files",
        "title",
        "authors",
        "year",
        "doi",
        "md5",
        "sha256",
        "batlit_title",
        "batlit_authors",
        "batlit_year_or_date",
        "batlit_doi",
        "batlit_zotero_id",
        "bat_relevance_status",
        "bat_relevance_reason",
    ]

    action_log_path = output_dir / f"{stamp}_{collection_slug}_action_log.csv"
    write_csv(action_log_path, fields, out_rows)
    write_csv(output_dir / "latest_action_log.csv", fields, out_rows)

    summary_counts = Counter((row["decision"], row["routed_folder"], row["action_taken"]) for row in out_rows)
    summary_rows = [
        {
            "log_timestamp": stamp,
            "project_name": args.project_name,
            "collection_name": args.collection_name,
            "decision": decision,
            "routed_folder": folder,
            "action_taken": action,
            "count": count,
        }
        for (decision, folder, action), count in sorted(summary_counts.items())
    ]
    summary_fields = [
        "log_timestamp",
        "project_name",
        "collection_name",
        "decision",
        "routed_folder",
        "action_taken",
        "count",
    ]
    summary_path = output_dir / f"{stamp}_{collection_slug}_action_summary.csv"
    write_csv(summary_path, summary_fields, summary_rows)
    write_csv(output_dir / "latest_action_summary.csv", summary_fields, summary_rows)

    print(f"Action rows: {len(out_rows)}")
    print(f"Action log: {action_log_path}")
    print(f"Action summary: {summary_path}")


if __name__ == "__main__":
    main()
