#!/usr/bin/env python3
import argparse
import csv
import hashlib
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path


DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
YEAR_RE = re.compile(r"\b(18|19|20)\d{2}\b")


def safe_name(path):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", path.stem).strip("_")


def clean_doi(value):
    return value.rstrip(").,;]").lower()


def normalize_doi(value):
    value = (value or "").strip().lower()
    value = re.sub(r"^https?://(dx\.)?doi\.org/", "", value)
    value = re.sub(r"^doi:\s*", "", value)
    return clean_doi(value)


def normalize_text(value):
    value = (value or "").casefold()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def author_tokens(value):
    normalized = normalize_text(value)
    stop = {"and", "the", "of", "jr", "ii", "iii", "iv"}
    return {token for token in normalized.split() if len(token) > 2 and token not in stop}


def file_hashes(path):
    md5 = hashlib.md5()
    sha256 = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            md5.update(chunk)
            sha256.update(chunk)
    return md5.hexdigest(), sha256.hexdigest()


def run_command(cmd, timeout=60):
    return subprocess.run(
        cmd,
        check=True,
        text=True,
        capture_output=True,
        timeout=timeout,
        errors="replace",
    )


def pdftotext(pdf_path, out_path, first_page=None, last_page=None, timeout=90):
    cmd = ["pdftotext"]
    if first_page is not None:
        cmd.extend(["-f", str(first_page)])
    if last_page is not None:
        cmd.extend(["-l", str(last_page)])
    cmd.extend([str(pdf_path), str(out_path)])
    run_command(cmd, timeout=timeout)
    return out_path.read_text(encoding="utf-8", errors="replace")


def cached_pdftotext(pdf_path, out_path, first_page=None, last_page=None, timeout=90, force=False):
    if force or not out_path.exists():
        return pdftotext(pdf_path, out_path, first_page=first_page, last_page=last_page, timeout=timeout)
    return out_path.read_text(encoding="utf-8", errors="replace")


def pdf_page_count(pdf_path):
    try:
        result = run_command(["pdfinfo", str(pdf_path)], timeout=30)
    except Exception:
        return ""
    for line in result.stdout.splitlines():
        if line.lower().startswith("pages:"):
            return line.split(":", 1)[1].strip()
    return ""


def load_batlit_refs(refs_path):
    by_doi = {}
    by_md5 = {}
    by_title = {}
    rows = 0

    if not refs_path.exists():
        return by_doi, by_md5, rows

    with refs_path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            rows += 1
            for key in ("doi", "alternativeDoi"):
                doi = normalize_doi(row.get(key))
                if doi:
                    by_doi.setdefault(doi, []).append(row)

            attachment_id = row.get("attachmentId") or ""
            md5_match = re.search(r"hash://md5/([a-f0-9]{32})", attachment_id, re.IGNORECASE)
            if md5_match:
                by_md5.setdefault(md5_match.group(1).lower(), []).append(row)

            title_key = normalize_text(row.get("title"))
            if title_key:
                by_title.setdefault(title_key, []).append(row)

    return by_doi, by_md5, by_title, rows


def plausible_title_and_authors(first_page_text):
    lines = [line.strip() for line in first_page_text.splitlines() if line.strip()]
    if not lines:
        return "", "", ""

    title_lines = []
    author_line = ""

    for index, line in enumerate(lines[:40]):
        lower = line.lower()
        if index < 3 and (YEAR_RE.search(line) or re.search(r"\d+\s*\(\d+\)", line)):
            continue
        if lower.startswith(("abstract", "summary", "introduction", "keywords", "key words")):
            break
        if "doi" in lower and DOI_RE.search(line):
            continue
        if len(title_lines) >= 1 and ("," in line or " and " in lower or " & " in line):
            author_line = line
            break
        title_lines.append(line)
        if len(title_lines) >= 6:
            break

    title = " ".join(title_lines).strip(" :")
    authors = re.sub(r"\d+", "", author_line)
    authors = authors.replace("&", "|")
    authors = re.sub(r"\s*\|\s*", " | ", authors)
    authors = re.sub(r"\s+", " ", authors).strip(" ,;")
    year_match = YEAR_RE.search(first_page_text[:5000])
    year = year_match.group(0) if year_match else ""
    return title, authors, year


def summarize_batlit_match(rows):
    if not rows:
        return "", "", "", "", "", ""
    first = rows[0]
    return (
        first.get("title", ""),
        first.get("authors", ""),
        first.get("date", ""),
        first.get("doi", ""),
        first.get("id", ""),
        first.get("attachmentId", ""),
    )


def year_from_date(value):
    match = YEAR_RE.search(value or "")
    return match.group(0) if match else ""


def likely_title_matches(title, authors, year, refs_by_title):
    title_key = normalize_text(title)
    if not title_key:
        return []

    matches = refs_by_title.get(title_key, [])
    if not matches:
        return []

    incoming_authors = author_tokens(authors)
    filtered = []
    for match in matches:
        ref_year = year_from_date(match.get("date"))
        year_ok = not year or not ref_year or year == ref_year
        ref_authors = author_tokens(match.get("authors"))
        author_ok = not incoming_authors or not ref_authors or bool(incoming_authors & ref_authors)
        if year_ok and author_ok:
            filtered.append(match)
    return filtered


BAT_TERMS = {
    "bat", "bats", "chiroptera", "chiropteran", "chiropterans", "microbat", "microbats",
    "pteropus", "rhinolophus", "hipposideros", "myotis", "pipistrellus",
    "miniopterus", "eptesicus", "nyctalus", "tadarida", "molossus",
    "artibeus", "carollia", "desmodus", "rousettus", "cynopterus",
    "megachiroptera", "microchiroptera", "vespertilionidae",
    "rhinolophidae", "pteropodidae", "molossidae", "phyllostomidae",
}

BAT_KEYWORD_RE = re.compile(r"\b(bat|bats|chiroptera|chiropteran|chiropterans|microbat|microbats)\b", re.IGNORECASE)

NON_BAT_TERMS = {
    "rodent", "rodents", "rodentia", "muridae", "murinae", "gerbillus",
    "apodemus", "eliomys", "dormouse", "dormice", "squirrel", "squirrels",
    "sciurus", "vole", "voles", "arvicola", "mouse", "mice", "rat", "rats",
    "hyena", "hyaena", "fox", "cat", "felis", "marten", "badger", "carnivore",
    "carnivora", "owl", "bird", "birds", "duck", "tourism",
}


def bat_relevance(text):
    tokens = set(normalize_text(text).split())
    bat_hits = sorted(tokens & BAT_TERMS)
    non_bat_hits = sorted(tokens & NON_BAT_TERMS)
    keyword_hits = sorted({match.group(0).casefold() for match in BAT_KEYWORD_RE.finditer(text or "")})
    if bat_hits or keyword_hits:
        hits = sorted(set(bat_hits) | set(keyword_hits))
        return "bat_relevant", "bat_terms:" + "|".join(hits[:8])
    if non_bat_hits:
        return "likely_non_bat", "non_bat_terms:" + "|".join(non_bat_hits[:8])
    return "unknown", ""


def decide(hash_matches, own_doi_matches, title_matches, text_error, relevance_status):
    if hash_matches:
        return "duplicate", "exact_md5_hash_match"
    if own_doi_matches:
        return "duplicate", "front_matter_doi_match"
    if title_matches:
        return "likely_duplicate", "exact_title_author_year_match"
    if text_error:
        return "manual_review", "text_extraction_failed"
    if relevance_status == "likely_non_bat":
        return "non_bat_review", "likely_non_bat_terms"
    return "new_literature", "no_hash_or_front_matter_doi_match"


def add_incoming_batch_duplicate_flags(rows):
    by_md5 = {}
    by_doi = {}
    by_title = {}

    for row in rows:
        row["incoming_batch_duplicate_status"] = ""
        row["incoming_batch_duplicate_reason"] = ""
        row["incoming_batch_primary_file"] = ""
        row["incoming_batch_match_files"] = ""

        md5 = row.get("md5")
        if md5:
            by_md5.setdefault(md5, []).append(row)

        for doi in (row.get("front_matter_dois") or "").split("|"):
            doi = normalize_doi(doi)
            if doi:
                by_doi.setdefault(doi, []).append(row)

        title_key = normalize_text(row.get("incoming_title"))
        if title_key:
            author_key = " ".join(sorted(author_tokens(row.get("incoming_authors"))))
            year_key = row.get("incoming_year_guess") or ""
            by_title.setdefault((title_key, author_key, year_key), []).append(row)

    def mark_group(group, reason):
        if len(group) < 2:
            return
        ordered = sorted(group, key=lambda item: item.get("file", ""))
        primary = ordered[0]
        files = " | ".join(row.get("file", "") for row in ordered)
        for row in ordered:
            if row["incoming_batch_duplicate_status"]:
                continue
            row["incoming_batch_duplicate_status"] = (
                "primary_in_batch" if row is primary else "duplicate_in_batch"
            )
            row["incoming_batch_duplicate_reason"] = reason
            row["incoming_batch_primary_file"] = primary.get("file", "")
            row["incoming_batch_match_files"] = files

            if row is primary:
                continue
            if row.get("batlit_match_scope") == "batlit_corpus":
                continue
            if row.get("decision") not in {"new_literature", "manual_review", "non_bat_review"}:
                continue
            if reason in {"exact_md5_hash_match", "front_matter_doi_match"}:
                row["decision"] = "duplicate"
            else:
                row["decision"] = "likely_duplicate"
            row["decision_reason"] = f"incoming_batch_{reason}"

    for groups in (by_md5, by_doi, by_title):
        for group in groups.values():
            if groups is by_title:
                mark_group(group, "exact_title_author_year_match")
            elif groups is by_doi:
                mark_group(group, "front_matter_doi_match")
            else:
                mark_group(group, "exact_md5_hash_match")


def write_csv(path, fieldnames, rows):
    try:
        handle = path.open("w", newline="", encoding="utf-8")
    except PermissionError:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = path.with_name(f"{path.stem}_{stamp}{path.suffix}")
        handle = path.open("w", newline="", encoding="utf-8")
    with handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def find_pdfs(incoming_dir):
    return sorted(
        path for path in incoming_dir.iterdir()
        if path.is_file() and path.suffix.lower() == ".pdf"
    )


def main():
    parser = argparse.ArgumentParser(description="Run BatLit pre-Zotero dedupe screening.")
    parser.add_argument("--base", default=".", help="batlit-dedupe folder; defaults to current directory")
    parser.add_argument("--limit", type=int, default=None, help="process only the first N PDFs")
    parser.add_argument("--force-text", action="store_true", help="refresh cached extracted text")
    args = parser.parse_args()

    base = Path(args.base).resolve()
    incoming_dir = base / "incoming"
    refs_path = base / "index" / "refs.csv"
    reports_dir = base / "reports"
    text_dir = base / "work" / "text_first3"
    full_text_dir = base / "work" / "text_full_keyword_scan"
    reports_dir.mkdir(parents=True, exist_ok=True)
    text_dir.mkdir(parents=True, exist_ok=True)
    full_text_dir.mkdir(parents=True, exist_ok=True)

    refs_by_doi, refs_by_md5, refs_by_title, ref_count = load_batlit_refs(refs_path)
    pdfs = find_pdfs(incoming_dir)
    if args.limit is not None:
        pdfs = pdfs[: args.limit]

    dedupe_rows = []
    zotero_rows = []

    total = len(pdfs)
    print(f"Loaded {ref_count} BatLit refs; screening {total} incoming PDFs.", file=sys.stderr)

    for index, pdf_path in enumerate(pdfs, start=1):
        if index == 1 or index % 25 == 0 or index == total:
            print(f"[{index}/{total}] {pdf_path.name}", file=sys.stderr, flush=True)

        md5, sha256 = file_hashes(pdf_path)
        size_bytes = pdf_path.stat().st_size
        page_count = pdf_page_count(pdf_path)
        hash_matches = refs_by_md5.get(md5, [])

        cache_base = text_dir / safe_name(pdf_path)
        first_page_path = cache_base.with_suffix(".page1.txt")
        first3_path = cache_base.with_suffix(".pages1-3.txt")
        full_text_path = (full_text_dir / safe_name(pdf_path)).with_suffix(".full.txt")
        text_error = ""

        try:
            first_page_text = cached_pdftotext(
                pdf_path, first_page_path, first_page=1, last_page=1, force=args.force_text
            )
            first3_text = cached_pdftotext(
                pdf_path, first3_path, first_page=1, last_page=3, force=args.force_text
            )
            full_keyword_text = cached_pdftotext(
                pdf_path, full_text_path, timeout=180, force=args.force_text
            )
        except Exception as exc:
            first_page_text = ""
            first3_text = ""
            full_keyword_text = ""
            text_error = f"{type(exc).__name__}: {exc}"

        title, authors, year = plausible_title_and_authors(first_page_text)
        front_matter_dois = sorted({clean_doi(match.group(0)) for match in DOI_RE.finditer(first3_text)})
        own_doi_matches = []
        for doi in front_matter_dois:
            own_doi_matches.extend(refs_by_doi.get(doi, []))

        relevance_status, relevance_reason = bat_relevance(" ".join([
            pdf_path.name,
            title,
            authors,
            full_keyword_text,
        ]))
        title_matches = likely_title_matches(title, authors, year, refs_by_title)
        decision, decision_reason = decide(hash_matches, own_doi_matches, title_matches, text_error, relevance_status)
        match_rows = hash_matches or own_doi_matches or title_matches
        (
            batlit_title,
            batlit_authors,
            batlit_date,
            batlit_doi,
            batlit_zotero_id,
            batlit_attachment_id,
        ) = summarize_batlit_match(match_rows)

        dedupe_rows.append({
            "decision": decision,
            "decision_reason": decision_reason,
            "batlit_match_scope": "batlit_corpus" if match_rows else "",
            "file": pdf_path.name,
            "size_bytes": size_bytes,
            "page_count": page_count,
            "md5": md5,
            "sha256": sha256,
            "incoming_title": title,
            "incoming_authors": authors,
            "incoming_year_guess": year,
            "front_matter_dois": " | ".join(front_matter_dois),
            "batlit_match_count": len(match_rows),
            "batlit_title": batlit_title,
            "batlit_authors": batlit_authors,
            "batlit_year_or_date": batlit_date,
            "batlit_doi": batlit_doi,
            "batlit_zotero_id": batlit_zotero_id,
            "batlit_attachment_id": batlit_attachment_id,
            "bat_relevance_status": relevance_status,
            "bat_relevance_reason": relevance_reason,
            "text_error": text_error,
        })

    add_incoming_batch_duplicate_flags(dedupe_rows)

    for row in dedupe_rows:
        if row["decision"] in {"new_literature", "manual_review"}:
            front_matter_dois = [
                normalize_doi(doi) for doi in (row.get("front_matter_dois") or "").split("|")
                if normalize_doi(doi)
            ]
            zotero_rows.append({
                "filename": row["file"],
                "title": row.get("incoming_title", ""),
                "creators": row.get("incoming_authors", ""),
                "date": row.get("incoming_year_guess", ""),
                "DOI": front_matter_dois[0] if front_matter_dois else "",
                "itemType": "journalArticle",
                "publicationTitle": "",
                "pages": "",
                "volume": "",
                "issue": "",
                "abstractNote": "",
                "tags": "batlit-prezotero",
                "notes": f"pre_zotero_decision={row['decision']}; reason={row['decision_reason']}; md5={row['md5']}",
            })

    dedupe_fields = [
        "decision",
        "decision_reason",
        "batlit_match_scope",
        "incoming_batch_duplicate_status",
        "incoming_batch_duplicate_reason",
        "incoming_batch_primary_file",
        "incoming_batch_match_files",
        "file",
        "size_bytes",
        "page_count",
        "md5",
        "sha256",
        "incoming_title",
        "incoming_authors",
        "incoming_year_guess",
        "front_matter_dois",
        "batlit_match_count",
        "batlit_title",
        "batlit_authors",
        "batlit_year_or_date",
        "batlit_doi",
        "batlit_zotero_id",
        "batlit_attachment_id",
        "bat_relevance_status",
        "bat_relevance_reason",
        "text_error",
    ]
    zotero_fields = [
        "filename",
        "title",
        "creators",
        "date",
        "DOI",
        "itemType",
        "publicationTitle",
        "pages",
        "volume",
        "issue",
        "abstractNote",
        "tags",
        "notes",
    ]

    dedupe_path = write_csv(reports_dir / "dedupe_report.csv", dedupe_fields, dedupe_rows)
    zotero_path = write_csv(reports_dir / "zotero_metadata_staging.csv", zotero_fields, zotero_rows)

    counts = {}
    for row in dedupe_rows:
        counts[row["decision"]] = counts.get(row["decision"], 0) + 1
    summary_path = reports_dir / "dedupe_summary.txt"
    summary_lines = [
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"BatLit refs loaded: {ref_count}",
        f"PDFs screened: {len(dedupe_rows)}",
        "",
        "Decisions:",
    ]
    for key in sorted(counts):
        summary_lines.append(f"  {key}: {counts[key]}")
    summary_lines.extend([
        "",
        f"Dedupe report: {dedupe_path.name}",
        f"Zotero staging report: {zotero_path.name}",
    ])
    summary_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
    print(summary_path)


if __name__ == "__main__":
    main()
