#!/usr/bin/env python3
import argparse
import csv
import json
import re
import subprocess
import time
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import quote_plus, urlencode
from urllib.request import Request, urlopen

from pypdf import PdfReader, PdfWriter


YEAR_RE = re.compile(r"\b(18|19|20)\d{2}\b")
DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
STOPWORDS = {
    "the", "and", "for", "with", "from", "into", "that", "this", "are", "was",
    "were", "bat", "bats", "chiroptera", "journal", "volume", "number",
    "description", "observations", "catalogue", "review",
}


def normalize_space(value):
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_text(value):
    value = (value or "").casefold()
    value = re.sub(r"10\.\d{4,9}/[-._;()/:a-z0-9]+", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def tokens(value):
    return {
        token for token in normalize_text(value).split()
        if len(token) >= 4 and token not in STOPWORDS
    }


def year_from(value):
    match = YEAR_RE.search(value or "")
    return match.group(0) if match else ""


def clean_doi(value):
    value = (value or "").strip()
    value = re.sub(r"^https?://(dx\.)?doi\.org/", "", value, flags=re.IGNORECASE)
    value = re.sub(r"^doi:\s*", "", value, flags=re.IGNORECASE)
    return value.rstrip(").,;]").lower()


def safe_name(path):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", path.stem).strip("_")


def run_command(cmd, timeout=90):
    return subprocess.run(
        cmd,
        check=True,
        text=True,
        capture_output=True,
        timeout=timeout,
        errors="replace",
    )


def pdftotext_first_pages(pdf_path, text_path, pages=3, force=False):
    if force or not text_path.exists():
        text_path.parent.mkdir(parents=True, exist_ok=True)
        run_command(["pdftotext", "-f", "1", "-l", str(pages), str(pdf_path), str(text_path)])
    return text_path.read_text(encoding="utf-8", errors="replace")


def extract_text_clues(text):
    lines = [normalize_space(line) for line in text.splitlines()]
    lines = [line for line in lines if line]
    doi_match = DOI_RE.search(text or "")
    useful_lines = []
    for line in lines[:80]:
        low = line.lower()
        if len(line) < 8:
            continue
        if low.startswith(("abstract", "references", "copyright", "downloaded", "jstor", "doi")):
            continue
        useful_lines.append(line)
        if len(useful_lines) >= 6:
            break
    return {
        "text_doi": clean_doi(doi_match.group(0)) if doi_match else "",
        "text_clues": " | ".join(useful_lines[:6]),
    }


def fallback_from_filename(row):
    original = Path(row.get("original_file", "") or row.get("routed_filename", "")).stem
    original = re.sub(r"^\d+[.)_-]*\s*", "", original.replace("_", " "))
    match = YEAR_RE.search(original)
    if not match:
        return {}
    author = normalize_space(original[: match.start()].strip(" .,-_"))
    title = normalize_space(original[match.end():].strip(" .,-_"))
    title = re.sub(r"\bpp?\.?\s*\d+.*$", "", title, flags=re.IGNORECASE).strip(" .,-_")
    if not title:
        return {}
    return {"title": title, "authors": author, "year": match.group(0)}


def best_local_query(row, clues):
    title = normalize_space(row.get("title"))
    authors = normalize_space(row.get("authors"))
    year = normalize_space(row.get("year"))
    fallback = fallback_from_filename(row)
    if not title:
        title = fallback.get("title", "")
    if not authors:
        authors = fallback.get("authors", "")
    if not year:
        year = fallback.get("year", "")
    pieces = [title, authors.split("|", 1)[0].strip(), year]
    query = normalize_space(" ".join(piece for piece in pieces if piece))
    if not query and clues.get("text_clues"):
        query = " ".join(clues["text_clues"].split(" | ")[:2])
    return query[:500], {"title": title, "authors": authors, "year": year}


def fetch_json(url, user_agent, timeout=30):
    request = Request(url, headers={"User-Agent": user_agent, "Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def crossref_candidates(query, mailto="", rows=3):
    params = {"query.bibliographic": query, "rows": rows}
    if mailto:
        params["mailto"] = mailto
    url = "https://api.crossref.org/works?" + urlencode(params)
    data = fetch_json(url, user_agent=f"BatLitMetadataResolver/0.1 (mailto:{mailto or 'unknown@example.com'})")
    items = data.get("message", {}).get("items", [])
    candidates = []
    for item in items:
        title = " ".join(item.get("title") or [])
        container = " ".join(item.get("container-title") or [])
        authors = []
        for author in item.get("author") or []:
            name = normalize_space(" ".join(filter(None, [author.get("given", ""), author.get("family", "")])))
            if name:
                authors.append(name)
        issued = item.get("issued", {}).get("date-parts") or []
        year = str(issued[0][0]) if issued and issued[0] else ""
        candidates.append({
            "source": "crossref",
            "title": title,
            "authors": " | ".join(authors),
            "year": year,
            "doi": clean_doi(item.get("DOI", "")),
            "issn": " | ".join(item.get("ISSN") or []),
            "journal": container,
            "volume": item.get("volume", ""),
            "issue": item.get("issue", ""),
            "pages": item.get("page", ""),
            "url": item.get("URL", ""),
            "raw_score": str(item.get("score", "")),
        })
    return candidates


def openalex_candidates(query, mailto="", rows=3):
    params = {"search": query, "per-page": rows}
    if mailto:
        params["mailto"] = mailto
    url = "https://api.openalex.org/works?" + urlencode(params)
    data = fetch_json(url, user_agent=f"BatLitMetadataResolver/0.1 (mailto:{mailto or 'unknown@example.com'})")
    candidates = []
    for item in data.get("results", []):
        authors = []
        for authorship in item.get("authorships") or []:
            author = authorship.get("author") or {}
            if author.get("display_name"):
                authors.append(author["display_name"])
        source = item.get("primary_location", {}).get("source") or {}
        doi = clean_doi(item.get("doi", ""))
        candidates.append({
            "source": "openalex",
            "title": item.get("title", ""),
            "authors": " | ".join(authors),
            "year": str(item.get("publication_year") or ""),
            "doi": doi,
            "issn": " | ".join(source.get("issn") or []),
            "journal": source.get("display_name", ""),
            "volume": item.get("biblio", {}).get("volume", ""),
            "issue": item.get("biblio", {}).get("issue", ""),
            "pages": item.get("biblio", {}).get("first_page", ""),
            "url": item.get("doi") or item.get("id", ""),
            "raw_score": "",
        })
    return candidates


def candidate_score(local, candidate):
    local_title = local.get("title", "")
    local_authors = local.get("authors", "")
    local_year = local.get("year", "")
    title_score = SequenceMatcher(None, normalize_text(local_title), normalize_text(candidate.get("title", ""))).ratio()
    author_overlap = len(tokens(local_authors) & tokens(candidate.get("authors", "")))
    score = title_score
    if local_year and candidate.get("year") and local_year == candidate["year"]:
        score += 0.12
    if author_overlap:
        score += min(0.12, author_overlap * 0.04)
    if candidate.get("doi"):
        score += 0.03
    return min(score, 1.0)


def search_links(query, doi=""):
    q = quote_plus(query)
    doi_q = quote_plus(doi)
    return {
        "google_scholar_search": f"https://scholar.google.com/scholar?q={q}" if query else "",
        "crossref_search": f"https://search.crossref.org/?q={q}" if query else "",
        "openalex_search": f"https://openalex.org/works?page=1&filter=default.search%3A{q}" if query else "",
        "semantic_scholar_search": f"https://www.semanticscholar.org/search?q={q}" if query else "",
        "doi_url": f"https://doi.org/{doi}" if doi else "",
        "doi_google_search": f"https://www.google.com/search?q={doi_q}" if doi else "",
    }


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def embed_pdf_metadata(pdf_path, row, candidate):
    reader = PdfReader(str(pdf_path))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    metadata = {key: str(value) for key, value in dict(reader.metadata or {}).items() if key.startswith("/")}
    metadata.update({
        "/Title": candidate.get("title", "") or row.get("title", ""),
        "/Author": candidate.get("authors", "") or row.get("authors", ""),
        "/Subject": "BatLit externally resolved bibliographic metadata",
        "/Keywords": "; ".join(filter(None, ["BatLit", "external-metadata", candidate.get("doi", ""), candidate.get("issn", "")])),
        "/Creator": "BatLit pre-Zotero deduplication pipeline",
        "/BatLitExternalMetadataSource": candidate.get("source", ""),
        "/BatLitExternalMetadataScore": candidate.get("match_score", ""),
        "/BatLitYear": candidate.get("year", "") or row.get("year", ""),
        "/BatLitJournal": candidate.get("journal", ""),
        "/BatLitISSN": candidate.get("issn", ""),
        "/DOI": candidate.get("doi", "") or row.get("doi", ""),
    })
    writer.add_metadata(metadata)
    temp_path = pdf_path.with_suffix(pdf_path.suffix + ".tmp")
    with temp_path.open("wb") as handle:
        writer.write(handle)
    temp_path.replace(pdf_path)


def main():
    parser = argparse.ArgumentParser(description="Resolve routed PDF metadata against Crossref/OpenAlex and optionally embed high-confidence results.")
    parser.add_argument("--base", default=".", help="batlit-dedupe folder.")
    parser.add_argument("--run-folder", required=True, help="Folder under processed_runs.")
    parser.add_argument("--folder", default="new_literature", help="Routed folder inside the run folder.")
    parser.add_argument("--limit", type=int, default=None, help="Resolve only the first N rows.")
    parser.add_argument("--threshold", type=float, default=0.82, help="Minimum score required to embed/update.")
    parser.add_argument("--mailto", default="", help="Email for polite Crossref/OpenAlex API requests.")
    parser.add_argument("--apply", action="store_true", help="Embed high-confidence results and update bibliography.csv.")
    parser.add_argument("--force-text", action="store_true", help="Refresh cached first-page text.")
    args = parser.parse_args()

    base = Path(args.base).resolve()
    folder = base / "processed_runs" / args.run_folder / args.folder
    bibliography_path = folder / "bibliography.csv"
    rows = read_csv(bibliography_path)
    original_rows = [dict(row) for row in rows]
    if args.limit is not None:
        rows_to_process = rows[: args.limit]
    else:
        rows_to_process = rows

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    enrichment_dir = base / "metadata_enrichment" / args.run_folder
    output_dir = enrichment_dir / f"{stamp}_external_metadata_resolution"
    text_dir = base / "work" / "external_metadata_text" / args.run_folder / args.folder
    report_rows = []
    fieldnames = list(original_rows[0].keys()) if original_rows else []

    for row in rows_to_process:
        routed = row.get("routed_filename") or row.get("filename") or ""
        pdf_path = folder / routed
        text_error = ""
        try:
            text = pdftotext_first_pages(pdf_path, (text_dir / safe_name(pdf_path)).with_suffix(".pages1-3.txt"), force=args.force_text)
            clues = extract_text_clues(text)
        except Exception as exc:
            clues = {"text_doi": "", "text_clues": ""}
            text_error = f"{type(exc).__name__}: {exc}"

        query, local = best_local_query(row, clues)
        if clues.get("text_doi") and not row.get("doi"):
            row["doi"] = clues["text_doi"]

        candidates = []
        error = text_error
        if query:
            try:
                candidates.extend(crossref_candidates(query, mailto=args.mailto))
                time.sleep(0.1)
            except Exception as exc:
                error = (error + " | " if error else "") + f"crossref:{type(exc).__name__}: {exc}"
            try:
                candidates.extend(openalex_candidates(query, mailto=args.mailto))
                time.sleep(0.1)
            except Exception as exc:
                error = (error + " | " if error else "") + f"openalex:{type(exc).__name__}: {exc}"

        best = {}
        best_score = 0.0
        for candidate in candidates:
            score = candidate_score(local, candidate)
            if score > best_score:
                best_score = score
                best = candidate
        if best:
            best["match_score"] = f"{best_score:.3f}"

        status = "no_candidate"
        if best:
            status = "high_confidence" if best_score >= args.threshold else "low_confidence"

        if args.apply and status == "high_confidence":
            row["title"] = best.get("title") or row.get("title", "")
            row["authors"] = best.get("authors") or row.get("authors", "")
            row["year"] = best.get("year") or row.get("year", "")
            row["doi"] = best.get("doi") or row.get("doi", "")
            try:
                embed_pdf_metadata(pdf_path, row, best)
                status = "embedded"
            except Exception as exc:
                status = "embed_failed"
                error = (error + " | " if error else "") + f"embed:{type(exc).__name__}: {exc}"

        links = search_links(query, best.get("doi", "") if best else row.get("doi", ""))
        report_rows.append({
            "status": status,
            "routed_filename": routed,
            "original_file": row.get("original_file", ""),
            "local_query": query,
            "local_title": local.get("title", ""),
            "local_authors": local.get("authors", ""),
            "local_year": local.get("year", ""),
            "resolved_source": best.get("source", ""),
            "match_score": best.get("match_score", ""),
            "resolved_title": best.get("title", ""),
            "resolved_authors": best.get("authors", ""),
            "resolved_year": best.get("year", ""),
            "resolved_doi": best.get("doi", ""),
            "resolved_issn": best.get("issn", ""),
            "resolved_journal": best.get("journal", ""),
            "resolved_volume": best.get("volume", ""),
            "resolved_issue": best.get("issue", ""),
            "resolved_pages": best.get("pages", ""),
            "resolved_url": best.get("url", ""),
            **links,
            "text_clues": clues.get("text_clues", ""),
            "error": error,
        })

    report_fields = [
        "status", "routed_filename", "original_file", "local_query", "local_title",
        "local_authors", "local_year", "resolved_source", "match_score",
        "resolved_title", "resolved_authors", "resolved_year", "resolved_doi",
        "resolved_issn", "resolved_journal", "resolved_volume", "resolved_issue",
        "resolved_pages", "resolved_url", "google_scholar_search", "crossref_search",
        "openalex_search", "semantic_scholar_search", "doi_url", "doi_google_search",
        "text_clues", "error",
    ]
    report_path = output_dir / "external_metadata_resolution_report.csv"
    timestamped_report_path = output_dir / f"{stamp}_external_metadata_resolution_report.csv"
    write_csv(report_path, report_fields, report_rows)
    write_csv(timestamped_report_path, report_fields, report_rows)
    write_csv(enrichment_dir / "latest_external_metadata_resolution_report.csv", report_fields, report_rows)

    if args.apply and fieldnames:
        backup_path = folder / f"{stamp}_bibliography_before_external_resolution.csv"
        write_csv(backup_path, fieldnames, original_rows)
        write_csv(bibliography_path, fieldnames, rows)

    counts = {}
    for report_row in report_rows:
        counts[report_row["status"]] = counts.get(report_row["status"], 0) + 1
    for key, value in sorted(counts.items()):
        print(f"{key}: {value}")
    print(report_path)
    print(timestamped_report_path)


if __name__ == "__main__":
    main()
