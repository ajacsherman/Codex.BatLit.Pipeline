#!/usr/bin/env python3
"""Scan routed BatLit PDFs for taxonomic citation clues and embed resolved metadata.

This script is intentionally conservative. It can create a clue spreadsheet for
manual lookup from OCR/text evidence, and it can embed metadata only from rows
marked as high confidence or explicitly approved in a resolved metadata CSV.
"""

import argparse
import csv
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus


YEAR_RE = re.compile(r"\b(17|18|19|20)\d{2}\b")
BINOMIAL_RE = re.compile(r"\b([A-Z][a-z]{2,})\s+([a-z][a-z-]{2,})\b")
NOISE_RE = re.compile(
    r"(reprint collection|dept\.? of mammal|american museum|a\.?\s*m\.?\s*n\.?\s*h\.?|"
    r"jstor|downloaded|copyright|biodiversity heritage library)",
    re.I,
)

BAT_GENERA = {
    "acerodon", "anoura", "artibeus", "barbastella", "carollia", "chaerephon",
    "chiromeles", "chiroderma", "choeronycteris", "corynorhinus", "desmodus",
    "diaemus", "eidolon", "eptesicus", "eumops", "furipterus", "glossophaga",
    "hipposideros", "lasiurus", "leptonycteris", "lonchophylla", "macrotus",
    "megaderma", "mesophylla", "micronycteris", "miniopterus", "molossus",
    "mormoops", "myotis", "mystacina", "natalus", "noctilio", "nyctalus",
    "nycteris", "nycticeius", "nyctinomops", "otonycteris", "perimyotis",
    "phyllostomus", "pipistrellus", "platyrrhinus", "plecotus", "pteronotus",
    "pteropus", "rhinolophus", "saccopteryx", "sturnira", "tadarida",
    "taphozous", "thyroptera", "tonatia", "vespadelus", "vespertilio",
}

EPITHET_STOPWORDS = {
    "are", "aux", "avec", "dans", "des", "du", "elle", "for", "from", "genre",
    "les", "malgache", "near", "non", "par", "pour", "sont", "sur", "the",
    "trouve", "und", "with",
}

FIELDNAMES = [
    "status",
    "routed_filename",
    "original_file",
    "current_title",
    "current_authors",
    "current_year",
    "current_doi",
    "detected_book_title",
    "detected_editors",
    "detected_chapter_title",
    "detected_chapter_author",
    "distinctive_quote",
    "candidate_taxon",
    "taxon_status",
    "mdd_accepted_name",
    "mdd_authority",
    "mdd_authority_link",
    "detected_years",
    "title_like_lines",
    "citation_clues",
    "recommended_query",
    "google_scholar_search",
    "crossref_search",
    "openalex_search",
    "bhl_search",
    "internet_archive_search",
    "manual_review_note",
]

RESOLVED_FIELDS = [
    "apply_metadata",
    "confidence",
    "routed_filename",
    "title",
    "authors",
    "year",
    "doi",
    "journal",
    "volume",
    "issue",
    "pages",
    "issn",
    "source_url",
    "metadata_source",
    "notes",
]


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def lower_columns(row):
    return {str(k or "").strip().lower(): v for k, v in row.items()}


def find_col(row, names):
    lowered = lower_columns(row)
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()]
    return ""


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def windows_to_wsl_path(path):
    value = str(Path(path).resolve())
    match = re.match(r"^([A-Za-z]):\\(.*)$", value)
    if not match:
        return value.replace("\\", "/")
    drive = match.group(1).lower()
    rest = match.group(2).replace("\\", "/")
    return f"/mnt/{drive}/{rest}"


def run_pdftotext(pdf_path, text_path, pages, force=False):
    if text_path.exists() and not force:
        return text_path.read_text(encoding="utf-8", errors="replace")

    text_path.parent.mkdir(parents=True, exist_ok=True)
    pdftotext = shutil.which("pdftotext")
    if pdftotext:
        cmd = [pdftotext, "-f", "1", "-l", str(pages), str(pdf_path), str(text_path)]
    elif os.name == "nt" and shutil.which("wsl"):
        pdf_wsl = windows_to_wsl_path(pdf_path)
        text_wsl = windows_to_wsl_path(text_path)
        script = (
            "pdftotext -f 1 -l {pages} {pdf} {text}"
        ).format(
            pages=pages,
            pdf=subprocess.list2cmdline([pdf_wsl]),
            text=subprocess.list2cmdline([text_wsl]),
        )
        cmd = ["wsl", "bash", "-lc", script]
    else:
        raise RuntimeError("pdftotext not found. Run in WSL or install Poppler.")

    subprocess.run(cmd, check=True, capture_output=True, text=True, errors="replace")
    return text_path.read_text(encoding="utf-8", errors="replace")


def load_mdd(species_csv="", synonyms_csv=""):
    accepted = {}
    synonyms = {}
    if species_csv and Path(species_csv).exists():
        for row in read_csv(Path(species_csv)):
            order = clean(find_col(row, ["order", "Order"])).casefold()
            sci = clean(find_col(row, ["sciName", "scientificName", "species", "acceptedName"]))
            if not sci:
                genus = clean(find_col(row, ["genus"]))
                epithet = clean(find_col(row, ["specificEpithet", "speciesEpithet"]))
                sci = clean(f"{genus} {epithet}")
            if "chiroptera" not in order and sci.split(" ", 1)[0].casefold() not in BAT_GENERA:
                continue
            key = sci.casefold()
            accepted[key] = {
                "accepted": sci,
                "authority": clean(find_col(row, ["authoritySpecies", "authority", "speciesAuthority"])),
                "link": clean(find_col(row, ["authoritySpeciesLink", "authorityLink", "sourceLink", "url"])),
            }
    if synonyms_csv and Path(synonyms_csv).exists():
        for row in read_csv(Path(synonyms_csv)):
            synonym = clean(find_col(row, ["synonym", "synName", "scientificName", "species"]))
            accepted_name = clean(find_col(row, ["acceptedName", "sciName", "validName"]))
            if synonym:
                synonyms[synonym.casefold()] = accepted_name
    return accepted, synonyms


def useful_lines(text):
    lines = [clean(line) for line in text.splitlines()]
    return [line for line in lines if len(line) >= 6]


def title_like_lines(lines):
    picks = []
    for line in lines[:120]:
        if NOISE_RE.search(line):
            continue
        letters = sum(char.isalpha() for char in line)
        if letters < 8 or len(line) > 170:
            continue
        upper_ratio = sum(char.isupper() for char in line if char.isalpha()) / max(letters, 1)
        if upper_ratio > 0.45 or any(term in line.lower() for term in ["description", "catalogue", "chiropter", "bat", "bats", "mammal"]):
            picks.append(line)
        if len(picks) >= 5:
            break
    return picks


def extract_book_chapter_metadata(lines):
    text = "\n".join(lines[:180])
    book_title = ""
    editors = []
    chapter_title = ""
    chapter_author = ""

    if re.search(r"Natural\s+\S{0,12}History\s+of\s+Vampire\s+Bats", text, re.I):
        book_title = "Natural History of Vampire Bats"

    for idx, line in enumerate(lines[:80]):
        if re.fullmatch(r"Editors?", line, flags=re.I):
            for candidate in lines[idx + 1: idx + 18]:
                if re.search(r"Office|Institute|University|Museum|Service|Associate|Washington|Florida|Germany|York|and\b", candidate):
                    continue
                if re.search(r"\b[A-Z][a-z]+\s+[A-Z]\.\s+[A-Z][a-z]+\b", candidate):
                    if candidate not in editors and not re.search(r"Office|Institute|University|Museum|Service", candidate):
                        editors.append(candidate)
                if len(editors) >= 3:
                    break

    for idx, line in enumerate(lines[:160]):
        if re.match(r"Chapter\s+\d+", line, flags=re.I):
            heading_parts = []
            for candidate in lines[idx + 1: idx + 8]:
                if re.search(r"TABLE OF CONTENTS", candidate, re.I):
                    break
                if re.search(r"\b[A-Z][a-z]+\s+[A-Z]\.\s+[A-Z][a-z]+\b", candidate):
                    chapter_author = clean(candidate)
                    break
                if len(candidate) >= 8 and not re.search(r"Chapter|^\d+$", candidate, re.I):
                    if candidate.isupper() or re.search(r"systematics|distributio|description|biology|ecology", candidate, re.I):
                        heading_parts.append(candidate)
            heading = clean(" ".join(heading_parts))
            if re.search(r"systematics", heading, re.I) and re.search(r"distributio", heading, re.I):
                chapter_title = "Systematics and distribution"
            elif heading:
                chapter_title = clean(heading.title() if heading.isupper() else heading)
            if chapter_author:
                break

    return {
        "book_title": book_title,
        "editors": " | ".join(editors),
        "chapter_title": chapter_title,
        "chapter_author": chapter_author,
    }


def clue_lines(lines, taxa):
    terms = ["sp. nov", "n. sp", "new species", "type locality", "holotype", "lectotype", "description", "chiropter", "bat"]
    taxon_terms = [taxon.lower() for taxon in taxa]
    picks = []
    for line in lines:
        low = line.lower()
        if any(term in low for term in terms) or any(taxon in low for taxon in taxon_terms):
            if not NOISE_RE.search(line):
                picks.append(line)
        if len(picks) >= 8:
            break
    return picks


def distinctive_quote(text):
    compact = clean(text)
    compact = re.sub(r"\s+([,.;:])", r"\1", compact)
    sentences = re.split(r"(?<=[.!?])\s+", compact)
    best = ""
    for sentence in sentences:
        words = re.findall(r"[A-Za-z][A-Za-z'-]+", sentence)
        if not 16 <= len(words) <= 55:
            continue
        low = sentence.lower()
        if any(term in low for term in ["table of contents", "reprint collection", "references"]):
            continue
        score = len(set(word.lower() for word in words))
        if any(term in low for term in ["vampire", "chiropter", "species", "genus", "described", "taxonomic"]):
            score += 20
        best_score = len(set(re.findall(r"[A-Za-z][A-Za-z'-]+", best.lower()))) if best else -1
        if score > best_score:
            best = sentence
    return best[:700]


def make_distinctive_query(row, quote):
    chapter_author = clean(row.get("detected_chapter_author"))
    chapter_title = clean(row.get("detected_chapter_title"))
    book_title = clean(row.get("detected_book_title"))
    pieces = [chapter_author, chapter_title, book_title, f"\"{quote}\"" if quote else ""]
    return clean(" ".join(piece for piece in pieces if piece))[:700]


def candidate_taxa(text, accepted):
    found = []
    seen = set()
    for genus, epithet in BINOMIAL_RE.findall(text):
        if epithet.casefold() in EPITHET_STOPWORDS:
            continue
        name = f"{genus} {epithet}"
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        if genus.casefold() in BAT_GENERA or key in accepted:
            found.append(name)
    return found[:12]


def taxon_match(name, accepted, synonyms):
    if not accepted and not synonyms:
        return "mdd_unavailable", "", "", ""
    key = name.casefold()
    if key in accepted:
        hit = accepted[key]
        return "mdd_exact_accepted", hit["accepted"], hit["authority"], hit["link"]
    if key in synonyms:
        accepted_name = synonyms[key]
        hit = accepted.get(accepted_name.casefold(), {})
        return "mdd_synonym", accepted_name, hit.get("authority", ""), hit.get("link", "")
    return "candidate_not_in_mdd", "", "", ""


def make_links(query):
    q = quote_plus(query)
    return {
        "google_scholar_search": f"https://scholar.google.com/scholar?q={q}" if query else "",
        "crossref_search": f"https://search.crossref.org/?q={q}" if query else "",
        "openalex_search": f"https://openalex.org/works?page=1&filter=default.search%3A{q}" if query else "",
        "bhl_search": f"https://www.biodiversitylibrary.org/search?searchTerm={q}" if query else "",
        "internet_archive_search": f"https://archive.org/search?query={q}" if query else "",
    }


def make_query(row, taxon, title_lines, years):
    chapter_title = clean(row.get("detected_chapter_title"))
    chapter_author = clean(row.get("detected_chapter_author"))
    book_title = clean(row.get("detected_book_title"))
    if chapter_title and chapter_author:
        pieces = [chapter_author, chapter_title, book_title]
        return clean(" ".join(piece for piece in pieces if piece))[:450]
    author = clean(row.get("authors"))
    title = clean(row.get("title"))
    year = clean(row.get("year")) or (years[0] if years else "")
    pieces = [taxon, author.split("|", 1)[0], year]
    if title and not NOISE_RE.search(title):
        pieces.append(title)
    elif title_lines:
        pieces.append(title_lines[0])
    return clean(" ".join(piece for piece in pieces if piece))[:450]


def row_quality(row):
    title = clean(row.get("title"))
    authors = clean(row.get("authors"))
    year = clean(row.get("year"))
    if not title or NOISE_RE.search(title) or len(title) < 12:
        return "needs_metadata"
    if not authors or NOISE_RE.search(authors):
        return "needs_metadata"
    if not YEAR_RE.fullmatch(year or ""):
        return "needs_metadata"
    return "metadata_present"


def embed_pdf_metadata(pdf_path, metadata):
    try:
        from pypdf import PdfReader, PdfWriter
    except Exception as exc:
        raise RuntimeError("pypdf is required for embedding metadata") from exc

    reader = PdfReader(str(pdf_path))
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    existing = {key: str(value) for key, value in dict(reader.metadata or {}).items() if key.startswith("/")}
    updates = {
        "/Title": metadata.get("title", ""),
        "/Author": metadata.get("authors", ""),
        "/Subject": "BatLit resolved bibliographic metadata for Zotero import",
        "/Keywords": "; ".join(filter(None, ["BatLit", "AMNH", "resolved-metadata", metadata.get("doi", "")])),
        "/Creator": "BatLit pre-Zotero deduplication pipeline",
        "/Producer": "BatLit pre-Zotero deduplication pipeline via pypdf",
        "/DOI": metadata.get("doi", ""),
        "/BatLitYear": metadata.get("year", ""),
        "/BatLitJournal": metadata.get("journal", ""),
        "/BatLitVolume": metadata.get("volume", ""),
        "/BatLitIssue": metadata.get("issue", ""),
        "/BatLitPages": metadata.get("pages", ""),
        "/BatLitISSN": metadata.get("issn", ""),
        "/BatLitMetadataSource": metadata.get("metadata_source", ""),
        "/BatLitMetadataSourceURL": metadata.get("source_url", ""),
        "/BatLitMetadataConfidence": metadata.get("confidence", ""),
    }
    existing.update({key: clean(value) for key, value in updates.items() if clean(value)})
    writer.add_metadata(existing)
    tmp = pdf_path.with_suffix(pdf_path.suffix + ".tmp")
    with tmp.open("wb") as handle:
        writer.write(handle)
    tmp.replace(pdf_path)


def apply_resolved_metadata(folder, resolved_csv, min_confidence):
    rows = read_csv(resolved_csv)
    report = []
    for row in rows:
        apply_flag = clean(row.get("apply_metadata")).casefold() in {"yes", "true", "1", "apply", "embedded"}
        confidence = clean(row.get("confidence")).casefold()
        allowed = apply_flag or confidence in {"high", "curated", "verified"}
        if not allowed:
            report.append({"routed_filename": row.get("routed_filename", ""), "status": "skipped_not_approved", "error": ""})
            continue
        if min_confidence and confidence not in {"high", "curated", "verified"}:
            report.append({"routed_filename": row.get("routed_filename", ""), "status": "skipped_low_confidence", "error": ""})
            continue
        pdf_path = folder / clean(row.get("routed_filename"))
        try:
            embed_pdf_metadata(pdf_path, row)
            report.append({"routed_filename": pdf_path.name, "status": "embedded", "error": ""})
        except Exception as exc:
            report.append({"routed_filename": pdf_path.name, "status": "failed", "error": f"{type(exc).__name__}: {exc}"})
    return report


def main():
    parser = argparse.ArgumentParser(description="Create MDD/taxon citation clues and embed verified metadata into routed PDFs.")
    parser.add_argument("--base", default=".", help="batlit-dedupe folder")
    parser.add_argument("--run-folder", required=True, help="processed_runs folder name")
    parser.add_argument("--folder", default="new_literature", help="routed folder to scan")
    parser.add_argument("--pages", type=int, default=10, help="leading pages to scan")
    parser.add_argument("--mdd-species-csv", default="", help="optional MDD species CSV")
    parser.add_argument("--mdd-synonyms-csv", default="", help="optional MDD synonym CSV")
    parser.add_argument("--force-text", action="store_true", help="refresh cached extracted text")
    parser.add_argument("--resolved-csv", default="", help="optional curated metadata CSV to embed")
    parser.add_argument("--apply", action="store_true", help="embed approved rows from --resolved-csv")
    parser.add_argument("--allow-non-high-confidence", action="store_true", help="embed rows approved by apply_metadata even if confidence is not high/curated/verified")
    args = parser.parse_args()

    base = Path(args.base).resolve()
    folder = base / "processed_runs" / args.run_folder / args.folder
    bibliography = folder / "bibliography.csv"
    if not bibliography.exists():
        raise SystemExit(f"Missing bibliography: {bibliography}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = base / "metadata_enrichment" / args.run_folder / f"{stamp}_mdd_citation_clues"
    text_dir = base / "work" / "mdd_citation_text" / args.run_folder / args.folder
    accepted, synonyms = load_mdd(args.mdd_species_csv, args.mdd_synonyms_csv)
    mdd_status = "loaded" if accepted else "mdd_unavailable"

    clue_rows = []
    template_rows = []
    for row in read_csv(bibliography):
        routed = clean(row.get("routed_filename"))
        pdf_path = folder / routed
        status = row_quality(row)
        try:
            text = run_pdftotext(pdf_path, (text_dir / Path(routed).stem).with_suffix(f".pages1-{args.pages}.txt"), args.pages, args.force_text)
            lines = useful_lines(text)
            layout = extract_book_chapter_metadata(lines)
            quote = distinctive_quote(text)
            years = sorted(set(YEAR_RE.findall(text)))
            years = [match.group(0) if hasattr(match, "group") else "".join(match) for match in YEAR_RE.finditer(text)]
            years = sorted(set(years))
            titles = title_like_lines(lines)
            taxa = candidate_taxa(text, accepted)
            if not taxa:
                taxa = [""]
            for taxon in taxa:
                taxon_status, accepted_name, authority, authority_link = (
                    taxon_match(taxon, accepted, synonyms) if taxon else (mdd_status, "", "", "")
                )
                clues = clue_lines(lines, [taxon] if taxon else [])
                query_row = dict(row)
                query_row.update({
                    "detected_book_title": layout["book_title"],
                    "detected_chapter_title": layout["chapter_title"],
                    "detected_chapter_author": layout["chapter_author"],
                })
                query = make_query(query_row, taxon, titles, years)
                if layout["book_title"] and layout["chapter_author"] and quote:
                    query = make_distinctive_query(query_row, quote)
                links = make_links(query)
                clue_rows.append({
                    "status": status,
                    "routed_filename": routed,
                    "original_file": row.get("original_file", ""),
                    "current_title": row.get("title", ""),
                    "current_authors": row.get("authors", ""),
                    "current_year": row.get("year", ""),
                    "current_doi": row.get("doi", ""),
                    "detected_book_title": layout["book_title"],
                    "detected_editors": layout["editors"],
                    "detected_chapter_title": layout["chapter_title"],
                    "detected_chapter_author": layout["chapter_author"],
                    "distinctive_quote": quote,
                    "candidate_taxon": taxon,
                    "taxon_status": taxon_status,
                    "mdd_accepted_name": accepted_name,
                    "mdd_authority": authority,
                    "mdd_authority_link": authority_link,
                    "detected_years": " | ".join(years[:8]),
                    "title_like_lines": " | ".join(titles[:5]),
                    "citation_clues": " | ".join(clues[:8]),
                    "recommended_query": query,
                    **links,
                    "manual_review_note": "" if accepted else "Place MDD species/synonym CSVs under batlit-dedupe/index/mdd/ and rerun for exact MDD matching.",
                })
            template_rows.append({
                "apply_metadata": "",
                "confidence": "",
                "routed_filename": routed,
                "title": "",
                "authors": "",
                "year": "",
                "doi": "",
                "journal": "",
                "volume": "",
                "issue": "",
                "pages": "",
                "issn": "",
                "source_url": "",
                "metadata_source": "",
                "notes": "",
            })
        except Exception as exc:
            clue_rows.append({
                "status": "text_failed",
                "routed_filename": routed,
                "original_file": row.get("original_file", ""),
                "current_title": row.get("title", ""),
                "current_authors": row.get("authors", ""),
                "current_year": row.get("year", ""),
                "current_doi": row.get("doi", ""),
                "detected_book_title": "",
                "detected_editors": "",
                "detected_chapter_title": "",
                "detected_chapter_author": "",
                "distinctive_quote": "",
                "candidate_taxon": "",
                "taxon_status": mdd_status,
                "mdd_accepted_name": "",
                "mdd_authority": "",
                "mdd_authority_link": "",
                "detected_years": "",
                "title_like_lines": "",
                "citation_clues": "",
                "recommended_query": "",
                **make_links(""),
                "manual_review_note": f"{type(exc).__name__}: {exc}",
            })

    clue_path = output_dir / "mdd_citation_clues.csv"
    template_path = output_dir / "metadata_to_embed_template.csv"
    write_csv(clue_path, FIELDNAMES, clue_rows)
    write_csv(output_dir / f"{stamp}_mdd_citation_clues.csv", FIELDNAMES, clue_rows)
    write_csv(base / "metadata_enrichment" / args.run_folder / "latest_mdd_citation_clues.csv", FIELDNAMES, clue_rows)
    write_csv(template_path, RESOLVED_FIELDS, template_rows)

    embed_report = []
    if args.apply:
        if not args.resolved_csv:
            raise SystemExit("--apply requires --resolved-csv so only verified metadata is embedded.")
        embed_report = apply_resolved_metadata(
            folder,
            Path(args.resolved_csv),
            min_confidence=not args.allow_non_high_confidence,
        )
        write_csv(output_dir / "metadata_embedding_from_mdd_clues_report.csv", ["routed_filename", "status", "error"], embed_report)

    summary_path = output_dir / "summary.txt"
    summary_path.write_text(
        "\n".join([
            f"Run folder: {args.run_folder}",
            f"Routed folder: {args.folder}",
            f"Pages scanned: {args.pages}",
            f"MDD status: {mdd_status}",
            f"PDF clue rows: {len(clue_rows)}",
            f"Embedding rows: {len(embed_report)}",
            f"Clue CSV: {clue_path}",
            f"Metadata template: {template_path}",
        ]) + "\n",
        encoding="utf-8",
    )
    print(summary_path)
    print(clue_path)
    print(template_path)


if __name__ == "__main__":
    main()
