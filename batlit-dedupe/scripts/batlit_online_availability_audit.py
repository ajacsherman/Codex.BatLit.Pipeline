#!/usr/bin/env python3
"""Create a hard online-availability audit for incoming BatLit citations.

This stage answers a fieldwork question before Zotero packaging:

    Is the AMNH/local scan uniquely valuable, or could this item have been
    obtained from BatLit/Zenodo/BHL/BioStor/JSTOR/Internet Archive/another
    online source?

The script is deliberately conservative. It records strong local evidence and
creates provider-specific search links. Optional API lookups can be enabled for
services with public APIs. JSTOR and Google Scholar are kept as review links
because they are not stable public-harvest APIs for this workflow.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path


YEAR_RE = re.compile(r"\b(?:17|18|19|20)\d{2}\b")
DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
JSTOR_RE = re.compile(r"https?://(?:www\.)?jstor\.org/stable/[A-Za-z0-9._-]+", re.IGNORECASE)


def clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def norm(value: str | None) -> str:
    text = clean(value).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return clean(text)


def title_score(expected: str, candidate: str) -> str:
    left = norm(expected)
    right = norm(candidate)
    if not left or not right:
        return ""
    if left == right:
        return "1.000"
    return f"{SequenceMatcher(None, left, right).ratio():.3f}"


def accepted_title_match(expected: str, candidate: str, threshold: float = 0.82) -> bool:
    score = title_score(expected, candidate)
    return bool(score and float(score) >= threshold)


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


def http_json(url: str, timeout: int = 20) -> dict | list | None:
    request = urllib.request.Request(url, headers={"User-Agent": "BatLit-preZotero-audit/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None


def first_author(authors: str) -> str:
    text = clean(authors)
    if not text:
        return ""
    first = re.split(r"\s*[;|]\s*", text)[0]
    if "," in first:
        return clean(first.split(",", 1)[0])
    parts = first.split()
    if len(parts) > 1 and parts[-1].rstrip(".").lower() in {"jr", "sr", "ii", "iii", "iv"}:
        parts = parts[:-1]
    return parts[-1] if parts else first


def exact_query(title: str, authors: str, year: str) -> str:
    pieces = []
    title = clean(title)
    if title:
        pieces.append(f'"{title}"')
    author = first_author(authors)
    if author:
        pieces.append(author)
    if clean(year):
        pieces.append(clean(year))
    return clean(" ".join(pieces))


def broad_query(title: str, authors: str, year: str, journal: str) -> str:
    pieces = [clean(title), first_author(authors), clean(year), clean(journal)]
    return clean(" ".join(piece for piece in pieces if piece))


def provider_links(title: str, authors: str, year: str, journal: str, doi: str) -> dict[str, str]:
    exact = exact_query(title, authors, year)
    broad = broad_query(title, authors, year, journal)
    exact_q = urllib.parse.quote_plus(exact)
    broad_q = urllib.parse.quote_plus(broad)
    title_q = urllib.parse.quote_plus(clean(title))
    return {
        "exact_query": exact,
        "broad_query": broad,
        "doi_url": f"https://doi.org/{doi}" if doi else "",
        "google_scholar": f"https://scholar.google.com/scholar?q={exact_q}" if exact else "",
        "google_web": f"https://www.google.com/search?q={exact_q}" if exact else "",
        "jstor_search": f"https://www.jstor.org/action/doBasicSearch?Query={title_q}" if title else "",
        "bhl_search": f"https://www.biodiversitylibrary.org/search?searchTerm={broad_q}" if broad else "",
        "biostor_search": f"https://biostor.org/search?q={broad_q}" if broad else "",
        "internet_archive_search": f"https://archive.org/search?query={broad_q}" if broad else "",
        "crossref_search": f"https://search.crossref.org/?q={broad_q}" if broad else "",
        "openalex_search": f"https://openalex.org/works?page=1&filter=default.search%3A{broad_q}" if broad else "",
        "zenodo_batlit_search": f"https://zenodo.org/communities/batlit/records?q={broad_q}" if broad else "",
    }


def lookup_batlit(title: str, authors: str, year: str, refs: list[dict[str, str]]) -> tuple[str, str, str]:
    ntitle = norm(title)
    year = clean(year)
    fa = norm(first_author(authors))
    if not ntitle:
        return "", "", ""
    best = ("", "", "")
    for row in refs:
        row_title = row.get("title") or row.get("Title") or row.get("item_title") or ""
        row_authors = row.get("creators") or row.get("authors") or row.get("Authors") or ""
        row_year = row.get("year") or row.get("date") or row.get("Year") or ""
        row_url = row.get("zotero_item_url") or row.get("item_url") or row.get("url") or row.get("URL") or ""
        if norm(row_title) == ntitle:
            score = "exact_title"
            if year and year in clean(row_year):
                score += "_year"
            if fa and fa in norm(row_authors):
                score += "_author"
            return "yes", score, row_url
        if ntitle and ntitle in norm(row_title) and year and year in clean(row_year):
            best = ("possible", "title_contains_year", row_url)
    return best


def crossref_lookup(title: str, rows: int = 3) -> tuple[str, str, str]:
    if not title:
        return "", "", ""
    url = "https://api.crossref.org/works?" + urllib.parse.urlencode({"query.title": title, "rows": rows})
    data = http_json(url)
    items = (((data or {}).get("message") or {}).get("items") or []) if isinstance(data, dict) else []
    if not items:
        return "", "", ""
    item = items[0]
    found_title = clean(" ".join(item.get("title") or []))
    doi = clean(item.get("DOI"))
    link = f"https://doi.org/{doi}" if doi else clean(item.get("URL"))
    return found_title, doi, link


def openalex_lookup(title: str, rows: int = 3) -> tuple[str, str, str]:
    if not title:
        return "", "", ""
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode({"search": title, "per-page": rows})
    data = http_json(url)
    results = (data or {}).get("results") or [] if isinstance(data, dict) else []
    if not results:
        return "", "", ""
    item = results[0]
    return clean(item.get("display_name")), clean(item.get("doi")), clean(item.get("id"))


def bhl_lookup(title: str, api_key: str = "") -> tuple[str, str]:
    if not title or not api_key:
        return "", ""
    params = {"op": "PublicationSearch", "searchterm": title, "format": "json", "apikey": api_key}
    data = http_json("https://www.biodiversitylibrary.org/api3?" + urllib.parse.urlencode(params))
    results = (data or {}).get("Result") or [] if isinstance(data, dict) else []
    if not results:
        return "", ""
    first = results[0]
    return clean(first.get("Title") or first.get("FullTitle")), clean(first.get("TitleUrl") or first.get("ItemUrl"))


def internet_archive_lookup(title: str) -> tuple[str, str]:
    if not title:
        return "", ""
    query = f'title:"{title}"'
    params = {"q": query, "fl[]": ["identifier", "title"], "rows": "1", "output": "json"}
    url = "https://archive.org/advancedsearch.php?" + urllib.parse.urlencode(params, doseq=True)
    data = http_json(url)
    docs = (((data or {}).get("response") or {}).get("docs") or []) if isinstance(data, dict) else []
    if not docs:
        return "", ""
    doc = docs[0]
    ident = clean(doc.get("identifier"))
    return clean(doc.get("title")), f"https://archive.org/details/{ident}" if ident else ""


def classify(row: dict[str, str]) -> tuple[str, str]:
    if row.get("batlit_match") == "yes":
        return "already_in_batlit", "Do not prioritize AMNH scan unless annotation/excerpt adds value."
    if row.get("doi_url") or row.get("crossref_accepted") == "yes" or row.get("openalex_accepted") == "yes":
        return "online_metadata_or_identifier_found", "Check full text/PDF availability before using AMNH scan."
    if row.get("jstor_stable_url"):
        return "jstor_record_found", "Likely obtainable online or through library/VPN; verify PDF/full text."
    if row.get("bhl_url") or row.get("internet_archive_accepted") == "yes":
        return "online_scan_candidate_found", "Prefer online scan unless AMNH scan is better or annotated."
    if row.get("crossref_url") or row.get("openalex_url") or row.get("internet_archive_url"):
        return "api_candidates_need_review", "API returned low-similarity candidates; verify manually before acting."
    return "needs_online_review", "Use exact title/author/year links before treating AMNH scan as unique."


def source_rows(path: Path) -> list[dict[str, str]]:
    rows = read_csv(path)
    out = []
    for row in rows:
        title = clean(row.get("title") or row.get("current_title") or row.get("incoming_title") or row.get("citation") or "")
        authors = clean(row.get("authors") or row.get("current_authors") or row.get("incoming_authors") or row.get("author") or "")
        year = clean(row.get("year") or row.get("current_year") or row.get("incoming_year_guess") or "")
        doi = clean(row.get("doi") or row.get("current_doi") or row.get("front_matter_dois") or "")
        journal = clean(row.get("journal") or row.get("publication") or row.get("container-title") or "")
        filename = clean(row.get("enhanced_filename") or row.get("pdf_filename") or row.get("routed_filename") or row.get("filename") or row.get("original_file") or "")
        url = clean(row.get("source_url") or row.get("resolved_url") or row.get("url") or "")
        if title or authors or filename:
            out.append({
                "source_file": str(path),
                "pdf_filename": filename,
                "title": title,
                "authors": authors,
                "year": year,
                "journal": journal,
                "doi": doi.split("|", 1)[0].strip(),
                "known_url": url,
            })
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit online availability before using local scans.")
    parser.add_argument("--input-csv", action="append", required=True, help="Citation/metadata CSV to audit. Repeatable.")
    parser.add_argument("--batlit-refs", default="", help="BatLit refs.csv or literature_fingerprint_index.csv.")
    parser.add_argument("--out", required=True, help="Output audit CSV path.")
    parser.add_argument("--query-apis", action="store_true", help="Query Crossref, OpenAlex, and Internet Archive APIs.")
    parser.add_argument("--bhl-api-key", default="", help="Optional BHL API key for PublicationSearch.")
    args = parser.parse_args()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    refs = read_csv(Path(args.batlit_refs)) if args.batlit_refs else []
    audit_rows: list[dict[str, str]] = []

    seen: set[tuple[str, str, str]] = set()
    for input_csv in args.input_csv:
        for src in source_rows(Path(input_csv)):
            key = (norm(src["title"]), norm(first_author(src["authors"])), clean(src["year"]))
            if key in seen:
                continue
            seen.add(key)
            links = provider_links(src["title"], src["authors"], src["year"], src["journal"], src["doi"])
            batlit_match, batlit_reason, batlit_url = lookup_batlit(src["title"], src["authors"], src["year"], refs)
            jstor_match = JSTOR_RE.search(src["known_url"]) or JSTOR_RE.search(" ".join(src.values()))
            row = {
                "audit_timestamp": stamp,
                **src,
                "batlit_match": batlit_match,
                "batlit_match_reason": batlit_reason,
                "batlit_match_url": batlit_url,
                "jstor_stable_url": jstor_match.group(0) if jstor_match else "",
                **links,
                "crossref_title": "",
                "crossref_title_score": "",
                "crossref_accepted": "",
                "crossref_doi": "",
                "crossref_url": "",
                "openalex_title": "",
                "openalex_title_score": "",
                "openalex_accepted": "",
                "openalex_doi": "",
                "openalex_url": "",
                "bhl_title": "",
                "bhl_url": "",
                "internet_archive_title": "",
                "internet_archive_title_score": "",
                "internet_archive_accepted": "",
                "internet_archive_url": "",
                "online_availability_decision": "",
                "recommended_action": "",
                "amnh_scan_value": "",
                "review_notes": "",
            }
            if args.query_apis:
                row["crossref_title"], row["crossref_doi"], row["crossref_url"] = crossref_lookup(src["title"])
                row["openalex_title"], row["openalex_doi"], row["openalex_url"] = openalex_lookup(src["title"])
                row["internet_archive_title"], row["internet_archive_url"] = internet_archive_lookup(src["title"])
                row["crossref_title_score"] = title_score(src["title"], row["crossref_title"])
                row["openalex_title_score"] = title_score(src["title"], row["openalex_title"])
                row["internet_archive_title_score"] = title_score(src["title"], row["internet_archive_title"])
                row["crossref_accepted"] = "yes" if accepted_title_match(src["title"], row["crossref_title"]) else "no" if row["crossref_title"] else ""
                row["openalex_accepted"] = "yes" if accepted_title_match(src["title"], row["openalex_title"]) else "no" if row["openalex_title"] else ""
                row["internet_archive_accepted"] = "yes" if accepted_title_match(src["title"], row["internet_archive_title"]) else "no" if row["internet_archive_title"] else ""
            if args.bhl_api_key:
                row["bhl_title"], row["bhl_url"] = bhl_lookup(src["title"], args.bhl_api_key)
            row["online_availability_decision"], row["recommended_action"] = classify(row)
            audit_rows.append(row)

    write_csv(Path(args.out), audit_rows)
    print(f"Wrote {len(audit_rows)} rows: {args.out}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
