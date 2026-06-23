#!/usr/bin/env python3
import argparse
import shutil
import subprocess
from pathlib import Path


FOLDERS = [
    "collections",
    "incoming",
    "index",
    "processed",
    "processed/duplicates",
    "processed/likely_duplicates",
    "processed/new_literature",
    "processed/manual_review",
    "processed/non_bat_review",
    "processed/failed_processing",
    "processed_runs",
    "reports",
    "work",
    "work/text_first3",
    "work/text_full_keyword_scan",
    "zotero_diffs",
    "collection_tracking",
]


REQUIRED_COMMANDS = [
    ("pdftotext", "Poppler text extraction"),
    ("pdfinfo", "Poppler PDF metadata/page counts"),
]


def run_command(cmd):
    return subprocess.run(cmd, text=True, capture_output=True, errors="replace")


def command_status(command):
    path = shutil.which(command)
    if not path:
        return "missing", ""
    result = run_command([command, "-v"])
    version = (result.stdout or result.stderr or "").splitlines()
    return "ok", version[0] if version else path


def create_folders(base):
    for folder in FOLDERS:
        (base / folder).mkdir(parents=True, exist_ok=True)


def write_gitkeep(base):
    keep_folders = [
        "collections",
        "incoming",
        "index",
        "processed_runs",
        "reports",
        "work",
        "zotero_diffs",
        "collection_tracking",
    ]
    for folder in keep_folders:
        keep = base / folder / ".gitkeep"
        if not keep.exists():
            keep.write_text("", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Initialize and check a BatLit pre-Zotero pipeline workspace.")
    parser.add_argument("--base", default=".", help="batlit-dedupe folder; defaults to current directory.")
    parser.add_argument("--no-gitkeep", action="store_true", help="Do not create .gitkeep files.")
    args = parser.parse_args()

    base = Path(args.base).resolve()
    create_folders(base)
    if not args.no_gitkeep:
        write_gitkeep(base)

    print(f"Base: {base}")
    print("Folders: ok")
    print("")
    print("Dependency check:")
    missing = []
    for command, description in REQUIRED_COMMANDS:
        status, detail = command_status(command)
        print(f"  {command}: {status} ({description}) {detail}")
        if status != "ok":
            missing.append(command)

    refs = base / "index" / "refs.csv"
    print("")
    if refs.exists():
        print(f"BatLit refs.csv: ok ({refs})")
    else:
        print(f"BatLit refs.csv: missing ({refs})")
        print("Place a BatLit refs.csv export in index/refs.csv before running dedupe.")

    if missing:
        raise SystemExit("Missing required command-line dependencies: " + ", ".join(missing))


if __name__ == "__main__":
    main()
