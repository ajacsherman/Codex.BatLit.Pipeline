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


def unique_dir(path):
    if not path.exists():
        return path
    for index in range(2, 100):
        candidate = path.with_name(f"{path.name}_{index:02d}")
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"Could not find an unused folder name for {path}")


def main():
    parser = argparse.ArgumentParser(description="Run the BatLit pre-Zotero pipeline for one incoming collection.")
    parser.add_argument("--base", default=".", help="batlit-dedupe folder; defaults to current directory.")
    parser.add_argument("--collection-name", required=True, help='Collection label, e.g. "Bates 2026".')
    parser.add_argument(
        "--incoming-folder",
        default="",
        help="PDF source folder relative to base; defaults to amnh_incoming for AMNH and incoming otherwise.",
    )
    parser.add_argument("--run-folder", default="", help="Optional processed_runs folder name.")
    parser.add_argument("--run-date", default="", help="Optional YYYYMMDD date stamp; defaults to today.")
    parser.add_argument(
        "--front-matter-pages",
        type=int,
        default=10,
        help="Number of leading PDF pages to scan for citation metadata and DOI candidates.",
    )
    parser.add_argument(
        "--excerpt-mode",
        action="store_true",
        help="Treat shared source-work metadata as possible distinct excerpts rather than duplicate evidence.",
    )
    parser.add_argument(
        "--time-stamps",
        action="store_true",
        help="Use YYYYMMDD_HHMMSS instead of date-only YYYYMMDD for generated collection files.",
    )
    parser.add_argument("--skip-snapshot", action="store_true", help="Skip incoming collection manifest/diff.")
    parser.add_argument("--skip-fingerprint", action="store_true", help="Skip rebuilding literature_fingerprint_index.csv.")
    parser.add_argument("--skip-ris", action="store_true", help="Skip RIS staging export.")
    parser.add_argument("--skip-embed-metadata", action="store_true", help="Skip embedding metadata into routed PDF copies.")
    parser.add_argument("--skip-metadata-fallbacks", action="store_true", help="Skip curated metadata fallback pass for new_literature.")
    parser.add_argument("--skip-sync", action="store_true", help="Skip synchronization of deduplicated review and Zotero upload folders.")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without running them.")
    args = parser.parse_args()

    base = Path(args.base).resolve()
    scripts = base / "scripts"
    collection_slug = slugify(args.collection_name)
    excerpt_mode = args.excerpt_mode or collection_slug.upper().startswith("AMNH")
    incoming_folder = args.incoming_folder or ("amnh_incoming" if excerpt_mode else "incoming")
    stamp_format = "%Y%m%d_%H%M%S" if args.time_stamps else "%Y%m%d"
    run_date = args.run_date or datetime.now().strftime(stamp_format)
    run_folder = args.run_folder or unique_dir(base / "processed_runs" / f"{collection_slug}_{run_date}").name

    python = sys.executable

    if not args.skip_snapshot:
        run_step(
            "Snapshot incoming collection",
            [
                python,
                str(scripts / "batlit_collection_diff.py"),
                "--base",
                str(base),
                "--incoming-folder",
                incoming_folder,
                "--label",
                args.collection_name,
            ] + ([] if args.time_stamps else ["--date-only"]) + (["--no-previous"] if excerpt_mode else []),
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
        [
            python,
            str(scripts / "batlit_dedupe_workflow.py"),
            "--base",
            str(base),
            "--incoming-folder",
            incoming_folder,
            "--front-matter-pages",
            str(args.front_matter_pages),
        ] + (["--excerpt-mode"] if excerpt_mode else []),
        dry_run=args.dry_run,
    )

    run_step(
        "Route PDFs into timestamped processed run",
        [
            python,
            str(scripts / "batlit_route_pdfs.py"),
            "--base",
            str(base),
            "--incoming-folder",
            incoming_folder,
            "--copy",
            "--include-duplicates",
            "--rename-citation",
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

    if not args.skip_metadata_fallbacks:
        run_step(
            "Apply curated metadata fallbacks",
            [
                python,
                str(scripts / "batlit_apply_metadata_fallbacks.py"),
                "--base",
                str(base),
                "--run-folder",
                run_folder,
                "--folder",
                "new_literature",
                "--apply",
            ],
            dry_run=args.dry_run,
        )

    if not args.skip_sync:
        run_step(
            "Synchronize metadata-improved review and upload folders",
            [
                python,
                str(scripts / "batlit_sync_run_outputs.py"),
                "--base",
                str(base),
                "--run-folder",
                run_folder,
                "--collection-name",
                args.collection_name,
                "--make-upload-folder",
            ] + ([] if args.time_stamps else ["--date-only"]),
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
        ] + ([] if args.time_stamps else ["--date-only"]),
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
