#!/usr/bin/env python3
import argparse
import csv
import hashlib
import re
from datetime import datetime
from pathlib import Path


FIELDNAMES = [
    "file",
    "relative_path",
    "size_bytes",
    "mtime_iso",
    "md5",
    "sha256",
]


def slugify(value):
    value = re.sub(r"[^A-Za-z0-9]+", "_", (value or "collection").strip())
    return re.sub(r"_+", "_", value).strip("_") or "collection"


def file_hashes(path):
    md5 = hashlib.md5()
    sha256 = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            md5.update(chunk)
            sha256.update(chunk)
    return md5.hexdigest(), sha256.hexdigest()


def find_pdfs(incoming_dir):
    return sorted(
        path for path in incoming_dir.rglob("*")
        if path.is_file() and path.suffix.lower() == ".pdf"
    )


def build_manifest(incoming_dir):
    rows = []
    for path in find_pdfs(incoming_dir):
        md5, sha256 = file_hashes(path)
        stat = path.stat()
        rows.append({
            "file": path.name,
            "relative_path": path.relative_to(incoming_dir).as_posix(),
            "size_bytes": stat.st_size,
            "mtime_iso": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
            "md5": md5,
            "sha256": sha256,
        })
    return rows


def read_manifest(path):
    if not path or not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def duplicate_hash_rows(rows):
    counts = {}
    for row in rows:
        counts[row["md5"]] = counts.get(row["md5"], 0) + 1
    return [row for row in rows if counts.get(row["md5"], 0) > 1]


def write_csv(path, rows, fieldnames=FIELDNAMES):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_csv_pair(collection_dir, file_prefix, filename, rows, fieldnames=FIELDNAMES):
    write_csv(collection_dir / filename, rows, fieldnames)
    write_csv(collection_dir / f"{file_prefix}_{filename}", rows, fieldnames)


def unique_dir(path):
    if not path.exists():
        return path
    for index in range(2, 100):
        candidate = path.with_name(f"{path.name}_{index:02d}")
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"Could not find an unused folder name for {path}")


def latest_prior_manifest(collections_dir):
    manifests = sorted(collections_dir.glob("*/incoming_manifest.csv"))
    return manifests[-1] if manifests else None


def main():
    parser = argparse.ArgumentParser(description="Create a timestamped manifest and diff for a newly added incoming collection.")
    parser.add_argument("--base", default=".", help="batlit-dedupe folder; defaults to current directory")
    parser.add_argument("--label", default="", help="short human-readable label for this collection")
    parser.add_argument("--previous", default="", help="optional prior manifest CSV to diff against")
    parser.add_argument("--no-previous", action="store_true", help="do not compare against a prior manifest")
    parser.add_argument(
        "--date-only",
        action="store_true",
        help="Use YYYYMMDD instead of YYYYMMDD_HHMMSS for generated folders and files.",
    )
    args = parser.parse_args()

    base = Path(args.base).resolve()
    incoming_dir = base / "incoming"
    collections_dir = base / "collections"
    label = slugify(args.label)
    stamp = datetime.now().strftime("%Y%m%d" if args.date_only else "%Y%m%d_%H%M%S")
    collection_dir = unique_dir(collections_dir / f"{label}_{stamp}")
    collection_file_prefix = collection_dir.name

    current = build_manifest(incoming_dir)
    previous_path = None if args.no_previous else Path(args.previous).resolve() if args.previous else latest_prior_manifest(collections_dir)
    previous = read_manifest(previous_path)

    previous_hashes = {row["md5"] for row in previous if row.get("md5")}
    current_hashes = {row["md5"] for row in current if row.get("md5")}

    added = [row for row in current if row.get("md5") not in previous_hashes]
    removed = [row for row in previous if row.get("md5") not in current_hashes]
    unchanged = [row for row in current if row.get("md5") in previous_hashes]
    duplicate_rows = duplicate_hash_rows(current)

    write_csv_pair(collection_dir, collection_file_prefix, "incoming_manifest.csv", current)
    write_csv_pair(collection_dir, collection_file_prefix, "diff_added.csv", added)
    write_csv_pair(collection_dir, collection_file_prefix, "diff_removed.csv", removed)
    write_csv_pair(collection_dir, collection_file_prefix, "diff_unchanged.csv", unchanged)
    write_csv_pair(collection_dir, collection_file_prefix, "duplicates_within_collection.csv", duplicate_rows)

    summary_lines = [
        f"Collection: {collection_dir.name}",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"Incoming folder: {incoming_dir}",
        f"Previous manifest: {previous_path if previous_path else 'none'}",
        "",
        f"Current PDFs: {len(current)}",
        f"Unique current MD5 hashes: {len(current_hashes)}",
        f"Added since previous manifest: {len(added)}",
        f"Removed since previous manifest: {len(removed)}",
        f"Unchanged since previous manifest: {len(unchanged)}",
        f"Files sharing a duplicate MD5 within this collection: {len(duplicate_rows)}",
        "",
        "Files:",
        "  incoming_manifest.csv",
        f"  {collection_file_prefix}_incoming_manifest.csv",
        "  diff_added.csv",
        f"  {collection_file_prefix}_diff_added.csv",
        "  diff_removed.csv",
        f"  {collection_file_prefix}_diff_removed.csv",
        "  diff_unchanged.csv",
        f"  {collection_file_prefix}_diff_unchanged.csv",
        "  duplicates_within_collection.csv",
        f"  {collection_file_prefix}_duplicates_within_collection.csv",
    ]
    (collection_dir / "summary.txt").write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    print(collection_dir)
    print("\n".join(summary_lines))


if __name__ == "__main__":
    main()
