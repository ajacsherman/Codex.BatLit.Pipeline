#!/usr/bin/env python3
import argparse
import csv
import re
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus


YEAR_RE = re.compile(r"\b(18|19|20)\d{2}\b")
DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)


def has_alpha(value):
    return bool(re.search(r"[A-Za-z]", value or ""))


def normalize_space(value):
    return re.sub(r"\s+", " ", value or "").strip()


def bad_title(value):
    value = normalize_space(value)
    if not value or len(value) < 12:
        return True
    if not has_alpha(value):
        return True
    low = value.lower()
    suspicious = {
        "journal",
        "contents",
        "abstract",
        "references",
        "copyright",
        "proceedings",
        "volume",
    }
    if low in suspicious:
        return True
    if value.count("_") >= 3 or value.count("~") >= 1:
        return True
    return False


def bad_authors(value):
    value = normalize_space(value)
    if not value or len(value) < 3:
        return True
    if not has_alpha(value):
        return True
    low = value.lower()
    if low in {"unknown", "none", "n/a", "copyright"}:
        return True
    return False


def bad_year(value):
    return not bool(YEAR_RE.search(value or ""))


def run_command(cmd, timeout=90):
    return subprocess.run(
        cmd,
        check=True,
        text=True,
        capture_output=True,
        timeout=timeout,
        errors="replace",
    )


def safe_name(path):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", path.stem).strip("_")


def pdftotext_first_pages(pdf_path, text_path, pages=3, force=False):
    if force or not text_path.exists():
        text_path.parent.mkdir(parents=True, exist_ok=True)
        run_command(["pdftotext", "-f", "1", "-l", str(pages), str(pdf_path), str(text_path)])
    return text_path.read_text(encoding="utf-8", errors="replace")


def extract_clues(text):
    lines = [normalize_space(line) for line in text.splitlines()]
    lines = [line for line in lines if line]
    doi_match = DOI_RE.search(text or "")
    years = sorted(set(match.group(0) for match in YEAR_RE.finditer(text or "")))
    useful_lines = []
    skip_starts = (
        "abstract",
        "references",
        "copyright",
        "downloaded",
        "jstor",
        "doi",
    )
    for line in lines[:80]:
        if len(line) < 8:
            continue
        if line.lower().startswith(skip_starts):
            continue
        useful_lines.append(line)
        if len(useful_lines) >= 8:
            break
    return {
        "first_pages_doi": doi_match.group(0).rstrip(").,;]").lower() if doi_match else "",
        "first_pages_years": " | ".join(years[:8]),
        "first_pages_clues": " | ".join(useful_lines[:6]),
    }


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


def query_string(row, clues):
    pieces = []
    title = row.get("title") or row.get("incoming_title") or ""
    authors = row.get("authors") or row.get("incoming_authors") or ""
    year = row.get("year") or row.get("incoming_year_guess") or ""
    if not bad_title(title):
        pieces.append(title)
    else:
        pieces.extend((clues.get("first_pages_clues") or "").split(" | ")[:2])
    if not bad_authors(authors):
        pieces.append(authors.split("|", 1)[0].strip())
    if not bad_year(year):
        pieces.append(year)
    return normalize_space(" ".join(piece for piece in pieces if piece))[:500]


def make_links(query, doi):
    q = quote_plus(query)
    doi_q = quote_plus(doi)
    if doi:
        doi_url = f"https://doi.org/{doi}"
    else:
        doi_url = ""
    return {
        "doi_url": doi_url,
        "google_scholar_search": f"https://scholar.google.com/scholar?q={q}" if query else "",
        "crossref_search": f"https://search.crossref.org/?q={q}" if query else "",
        "openalex_search": f"https://openalex.org/works?page=1&filter=default.search%3A{q}" if query else "",
        "semantic_scholar_search": f"https://www.semanticscholar.org/search?q={q}" if query else "",
        "bhl_search": f"https://www.biodiversitylibrary.org/search?searchTerm={q}" if query else "",
        "internet_archive_search": f"https://archive.org/search?query={q}" if query else "",
        "doi_search": f"https://www.google.com/search?q={doi_q}" if doi else "",
    }


def review_reason(row):
    reasons = []
    if bad_title(row.get("title") or row.get("incoming_title")):
        reasons.append("missing_or_suspicious_title")
    if bad_authors(row.get("authors") or row.get("incoming_authors")):
        reasons.append("missing_or_suspicious_authors")
    if bad_year(row.get("year") or row.get("incoming_year_guess")):
        reasons.append("missing_year")
    if not (row.get("doi") or row.get("front_matter_dois")):
        reasons.append("missing_doi")
    return " | ".join(reasons)


def main():
    parser = argparse.ArgumentParser(description="Prepare external metadata lookup spreadsheet for routed PDFs.")
    parser.add_argument("--base", default=".", help="batlit-dedupe folder.")
    parser.add_argument("--run-folder", required=True, help="Folder under processed_runs.")
    parser.add_argument("--folders", default="new_literature", help="Comma-separated routed folders to scan.")
    parser.add_argument("--all", action="store_true", help="Include rows that do not look like they need lookup.")
    parser.add_argument("--force-text", action="store_true", help="Refresh cached first-page text.")
    args = parser.parse_args()

    base = Path(args.base).resolve()
    run_dir = base / "processed_runs" / args.run_folder
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = base / "metadata_enrichment" / args.run_folder
    text_dir = base / "work" / "metadata_lookup_text" / args.run_folder

    rows_out = []
    folders = [folder.strip() for folder in args.folders.split(",") if folder.strip()]
    for folder in folders:
        folder_dir = run_dir / folder
        bibliography = read_csv(folder_dir / "bibliography.csv")
        if not bibliography:
            bibliography = read_csv(folder_dir / "deduplicated_review_manifest.csv")
        for row in bibliography:
            filename = row.get("routed_filename") or row.get("filename") or row.get("original_file") or ""
            pdf_path = folder_dir / filename
            if not filename or not pdf_path.exists() or pdf_path.suffix.lower() != ".pdf":
                continue
            reason = review_reason(row)
            if reason == "missing_doi" and not args.all:
                # Missing DOI alone is common for older literature; keep only if another field looks weak.
                pass
            if not args.all and not reason:
                continue

            text_error = ""
            try:
                text = pdftotext_first_pages(
                    pdf_path,
                    (text_dir / folder / safe_name(pdf_path)).with_suffix(".pages1-3.txt"),
                    force=args.force_text,
                )
                clues = extract_clues(text)
            except Exception as exc:
                clues = {"first_pages_doi": "", "first_pages_years": "", "first_pages_clues": ""}
                text_error = f"{type(exc).__name__}: {exc}"

            doi = row.get("doi") or row.get("front_matter_dois") or clues.get("first_pages_doi", "")
            doi = (doi or "").split("|", 1)[0].strip()
            query = query_string(row, clues)
            links = make_links(query, doi)
            rows_out.append({
                "created": stamp,
                "run_folder": args.run_folder,
                "source_folder": folder,
                "pdf_filename": filename,
                "review_reason": reason,
                "current_title": row.get("title") or row.get("incoming_title") or "",
                "current_authors": row.get("authors") or row.get("incoming_authors") or "",
                "current_year": row.get("year") or row.get("incoming_year_guess") or "",
                "current_doi": doi,
                "first_pages_doi": clues.get("first_pages_doi", ""),
                "first_pages_years": clues.get("first_pages_years", ""),
                "first_pages_clues": clues.get("first_pages_clues", ""),
                "recommended_query": query,
                **links,
                "manual_resolution_status": "",
                "resolved_title": "",
                "resolved_authors": "",
                "resolved_year": "",
                "resolved_doi": "",
                "resolved_url": "",
                "notes": text_error,
            })

    fields = [
        "created",
        "run_folder",
        "source_folder",
        "pdf_filename",
        "review_reason",
        "current_title",
        "current_authors",
        "current_year",
        "current_doi",
        "first_pages_doi",
        "first_pages_years",
        "first_pages_clues",
        "recommended_query",
        "doi_url",
        "google_scholar_search",
        "crossref_search",
        "openalex_search",
        "semantic_scholar_search",
        "bhl_search",
        "internet_archive_search",
        "doi_search",
        "manual_resolution_status",
        "resolved_title",
        "resolved_authors",
        "resolved_year",
        "resolved_doi",
        "resolved_url",
        "notes",
    ]
    write_csv(output_dir / "external_metadata_lookup.csv", fields, rows_out)
    write_csv(output_dir / f"{stamp}_external_metadata_lookup.csv", fields, rows_out)
    summary = "\n".join([
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"Run folder: {args.run_folder}",
        f"Scanned folders: {', '.join(folders)}",
        f"Lookup rows: {len(rows_out)}",
        "",
        "Outputs:",
        "  external_metadata_lookup.csv",
        f"  {stamp}_external_metadata_lookup.csv",
    ])
    (output_dir / "summary.txt").write_text(summary + "\n", encoding="utf-8")
    print(summary)


if __name__ == "__main__":
    main()
