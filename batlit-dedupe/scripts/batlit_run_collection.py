#!/usr/bin/env python3
import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def slugify(value):
    value = re.sub(r"[^A-Za-z0-9]+", "_", value.strip())
    return re.sub(r"_+", "_", value).strip("_") or "collection"


def run_step(label, cmd, dry_run=False):
    printable = " ".join(str(part) for part in cmd)
    print("")
    print(f"== {label} ==")
    print(printable)
    if dry_run:
        return
    subprocess.run(cmd, check=True)


def main():
    parser = argparse.ArgumentParser(description="Run the BatLit pre-Zotero pipeline for one incoming collection.")
    parser.add_argument("--base", default=".", help="batlit-dedupe folder; defaults to current directory.")
    parser.add_argument("--collection-name", required=True, help='Collection label, e.g. "Bates 2026".')
    parser.add_argument("--run-folder", default="", help="Optional processed_runs folder name.")
    parser.add_argument("--skip-snapshot", action="store_true", help="Skip incoming collection manifest/diff.")
    parser.add_argument("--skip-fingerprint", action="store_true", help="Skip rebuilding literature_fingerprint_index.csv.")
    parser.add_argument("--skip-ris", action="store_true", help="Skip RIS staging export.")
    parser.add_argument("--skip-embed-metadata", action="store_true", help="Skip embedding metadata into routed PDF copies.")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without running them.")
    args = parser.parse_args()

    base = Path(args.base).resolve()
    scripts = base / "scripts"
    collection_slug = slugify(args.collection_name)
    run_folder = args.run_folder or f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{collection_slug}"

    python = sys.executable

    if not args.skip_snapshot:
        run_step(
            "Snapshot incoming collection",
            [python, str(scripts / "batlit_collection_diff.py"), "--base", str(base), "--label", args.collection_name],
            dry_run=args.dry_run,
        )

    if not args.skip_fingerprint:
        run_step(
            "Build literature fingerprint index",
            [python, str(scripts / "batlit_build_fingerprint_index.py"), "--base", str(base)],
            dry_run=args.dry_run,
        )

    run_step(
        "Run dedupe screening",
        [python, str(scripts / "batlit_dedupe_workflow.py"), "--base", str(base)],
        dry_run=args.dry_run,
    )

    run_step(
        "Route PDFs into timestamped processed run",
        [
            python,
            str(scripts / "batlit_route_pdfs.py"),
            "--base",
            str(base),
            "--copy",
            "--include-duplicates",
            "--rename-citation",
            "--run-folder",
            run_folder,
        ],
        dry_run=args.dry_run,
    )

    run_step(
        "Create duplicate-omitted review sets",
        [
            python,
            str(scripts / "batlit_create_deduplicated_review_sets.py"),
            "--base",
            str(base),
            "--run-folder",
            run_folder,
            "--collection-name",
            args.collection_name,
        ],
        dry_run=args.dry_run,
    )

    run_step(
        "Create collection action log",
        [
            python,
            str(scripts / "batlit_collection_action_log.py"),
            "--base",
            str(base),
            "--collection-name",
            args.collection_name,
            "--run-folder",
            run_folder,
        ],
        dry_run=args.dry_run,
    )

    if not args.skip_embed_metadata:
        run_step(
            "Embed metadata into routed PDF copies",
            [
                python,
                str(scripts / "batlit_embed_pdf_metadata.py"),
                "--base",
                str(base),
                "--run-folder",
                run_folder,
                "--apply",
            ],
            dry_run=args.dry_run,
        )

    if not args.skip_ris:
        run_step(
            "Create Zotero RIS staging file",
            [python, str(scripts / "batlit_make_zotero_ris.py"), "--base", str(base)],
            dry_run=args.dry_run,
        )

    print("")
    print("Pipeline complete.")
    print(f"Run folder: {base / 'processed_runs' / run_folder}")
    print(f"Action log: {base / 'collection_tracking' / collection_slug / 'latest_action_log.csv'}")


if __name__ == "__main__":
    main()
