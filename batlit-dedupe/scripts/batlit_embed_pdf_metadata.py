#!/usr/bin/env python3
import argparse
import csv
import tempfile
from datetime import datetime
from pathlib import Path

from pypdf import PdfReader, PdfWriter


FIELDNAMES = [
    "status",
    "folder",
    "pdf",
    "title",
    "authors",
    "year",
    "doi",
    "decision",
    "error",
]


def latest_run(processed_runs_dir):
    runs = sorted(path for path in processed_runs_dir.iterdir() if path.is_dir())
    if not runs:
        raise SystemExit(f"No processed run folders found in {processed_runs_dir}")
    return runs[-1]


def clean_value(value):
    return " ".join(str(value or "").split())


def metadata_from_row(row):
    title = clean_value(row.get("title"))
    authors = clean_value(row.get("authors"))
    year = clean_value(row.get("year"))
    doi = clean_value(row.get("doi"))
    decision = clean_value(row.get("decision"))
    reason = clean_value(row.get("decision_reason"))
    original_file = clean_value(row.get("original_file"))
    routed_filename = clean_value(row.get("routed_filename"))

    keywords = [
        "BatLit",
        "pre-Zotero",
        decision,
    ]
    if doi:
        keywords.append(f"doi:{doi}")
    keywords = [item for item in keywords if item]

    subject_parts = [
        f"Decision: {decision}" if decision else "",
        f"Reason: {reason}" if reason else "",
        f"DOI: {doi}" if doi else "",
        f"Original file: {original_file}" if original_file else "",
    ]

    metadata = {
        "/Title": title or Path(routed_filename).stem,
        "/Author": authors,
        "/Subject": "; ".join(part for part in subject_parts if part),
        "/Keywords": "; ".join(keywords),
        "/Creator": "BatLit Pre-Zotero Deduplication Pipeline",
        "/Producer": "BatLit Pre-Zotero Deduplication Pipeline via pypdf",
        "/CreationDate": "",
        "/ModDate": "",
        "/DOI": doi,
        "/BatLitDecision": decision,
        "/BatLitDecisionReason": reason,
        "/BatLitOriginalFile": original_file,
        "/BatLitYear": year,
        "/BatLitMD5": clean_value(row.get("md5")),
        "/BatLitZoteroItem": clean_value(row.get("batlit_zotero_id")),
    }
    return {key: value for key, value in metadata.items() if value}


def embed_metadata(pdf_path, metadata, apply):
    if not apply:
        return

    reader = PdfReader(str(pdf_path))
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)

    existing = dict(reader.metadata or {})
    existing.update(metadata)
    writer.add_metadata(existing)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf", dir=str(pdf_path.parent)) as tmp:
        tmp_path = Path(tmp.name)
        writer.write(tmp)

    tmp_path.replace(pdf_path)


def process_folder(folder, apply):
    bibliography = folder / "bibliography.csv"
    if not bibliography.exists():
        return []

    rows_out = []
    with bibliography.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            routed_filename = row.get("routed_filename", "")
            pdf_path = folder / routed_filename
            status = "would_embed"
            error = ""
            try:
                if not pdf_path.exists():
                    status = "missing_pdf"
                    raise FileNotFoundError(pdf_path)
                metadata = metadata_from_row(row)
                embed_metadata(pdf_path, metadata, apply=apply)
                status = "embedded" if apply else "would_embed"
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                if status != "missing_pdf":
                    status = "failed"

            rows_out.append({
                "status": status,
                "folder": folder.name,
                "pdf": routed_filename,
                "title": row.get("title", ""),
                "authors": row.get("authors", ""),
                "year": row.get("year", ""),
                "doi": row.get("doi", ""),
                "decision": row.get("decision", ""),
                "error": error,
            })
    return rows_out


def write_report(run_dir, rows, stamp):
    paths = [
        run_dir / "metadata_embedding_report.csv",
        run_dir / f"{stamp}_metadata_embedding_report.csv",
    ]
    for path in paths:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows)
    return paths


def main():
    parser = argparse.ArgumentParser(description="Embed bibliography metadata into routed PDF copies.")
    parser.add_argument("--base", default=".", help="batlit-dedupe folder; defaults to current directory")
    parser.add_argument("--run-folder", default="", help="processed_runs folder name; defaults to latest")
    parser.add_argument("--apply", action="store_true", help="write metadata into PDFs; otherwise dry-run only")
    args = parser.parse_args()

    base = Path(args.base).resolve()
    processed_runs_dir = base / "processed_runs"
    run_dir = processed_runs_dir / args.run_folder if args.run_folder else latest_run(processed_runs_dir)
    if not run_dir.exists():
        raise SystemExit(f"Run folder not found: {run_dir}")

    all_rows = []
    for folder in sorted(path for path in run_dir.iterdir() if path.is_dir()):
        all_rows.extend(process_folder(folder, apply=args.apply))

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    reports = write_report(run_dir, all_rows, stamp)

    counts = {}
    for row in all_rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1

    print(f"Run folder: {run_dir}")
    print(f"Mode: {'apply' if args.apply else 'dry-run'}")
    for key in sorted(counts):
        print(f"{key}: {counts[key]}")
    for report in reports:
        print(report)


if __name__ == "__main__":
    main()
