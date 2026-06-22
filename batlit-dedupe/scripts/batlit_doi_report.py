#!/usr/bin/env python3
import argparse
import csv
import re
import subprocess
from datetime import datetime
from pathlib import Path


DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)


def run_pdftotext(pdf_path, out_path=None, first_page=None, last_page=None):
    cmd = ["pdftotext"]
    if first_page is not None:
        cmd.extend(["-f", str(first_page)])
    if last_page is not None:
        cmd.extend(["-l", str(last_page)])
    cmd.append(str(pdf_path))
    if out_path is None:
        cmd.append("-")
        return subprocess.run(cmd, check=True, text=True, capture_output=True).stdout
    cmd.append(str(out_path))
    subprocess.run(cmd, check=True)
    return out_path.read_text(encoding="utf-8", errors="replace")


def clean_doi(value):
    return value.rstrip(").,;]").lower()


def load_batlit_refs(refs_path):
    refs_by_doi = {}
    if not refs_path.exists():
        return refs_by_doi

    with refs_path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            doi = (row.get("doi") or "").strip().lower()
            if doi:
                refs_by_doi.setdefault(doi, []).append(row)
    return refs_by_doi


def plausible_title_and_authors(first_page_text):
    lines = [line.strip() for line in first_page_text.splitlines() if line.strip()]
    if not lines:
        return "", ""

    title_lines = []
    author_line = ""

    for index, line in enumerate(lines[:30]):
        if index < 2 and (re.search(r"\b\d{4}\b", line) or re.search(r"\d+\s*\(\d+\)", line)):
            continue
        if re.search(r"\bAbstract\b", line, re.IGNORECASE):
            break
        if re.search(r"\d", line) and "doi" in line.lower():
            continue
        if "," in line and re.search(r"\b[A-Z][a-z]+", line) and len(title_lines) >= 1:
            author_line = line
            break
        title_lines.append(line)
        if len(title_lines) >= 5:
            break

    title = " ".join(title_lines).strip(" :")
    authors = re.sub(r"\d+", "", author_line)
    authors = authors.replace("&", "|")
    authors = re.sub(r"\s*\|\s*", " | ", authors)
    authors = re.sub(r"\s+", " ", authors).strip(" ,;")
    return title, authors


def doi_context(full_text, doi):
    match = re.search(re.escape(doi), full_text, re.IGNORECASE)
    if not match:
        return "unknown"

    before = full_text[: match.start()]
    reference_markers = [
        before.lower().rfind("references"),
        before.lower().rfind("literature cited"),
        before.lower().rfind("bibliography"),
    ]
    latest_marker = max(reference_markers)
    if latest_marker >= 0 and match.start() - latest_marker < 60000:
        return "reference_list"
    if match.start() < 12000:
        return "front_matter"
    return "full_text"


def main():
    parser = argparse.ArgumentParser(description="Create a BatLit pre-Zotero DOI report for incoming PDFs.")
    parser.add_argument("--base", default=".", help="batlit-dedupe folder; defaults to current directory")
    args = parser.parse_args()

    base = Path(args.base).resolve()
    incoming_dir = base / "incoming"
    text_dir = base / "work" / "text"
    reports_dir = base / "reports"
    refs_path = base / "index" / "refs.csv"
    out_path = reports_dir / "doi_match_report_with_metadata.csv"

    text_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    refs_by_doi = load_batlit_refs(refs_path)
    rows = []

    for pdf_path in sorted(incoming_dir.glob("*.pdf")):
        first_page_text = run_pdftotext(pdf_path, first_page=1, last_page=1)
        full_text_path = text_dir / f"{pdf_path.stem}.full.txt"
        full_text = run_pdftotext(pdf_path, out_path=full_text_path)
        title, authors = plausible_title_and_authors(first_page_text)

        dois = sorted({clean_doi(match.group(0)) for match in DOI_RE.finditer(full_text)})
        if not dois:
            rows.append({
                "file": pdf_path.name,
                "incoming_title": title,
                "incoming_authors": authors,
                "found_doi": "",
                "doi_context": "none_found",
                "batlit_status": "NO_DOI_FOUND",
                "batlit_title": "",
                "batlit_authors": "",
                "batlit_year_or_date": "",
                "batlit_zotero_id": "",
                "batlit_attachment_id": "",
            })
            continue

        for doi in dois:
            matches = refs_by_doi.get(doi, [])
            context = doi_context(full_text, doi)
            if matches:
                for match in matches:
                    rows.append({
                        "file": pdf_path.name,
                        "incoming_title": title,
                        "incoming_authors": authors,
                        "found_doi": doi,
                        "doi_context": context,
                        "batlit_status": "DOI_MATCH",
                        "batlit_title": match.get("title", ""),
                        "batlit_authors": match.get("authors", ""),
                        "batlit_year_or_date": match.get("date", ""),
                        "batlit_zotero_id": match.get("id", ""),
                        "batlit_attachment_id": match.get("attachmentId", ""),
                    })
            else:
                rows.append({
                    "file": pdf_path.name,
                    "incoming_title": title,
                    "incoming_authors": authors,
                    "found_doi": doi,
                    "doi_context": context,
                    "batlit_status": "NO_DOI_MATCH",
                    "batlit_title": "",
                    "batlit_authors": "",
                    "batlit_year_or_date": "",
                    "batlit_zotero_id": "",
                    "batlit_attachment_id": "",
                })

    fieldnames = [
        "file",
        "incoming_title",
        "incoming_authors",
        "found_doi",
        "doi_context",
        "batlit_status",
        "batlit_title",
        "batlit_authors",
        "batlit_year_or_date",
        "batlit_zotero_id",
        "batlit_attachment_id",
    ]
    try:
        handle = out_path.open("w", newline="", encoding="utf-8")
    except PermissionError:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = reports_dir / f"doi_match_report_with_metadata_{stamp}.csv"
        handle = out_path.open("w", newline="", encoding="utf-8")

    with handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(out_path)


if __name__ == "__main__":
    main()
