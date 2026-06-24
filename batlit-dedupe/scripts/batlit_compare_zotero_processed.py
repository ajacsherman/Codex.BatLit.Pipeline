#!/usr/bin/env python3
import argparse
import csv
import re
from difflib import SequenceMatcher
from pathlib import Path


YEAR_RE = re.compile(r"\b(18|19|20)\d{2}\b")
STOPWORDS = {
    "the", "and", "for", "with", "from", "into", "that", "this", "are", "was",
    "were", "bat", "bats", "chiroptera", "journal", "volume", "number",
}


def normalize_text(value):
    value = (value or "").casefold()
    value = re.sub(r"https?://\S+", " ", value)
    value = re.sub(r"10\.\d{4,9}/[-._;()/:a-z0-9]+", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def titleish_from_citation(value):
    value = re.sub(r"https?://\S+", "", value or "")
    value = re.sub(r"\([^)]*\d{4}[a-z]?\)", ". ", value)
    parts = [part.strip() for part in re.split(r"\.\s+", value) if part.strip()]
    if len(parts) >= 2:
        return parts[1]
    return value.strip()


def year_from(value):
    match = YEAR_RE.search(value or "")
    return match.group(0) if match else ""


def tokens(value):
    return {
        token
        for token in normalize_text(value).split()
        if len(token) >= 4 and token not in STOPWORDS
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


def load_success_lines(path):
    raw_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    lines = [line.strip() for line in raw_lines if line.strip()]
    records = []
    for line in lines:
        records.append({
            "citation": line,
            "citation_title_guess": titleish_from_citation(line),
            "citation_year": year_from(line),
            "citation_norm": normalize_text(line),
            "title_norm": normalize_text(titleish_from_citation(line)),
            "tokens": tokens(line),
        })
    return records


def row_search_fields(row):
    title = row.get("title") or row.get("incoming_title") or row.get("routed_filename") or ""
    authors = row.get("authors") or row.get("incoming_authors") or ""
    year = row.get("year") or row.get("incoming_year_guess") or ""
    text = f"{authors} {year} {title} {row.get('routed_filename') or row.get('filename') or ''}"
    return title, authors, year, tokens(text)


def plausible_candidate(row_year, row_tokens, success):
    if row_year and success["citation_year"] and row_year == success["citation_year"]:
        return True
    shared = row_tokens & success["tokens"]
    return len(shared) >= 2


def match_score(row, success, row_fields=None):
    if row_fields is None:
        title, authors, year, _row_tokens = row_search_fields(row)
    else:
        title, authors, year, _row_tokens = row_fields
    candidates = [
        normalize_text(title),
        normalize_text(f"{authors} {year} {title}"),
        normalize_text(row.get("routed_filename") or row.get("filename") or ""),
    ]
    success_candidates = [success["title_norm"], success["citation_norm"]]
    best = 0.0
    for left in candidates:
        if not left:
            continue
        for right in success_candidates:
            if not right:
                continue
            score = SequenceMatcher(None, left, right).ratio()
            if score > best:
                best = score
    row_year = year_from(year)
    if row_year and success["citation_year"] and row_year == success["citation_year"]:
        best = min(1.0, best + 0.05)
    return best


def main():
    parser = argparse.ArgumentParser(description="Compare routed BatLit items with a pasted list of items Zotero processed successfully.")
    parser.add_argument("--base", default=".", help="batlit-dedupe folder.")
    parser.add_argument("--run-folder", required=True, help="Folder under processed_runs.")
    parser.add_argument("--folder", default="new_literature", help="Routed folder to compare.")
    parser.add_argument("--success-list", required=True, help="Plain text list of citations Zotero processed successfully.")
    parser.add_argument("--threshold", type=float, default=0.72, help="Fuzzy score threshold for likely processed matches.")
    args = parser.parse_args()

    base = Path(args.base).resolve()
    run_dir = base / "processed_runs" / args.run_folder
    bibliography_path = run_dir / args.folder / "bibliography.csv"
    output_dir = base / "metadata_enrichment" / args.run_folder
    success_records = load_success_lines(Path(args.success_list))
    rows = read_csv(bibliography_path)

    out_rows = []
    needs_lookup = []
    for row in rows:
        best_success = None
        best_score = 0.0
        row_fields = row_search_fields(row)
        _title, _authors, row_year, row_tokens = row_fields
        plausible = [
            success for success in success_records
            if plausible_candidate(year_from(row_year), row_tokens, success)
        ]
        if not plausible:
            plausible = success_records
        for success in plausible:
            score = match_score(row, success, row_fields=row_fields)
            if score > best_score:
                best_score = score
                best_success = success
        status = "zotero_processed_likely" if best_score >= args.threshold else "needs_external_lookup"
        out = {
            "status": status,
            "match_score": f"{best_score:.3f}",
            "routed_filename": row.get("routed_filename", ""),
            "original_file": row.get("original_file", ""),
            "title": row.get("title", ""),
            "authors": row.get("authors", ""),
            "year": row.get("year", ""),
            "doi": row.get("doi", ""),
            "matched_zotero_citation": best_success["citation"] if best_success else "",
            "matched_zotero_title_guess": best_success["citation_title_guess"] if best_success else "",
        }
        out_rows.append(out)
        if status == "needs_external_lookup":
            needs_lookup.append(out)

    fields = [
        "status",
        "match_score",
        "routed_filename",
        "original_file",
        "title",
        "authors",
        "year",
        "doi",
        "matched_zotero_citation",
        "matched_zotero_title_guess",
    ]
    write_csv(output_dir / "zotero_processed_comparison.csv", fields, out_rows)
    write_csv(output_dir / "zotero_unprocessed_needs_lookup.csv", fields, needs_lookup)
    print(f"Routed rows: {len(rows)}")
    print(f"Zotero success-list rows: {len(success_records)}")
    print(f"Likely processed: {len(out_rows) - len(needs_lookup)}")
    print(f"Needs lookup: {len(needs_lookup)}")
    print(output_dir / "zotero_processed_comparison.csv")
    print(output_dir / "zotero_unprocessed_needs_lookup.csv")


if __name__ == "__main__":
    main()
