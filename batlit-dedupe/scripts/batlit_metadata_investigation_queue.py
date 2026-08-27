#!/usr/bin/env python3
"""Build a metadata investigation queue for weak AMNH/BatLit PDF records."""

import argparse
import csv
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

from batlit_mdd_citation_clues import (
    clean,
    clue_lines,
    distinctive_quote,
    extract_book_chapter_metadata,
    title_like_lines,
    useful_lines,
)
from batlit_dedupe_workflow import best_text_extraction


NOISE_RE = re.compile(
    r"reprint|collection|dept\.?|mammalog|a\.?\s*m\.?\s*n\.?\s*h\.?|"
    r"made in united states|printed from|copyright",
    re.I,
)

FIELDNAMES = [
    "status",
    "routed_filename",
    "original_file",
    "issue_flags",
    "current_title",
    "current_authors",
    "current_year",
    "current_doi",
    "text_extraction_method",
    "front_matter_text_score",
    "full_text_score",
    "ocr_attempts",
    "pages_examined",
    "annotation_clues",
    "mdd_priority_status",
    "mdd_priority_matches",
    "mdd_priority_queries",
    "detected_book_title",
    "detected_editors",
    "detected_chapter_title",
    "detected_chapter_author",
    "title_like_lines",
    "citation_clues",
    "distinctive_quote",
    "recommended_query",
    "google_scholar_search",
    "crossref_search",
    "openalex_search",
    "bhl_search",
    "internet_archive_search",
    "first_pages_text",
    "rendered_page_1",
    "rendered_page_2",
    "recommended_action",
]


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def safe_stem(value):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", Path(value).stem).strip("_") or "pdf"


def normalize(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def issue_flags(row):
    flags = []
    filename = clean(row.get("routed_filename"))
    title = clean(row.get("title"))
    authors = clean(row.get("authors"))
    year = clean(row.get("year"))
    if filename.startswith("Unknown") or filename.startswith("()"):
        flags.append("unknown_filename")
    if not authors:
        flags.append("blank_author")
    if not title or NOISE_RE.search(title):
        flags.append("noisy_title")
    if not re.fullmatch(r"(17|18|19|20)\d{2}", year or ""):
        flags.append("missing_or_invalid_year")
    if year and int(year) < 1850 and not re.search(r"\b(Proceedings|Journal|Bulletin|Annals|Magazine|Natural History|Memoirs)\b", title, re.I):
        flags.append("possible_taxonomic_year")
    return flags


def search_links(query):
    q = quote_plus(query)
    return {
        "google_scholar_search": f"https://scholar.google.com/scholar?q={q}" if query else "",
        "crossref_search": f"https://search.crossref.org/?q={q}" if query else "",
        "openalex_search": f"https://openalex.org/works?page=1&filter=default.search%3A{q}" if query else "",
        "bhl_search": f"https://www.biodiversitylibrary.org/search?searchTerm={q}" if query else "",
        "internet_archive_search": f"https://archive.org/search?query={q}" if query else "",
    }


def load_mdd_priority(path):
    if not path:
        return [], "not_configured"
    priority_path = Path(path)
    if not priority_path.exists():
        return [], f"missing:{priority_path}"
    rows = []
    for row in read_csv(priority_path):
        values = {str(k or "").strip().casefold(): clean(v) for k, v in row.items()}
        def by_exact_or_contains(*needles):
            for needle in needles:
                if needle in values and values[needle]:
                    return values[needle]
            for key, value in values.items():
                if value and any(needle in key for needle in needles):
                    return value
            return ""
        text = " ".join(value for value in values.values() if value)
        citation = by_exact_or_contains("full citation", "citation", "reference")
        authority = by_exact_or_contains("author and date", "authorityspecies", "authority")
        link = by_exact_or_contains("doi or pdf", "mdd taxon url", "authorityspecieslink", "url", "link")
        species = by_exact_or_contains("species", "scientificname", "sciname", "acceptedname", "taxon")
        original_name = by_exact_or_contains("original name", "originalname", "synonym")
        rows.append({
            "label": clean(
                citation
                or authority
                or values.get("title")
                or text[:220]
            ),
            "taxon": clean(
                species
                or original_name
            ),
            "query": clean(
                values.get("query")
                or values.get("search_query")
                or citation
                or " ".join(item for item in [species, original_name, authority, citation] if item)
                or text[:350]
            ),
            "haystack": normalize(" ".join([text, species, original_name, authority, citation, link])),
        })
    return rows, f"loaded:{priority_path}:{len(rows)}"


def mdd_priority_matches(priority_rows, evidence_text, limit=5):
    if not priority_rows:
        return [], []
    evidence = normalize(evidence_text)
    evidence_tokens = {token for token in evidence.split() if len(token) >= 5}
    scored = []
    for row in priority_rows:
        taxon = normalize(row.get("taxon"))
        label = normalize(row.get("label"))
        score = 0
        if taxon and taxon in evidence:
            score += 50
        if label and label[:80] and label[:80] in evidence:
            score += 35
        row_tokens = {token for token in row["haystack"].split() if len(token) >= 5}
        score += len(evidence_tokens & row_tokens)
        if score >= 4:
            scored.append((score, row))
    scored.sort(key=lambda item: item[0], reverse=True)
    matches = [f"{score}: {row['label']}" for score, row in scored[:limit]]
    queries = [row["query"] for score, row in scored[:limit] if row.get("query")]
    return matches, queries


def annotation_clues(pdf_path, max_pages=3):
    try:
        from pypdf import PdfReader
    except Exception:
        return ""
    clues = []
    try:
        reader = PdfReader(str(pdf_path))
        for page_index, page in enumerate(reader.pages[:max_pages], start=1):
            for annot_ref in page.get("/Annots", []) or []:
                annot = annot_ref.get_object()
                parts = [
                    annot.get("/Contents", ""),
                    annot.get("/T", ""),
                    annot.get("/Subj", ""),
                ]
                text = clean(" ".join(str(part) for part in parts if part))
                if text:
                    clues.append(f"p{page_index}: {text}")
    except Exception as exc:
        return f"annotation_read_error:{type(exc).__name__}: {exc}"
    return " | ".join(clues[:12])


def investigation_query(row, layout, titles, quote, annotation_text="", mdd_queries=None):
    if mdd_queries:
        return clean(mdd_queries[0])[:700]
    chapter_author = layout.get("chapter_author", "")
    chapter_title = layout.get("chapter_title", "")
    book_title = layout.get("book_title", "")
    if chapter_author and chapter_title:
        pieces = [chapter_author, chapter_title, book_title, f"\"{quote}\"" if quote else ""]
        return clean(" ".join(piece for piece in pieces if piece))[:700]

    current_authors = clean(row.get("authors"))
    current_title = clean(row.get("title"))
    title_hint = ""
    for title in titles:
        if not NOISE_RE.search(title):
            title_hint = title
            break
    if not title_hint and current_title and not NOISE_RE.search(current_title):
        title_hint = current_title

    pieces = []
    if current_authors and not NOISE_RE.search(current_authors):
        pieces.append(current_authors)
    if title_hint:
        pieces.append(title_hint)
    elif current_title:
        pieces.append(current_title)
    if quote:
        pieces.append(f"\"{quote}\"")
    if annotation_text and len(annotation_text) < 250:
        pieces.append(annotation_text)
    return clean(" ".join(pieces))[:700]


def render_pages(pdf_path, output_dir, pages=2):
    if pages <= 0:
        return ["", ""]
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = output_dir / "page"
    if shutil.which("pdftoppm"):
        cmd = ["pdftoppm", "-f", "1", "-l", str(pages), "-png", "-r", "160", str(pdf_path), str(prefix)]
    else:
        return ["", ""]
    subprocess.run(cmd, check=True, capture_output=True, text=True, errors="replace")
    rendered = sorted(output_dir.glob("page-*.png"))
    return [str(rendered[index]) if index < len(rendered) else "" for index in range(2)]


def should_expand_to_fallback(flags, layout, titles, quote, annotation_text, mdd_matches):
    if layout.get("chapter_author") and layout.get("chapter_title"):
        return False
    useful_titles = [title for title in titles if not NOISE_RE.search(title)]
    if mdd_matches:
        return False
    if annotation_text and re.search(r"\b(17|18|19|20)\d{2}\b", annotation_text):
        return False
    if useful_titles and quote and "blank_author" not in flags:
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description="Create a staged metadata investigation queue for weak PDF records.")
    parser.add_argument("--base", default=".", help="batlit-dedupe folder")
    parser.add_argument("--run-folder", required=True, help="processed_runs folder name")
    parser.add_argument("--folder", default="new_literature", help="routed folder")
    parser.add_argument("--initial-pages", type=int, default=3, help="leading pages to inspect first")
    parser.add_argument("--pages", type=int, default=10, help="fallback leading pages to inspect if first pass is unresolved")
    parser.add_argument("--render-pages", type=int, default=2, help="number of leading pages to render")
    parser.add_argument("--limit", type=int, default=0, help="process only the first N queued records")
    parser.add_argument("--only-filename", default="", help="process only a routed filename containing this text")
    parser.add_argument("--min-front-text-score", type=int, default=220, help="front-matter score below which OCR fallbacks are attempted")
    parser.add_argument(
        "--ocr-flagged-records",
        action="store_true",
        help="try OCR fallbacks for queued records even when native text is abundant",
    )
    parser.add_argument("--no-ocr-fallback", action="store_true", help="disable OCR fallback attempts")
    parser.add_argument("--mdd-priority-csv", default="", help="optional MDD/AMNH priority original-description citation CSV")
    parser.add_argument("--force-text", action="store_true", help="refresh cached extracted text")
    args = parser.parse_args()

    base = Path(args.base).resolve()
    folder = base / "processed_runs" / args.run_folder / args.folder
    bibliography = folder / "bibliography.csv"
    if not bibliography.exists():
        raise SystemExit(f"Missing bibliography: {bibliography}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = base / "metadata_enrichment" / args.run_folder / f"{stamp}_metadata_investigation_queue"
    text_dir = base / "work" / "metadata_investigation_text" / args.run_folder / args.folder
    ocr_dir = base / "work" / "metadata_investigation_ocr" / args.run_folder / args.folder
    priority_rows, priority_status = load_mdd_priority(args.mdd_priority_csv)
    rows_out = []

    queued_seen = 0
    for row in read_csv(bibliography):
        flags = issue_flags(row)
        if not flags:
            continue
        routed = clean(row.get("routed_filename"))
        if args.only_filename and args.only_filename.casefold() not in routed.casefold():
            continue
        queued_seen += 1
        if args.limit and queued_seen > args.limit:
            break
        pdf_path = folder / routed
        stem = safe_stem(routed)
        text_path = (text_dir / stem).with_suffix(f".pages1-{args.initial_pages}.txt")
        evidence_dir = output_dir / "rendered_pages" / stem
        try:
            min_score = 999999 if args.ocr_flagged_records else args.min_front_text_score
            first, text, full_text, method, front_score, full_score, attempts, text_error = best_text_extraction(
                pdf_path,
                text_dir,
                ocr_dir,
                args.initial_pages,
                force=args.force_text,
                min_front_score=min_score,
                ocr_fallback=not args.no_ocr_fallback,
            )
            text_path.parent.mkdir(parents=True, exist_ok=True)
            text_path.write_text(text, encoding="utf-8", errors="replace")
            pages_examined = args.initial_pages
            annot_text = annotation_clues(pdf_path, max_pages=args.initial_pages)
            lines = useful_lines(text)
            layout = extract_book_chapter_metadata(lines)
            titles = title_like_lines(lines)
            quote = distinctive_quote(text)
            clues = clue_lines(lines, [])
            evidence_text = " ".join([
                row.get("title", ""),
                row.get("authors", ""),
                row.get("year", ""),
                text,
                annot_text,
            ])
            matches, mdd_queries = mdd_priority_matches(priority_rows, evidence_text)
            if args.pages > args.initial_pages and should_expand_to_fallback(flags, layout, titles, quote, annot_text, matches):
                text_path = (text_dir / stem).with_suffix(f".pages1-{args.pages}.txt")
                first, text, full_text, method, front_score, full_score, attempts, text_error = best_text_extraction(
                    pdf_path,
                    text_dir,
                    ocr_dir,
                    args.pages,
                    force=args.force_text,
                    min_front_score=min_score,
                    ocr_fallback=not args.no_ocr_fallback,
                )
                text_path.parent.mkdir(parents=True, exist_ok=True)
                text_path.write_text(text, encoding="utf-8", errors="replace")
                pages_examined = args.pages
                annot_text = annotation_clues(pdf_path, max_pages=min(args.pages, 10))
                lines = useful_lines(text)
                layout = extract_book_chapter_metadata(lines)
                titles = title_like_lines(lines)
                quote = distinctive_quote(text)
                clues = clue_lines(lines, [])
                evidence_text = " ".join([
                    row.get("title", ""),
                    row.get("authors", ""),
                    row.get("year", ""),
                    text,
                    annot_text,
                ])
                matches, mdd_queries = mdd_priority_matches(priority_rows, evidence_text)
            rendered = render_pages(pdf_path, evidence_dir, pages=args.render_pages)
            query = investigation_query(row, layout, titles, quote, annot_text, mdd_queries)
            links = search_links(query)
            rows_out.append({
                "status": "needs_investigation",
                "routed_filename": routed,
                "original_file": row.get("original_file", ""),
                "issue_flags": " | ".join(flags),
                "current_title": row.get("title", ""),
                "current_authors": row.get("authors", ""),
                "current_year": row.get("year", ""),
                "current_doi": row.get("doi", ""),
                "text_extraction_method": method,
                "front_matter_text_score": front_score,
                "full_text_score": full_score,
                "ocr_attempts": attempts,
                "pages_examined": pages_examined,
                "annotation_clues": annot_text,
                "mdd_priority_status": priority_status,
                "mdd_priority_matches": " | ".join(matches),
                "mdd_priority_queries": " | ".join(mdd_queries),
                "detected_book_title": layout.get("book_title", ""),
                "detected_editors": layout.get("editors", ""),
                "detected_chapter_title": layout.get("chapter_title", ""),
                "detected_chapter_author": layout.get("chapter_author", ""),
                "title_like_lines": " | ".join(titles[:6]),
                "citation_clues": " | ".join(clues[:8]),
                "distinctive_quote": quote,
                "recommended_query": query,
                **links,
                "first_pages_text": str(text_path),
                "rendered_page_1": rendered[0],
                "rendered_page_2": rendered[1],
                "recommended_action": "curate_metadata_then_embed",
            })
        except Exception as exc:
            rows_out.append({
                "status": "investigation_failed",
                "routed_filename": routed,
                "original_file": row.get("original_file", ""),
                "issue_flags": " | ".join(flags),
                "current_title": row.get("title", ""),
                "current_authors": row.get("authors", ""),
                "current_year": row.get("year", ""),
                "current_doi": row.get("doi", ""),
                "text_extraction_method": "",
                "front_matter_text_score": "",
                "full_text_score": "",
                "ocr_attempts": "",
                "pages_examined": "",
                "annotation_clues": "",
                "mdd_priority_status": priority_status,
                "mdd_priority_matches": "",
                "mdd_priority_queries": "",
                "recommended_action": f"{type(exc).__name__}: {exc}",
            })

    queue = output_dir / "metadata_investigation_queue.csv"
    timestamped = output_dir / f"{stamp}_metadata_investigation_queue.csv"
    latest = base / "metadata_enrichment" / args.run_folder / "latest_metadata_investigation_queue.csv"
    write_csv(queue, rows_out)
    write_csv(timestamped, rows_out)
    if not args.limit and not args.only_filename:
        write_csv(latest, rows_out)
    (output_dir / "summary.txt").write_text(
        "\n".join([
            f"Run folder: {args.run_folder}",
            f"Routed folder: {args.folder}",
            f"Initial pages: {args.initial_pages}",
            f"Fallback pages: {args.pages}",
            f"MDD priority status: {priority_status}",
            f"Queued records: {len(rows_out)}",
            f"Queue: {queue}",
            "",
        ]),
        encoding="utf-8",
    )
    print(queue)
    print(timestamped)
    if not args.limit and not args.only_filename:
        print(latest)
    print(f"Queued records: {len(rows_out)}")


if __name__ == "__main__":
    main()
