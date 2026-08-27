#!/usr/bin/env python3
"""Rebuild strict Zotero-ready and metadata-investigation PDF sets for a run."""

from __future__ import annotations

import argparse
import csv
import shutil
from datetime import datetime
from pathlib import Path


READY_CONFIDENCE = {"curated", "verified", "high"}


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def archive_existing(path: Path, archive_root: Path, stamp: str) -> None:
    if not path.exists():
        return
    archive_root.mkdir(parents=True, exist_ok=True)
    target = archive_root / f"{path.name}_{stamp}"
    counter = 2
    while target.exists():
        target = archive_root / f"{path.name}_{stamp}_{counter}"
        counter += 1
    shutil.move(str(path), str(target))


def curated_lookup(report: Path) -> dict[str, dict[str, str]]:
    lookup: dict[str, dict[str, str]] = {}
    for row in read_csv(report):
        confidence = row.get("confidence", "").strip().lower()
        status = row.get("status", "").strip().lower()
        enhanced = row.get("enhanced_filename", "").strip()
        routed = row.get("routed_filename", "").strip()
        if enhanced and confidence in READY_CONFIDENCE and "embedded" in status:
            lookup[enhanced] = row
            if routed:
                lookup[routed] = row
    return lookup


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, help="batlit-dedupe root")
    parser.add_argument("--run-folder", required=True, help="processed run folder name")
    parser.add_argument("--source-folder", default=None, help="PDF source folder inside the run folder")
    parser.add_argument("--curated-report", default=None, help="CSV listing curated embedded metadata")
    parser.add_argument("--queue-csv", default=None, help="Latest metadata investigation queue CSV to copy into needs folder")
    args = parser.parse_args()

    base = Path(args.base)
    run = args.run_folder
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_root = base / "processed_runs" / run
    source_name = args.source_folder or f"{run}_enhanced_zotero_upload"
    source = run_root / source_name
    report = Path(args.curated_report) if args.curated_report else run_root / f"{run}_enhanced_metadata_report.csv"
    enrichment = base / "metadata_enrichment" / run
    ready_dir = enrichment / "Zotero_Ready_PDFs"
    needs_dir = enrichment / "Needs_Metadata_Investigation_PDFs"
    archive_root = base / "archive" / f"{run}_ready_set_rebuilds"

    if not source.exists():
        raise SystemExit(f"Missing source folder: {source}")

    archive_existing(ready_dir, archive_root, stamp)
    archive_existing(needs_dir, archive_root, stamp)
    ready_dir.mkdir(parents=True, exist_ok=True)
    needs_dir.mkdir(parents=True, exist_ok=True)

    curated = curated_lookup(report)
    ready_rows: list[dict[str, str]] = []
    needs_rows: list[dict[str, str]] = []

    for pdf in sorted(source.glob("*.pdf"), key=lambda path: path.name.lower()):
        metadata = curated.get(pdf.name)
        if metadata:
            output_name = metadata.get("enhanced_filename", "").strip() or pdf.name
            shutil.copy2(pdf, ready_dir / output_name)
            ready_rows.append({
                "filename": output_name,
                "source_filename": pdf.name,
                "decision": "zotero_ready",
                "reason": "curated metadata embedded",
                "title": metadata.get("title", ""),
                "authors": metadata.get("authors", ""),
                "year": metadata.get("year", ""),
                "doi": metadata.get("doi", ""),
                "source": metadata.get("source", ""),
            })
        else:
            shutil.copy2(pdf, needs_dir / pdf.name)
            needs_rows.append({
                "filename": pdf.name,
                "decision": "needs_metadata_investigation",
                "reason": "not present in curated embedded metadata report",
            })

    write_csv(ready_dir / "zotero_ready_manifest.csv", ready_rows)
    write_csv(needs_dir / "needs_metadata_investigation_manifest.csv", needs_rows)

    if args.queue_csv:
        queue = Path(args.queue_csv)
        if queue.exists():
            shutil.copy2(queue, needs_dir / queue.name)

    readme = enrichment / f"README_{run}_WORKSPACE.txt"
    readme.write_text(
        "\n".join([
            f"{run} metadata enrichment workspace",
            "",
            "Zotero_Ready_PDFs contains only PDFs with curated, embedded metadata.",
            "Needs_Metadata_Investigation_PDFs contains PDFs whose metadata still needs confirmation before Zotero import.",
            "",
            f"Source folder: {source}",
            f"Curated metadata report: {report}",
            f"Ready PDFs: {len(ready_rows)}",
            f"Needs investigation PDFs: {len(needs_rows)}",
            f"Rebuilt: {stamp}",
            "",
        ]),
        encoding="utf-8",
    )

    print(f"Ready PDFs: {len(ready_rows)} -> {ready_dir}")
    print(f"Needs investigation PDFs: {len(needs_rows)} -> {needs_dir}")
    print(f"Archived previous generated folders under: {archive_root}")


if __name__ == "__main__":
    main()
