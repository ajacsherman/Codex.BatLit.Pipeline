#!/usr/bin/env python3
import argparse
import csv
import hashlib
import re
import subprocess
from datetime import datetime
from pathlib import Path


DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
URL_RE = re.compile(r"https?://[^\s<>\]\)]+", re.IGNORECASE)
YEAR_RE = re.compile(r"\b(18|19|20)\d{2}[a-z]?\b", re.IGNORECASE)
REFERENCE_HEADING_RE = re.compile(
    r"^\s*(references|literature cited|bibliography|works cited|citations)\s*$",
    re.IGNORECASE,
)
STOP_HEADING_RE = re.compile(
    r"^\s*(appendix|appendices|supplement|supplementary|supporting information|acknowledg(e)?ments?)\b",
    re.IGNORECASE,
)


def safe_name(path):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", path.stem).strip("_")


def clean_doi(value):
    return (value or "").rstrip(").,;]").lower()


def normalize_text(value):
    value = (value or "").casefold()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def run_command(cmd, timeout=180):
    return subprocess.run(
        cmd,
        check=True,
        text=True,
        capture_output=True,
        timeout=timeout,
        errors="replace",
    )


def cached_pdftotext(pdf_path, text_path, force=False):
    if force or not text_path.exists():
        text_path.parent.mkdir(parents=True, exist_ok=True)
        run_command(["pdftotext", str(pdf_path), str(text_path)])
    return text_path.read_text(encoding="utf-8", errors="replace")


def find_reference_section(text):
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if REFERENCE_HEADING_RE.match(line.strip()):
            start = index + 1
    if start is None:
        return ""

    end = len(lines)
    for index in range(start, len(lines)):
        line = lines[index].strip()
        if STOP_HEADING_RE.match(line):
            end = index
            break
    return "\n".join(lines[start:end]).strip()


def looks_like_reference_start(line):
    stripped = line.strip()
    if not stripped:
        return False
    if re.match(r"^\[\d+\]\s+", stripped):
        return True
    if re.match(r"^\d+[.)]\s+", stripped):
        return True
    if re.match(r"^[A-Z][A-Za-z'`-]+,\s+[A-Z]", stripped):
        return True
    if YEAR_RE.search(stripped) and re.match(r"^[A-Z][A-Za-z'`-]+", stripped):
        return True
    return False


def split_reference_entries(reference_text):
    lines = [line.rstrip() for line in reference_text.splitlines()]
    entries = []
    current = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current:
                current.append("")
            continue
        if looks_like_reference_start(stripped) and current:
            entry = " ".join(part.strip() for part in current if part.strip())
            if entry:
                entries.append(entry)
            current = [stripped]
        else:
            current.append(stripped)

    if current:
        entry = " ".join(part.strip() for part in current if part.strip())
        if entry:
            entries.append(entry)

    return [entry for entry in entries if len(entry) >= 25]


def guess_title(reference_text):
    text = re.sub(r"^\[\d+\]\s*", "", reference_text)
    text = re.sub(r"^\d+[.)]\s*", "", text)
    parts = [part.strip() for part in re.split(r"\.\s+", text) if part.strip()]
    if len(parts) >= 3:
        return parts[1][:300]
    if len(parts) >= 2:
        return parts[-1][:300]
    return ""


def guess_authors(reference_text):
    text = re.sub(r"^\[\d+\]\s*", "", reference_text)
    text = re.sub(r"^\d+[.)]\s*", "", text)
    year_match = YEAR_RE.search(text)
    if year_match:
        return text[: year_match.start()].strip(" .")
    parts = text.split(".", 1)
    return parts[0].strip()[:300] if parts else ""


def reference_key(reference_text):
    doi_match = DOI_RE.search(reference_text)
    if doi_match:
        return "doi:" + clean_doi(doi_match.group(0))
    return "text:" + hashlib.md5(normalize_text(reference_text).encode("utf-8")).hexdigest()


def find_pdfs(root):
    return sorted(path for path in root.rglob("*.pdf") if path.is_file())


def write_csv(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description="Extract cited reference candidates from routed BatLit PDFs.")
    parser.add_argument("--base", default=".", help="batlit-dedupe folder.")
    parser.add_argument("--run-folder", required=True, help="Folder under processed_runs.")
    parser.add_argument(
        "--folders",
        default="Deduplicated_new_literature,Deduplicated_likely_duplicates",
        help="Comma-separated folders inside the run folder to scan.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Process only the first N PDFs for testing.")
    parser.add_argument("--force-text", action="store_true", help="Refresh cached full text.")
    args = parser.parse_args()

    base = Path(args.base).resolve()
    run_dir = base / "processed_runs" / args.run_folder
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = base / "citation_network" / args.run_folder
    text_dir = base / "work" / "citation_reference_text" / args.run_folder

    rows = []
    edge_rows = []
    seen_reference_keys = {}
    folders = [folder.strip() for folder in args.folders.split(",") if folder.strip()]
    pdfs_to_scan = []

    for folder in folders:
        folder_path = run_dir / folder
        if not folder_path.exists():
            continue
        for pdf_path in find_pdfs(folder_path):
            pdfs_to_scan.append((folder, pdf_path))

    if args.limit is not None:
        pdfs_to_scan = pdfs_to_scan[: args.limit]

    for folder, pdf_path in pdfs_to_scan:
        rel_pdf = pdf_path.relative_to(run_dir).as_posix()
        text_path = (text_dir / folder / safe_name(pdf_path)).with_suffix(".txt")
        try:
            full_text = cached_pdftotext(pdf_path, text_path, force=args.force_text)
            reference_section = find_reference_section(full_text)
            entries = split_reference_entries(reference_section) if reference_section else []
            text_error = ""
        except Exception as exc:
            entries = []
            text_error = f"{type(exc).__name__}: {exc}"

        if not entries:
            rows.append({
                "extraction_timestamp": stamp,
                "source_pdf": rel_pdf,
                "source_folder": folder,
                "reference_number": "",
                "reference_key": "",
                "reference_text": "",
                "doi": "",
                "url": "",
                "year": "",
                "guessed_authors": "",
                "guessed_title": "",
                "deduplicated_reference_count": "",
                "status": "no_references_extracted" if not text_error else "text_extraction_failed",
                "error": text_error,
            })
            continue

        for number, entry in enumerate(entries, start=1):
            doi_match = DOI_RE.search(entry)
            url_match = URL_RE.search(entry)
            year_match = YEAR_RE.search(entry)
            key = reference_key(entry)
            seen_reference_keys.setdefault(key, set()).add(rel_pdf)
            row = {
                "extraction_timestamp": stamp,
                "source_pdf": rel_pdf,
                "source_folder": folder,
                "reference_number": number,
                "reference_key": key,
                "reference_text": entry,
                "doi": clean_doi(doi_match.group(0)) if doi_match else "",
                "url": url_match.group(0).rstrip(".,;") if url_match else "",
                "year": year_match.group(0)[:4] if year_match else "",
                "guessed_authors": guess_authors(entry),
                "guessed_title": guess_title(entry),
                "deduplicated_reference_count": "",
                "status": "extracted",
                "error": "",
            }
            rows.append(row)
            edge_rows.append({
                "source_pdf": rel_pdf,
                "cited_reference_key": key,
                "cited_doi": row["doi"],
                "cited_year": row["year"],
                "cited_title_guess": row["guessed_title"],
            })

    for row in rows:
        key = row.get("reference_key")
        if key:
            row["deduplicated_reference_count"] = len(seen_reference_keys.get(key, set()))

    fields = [
        "extraction_timestamp",
        "source_pdf",
        "source_folder",
        "reference_number",
        "reference_key",
        "reference_text",
        "doi",
        "url",
        "year",
        "guessed_authors",
        "guessed_title",
        "deduplicated_reference_count",
        "status",
        "error",
    ]
    edge_fields = ["source_pdf", "cited_reference_key", "cited_doi", "cited_year", "cited_title_guess"]

    write_csv(output_dir / "cited_reference_candidates.csv", fields, rows)
    write_csv(output_dir / f"{stamp}_cited_reference_candidates.csv", fields, rows)
    write_csv(output_dir / "citation_edges.csv", edge_fields, edge_rows)
    write_csv(output_dir / f"{stamp}_citation_edges.csv", edge_fields, edge_rows)

    unique_refs = len(seen_reference_keys)
    extracted = len([row for row in rows if row["status"] == "extracted"])
    no_refs = len([row for row in rows if row["status"] != "extracted"])
    summary = "\n".join([
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"Run folder: {args.run_folder}",
        f"Scanned folders: {', '.join(folders)}",
        f"Reference rows extracted: {extracted}",
        f"Unique reference keys: {unique_refs}",
        f"PDFs without extracted references/errors: {no_refs}",
        "",
        "Outputs:",
        "  cited_reference_candidates.csv",
        "  citation_edges.csv",
    ])
    (output_dir / "summary.txt").write_text(summary + "\n", encoding="utf-8")
    print(summary)


if __name__ == "__main__":
    main()
