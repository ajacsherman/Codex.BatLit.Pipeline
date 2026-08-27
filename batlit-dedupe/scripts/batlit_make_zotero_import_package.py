#!/usr/bin/env python3
"""Create a Zotero import package from curated BatLit metadata and PDFs."""

from __future__ import annotations

import argparse
import csv
import re
import shutil
from datetime import datetime
from pathlib import Path

from pypdf import PdfReader


READY_CONFIDENCE = {"curated", "verified", "high"}


def clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def split_people(value: str) -> list[str]:
    if ";" in value:
        parts = value.split(";")
    elif "|" in value:
        parts = value.split("|")
    else:
        parts = [value]
    return [clean(part) for part in parts if clean(part)]


def page_start_end(value: str) -> tuple[str, str]:
    text = clean(value)
    match = re.match(r"^([A-Za-z]*\d+)\s*[-–]\s*([A-Za-z]*\d+)$", text)
    if match:
        return match.group(1), match.group(2)
    return text, ""


def ris_type(row: dict[str, str]) -> str:
    journal = clean(row.get("journal"))
    pages = clean(row.get("pages"))
    title = clean(row.get("title")).lower()
    if journal:
        return "JOUR"
    if pages.endswith("pp.") or "book" in clean(row.get("abstract")).lower() or "handbook" in title:
        return "BOOK"
    return "CHAP"


def bib_type(row: dict[str, str]) -> str:
    ty = ris_type(row)
    if ty == "JOUR":
        return "article"
    if ty == "BOOK":
        return "book"
    return "incollection"


def cite_key(row: dict[str, str], existing: set[str]) -> str:
    authors = split_people(clean(row.get("authors")))
    last = "unknown"
    if authors:
        last = re.split(r"\s+", authors[0].replace(",", " "))[0].lower()
    year = clean(row.get("year")) or "nd"
    title_words = re.findall(r"[A-Za-z0-9]+", clean(row.get("title")).lower())
    stem = "_".join([last, year] + title_words[:3])
    stem = re.sub(r"[^a-z0-9_]+", "", stem) or f"batlit_{year}"
    key = stem
    counter = 2
    while key in existing:
        key = f"{stem}_{counter}"
        counter += 1
    existing.add(key)
    return key


def write_ris(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        for row in rows:
            filename = clean(row.get("enhanced_filename")) or clean(row.get("filename"))
            start_page, end_page = page_start_end(clean(row.get("pages")))
            journal = clean(row.get("journal"))
            handle.write(f"TY  - {ris_type(row)}\n")
            write_ris_line(handle, "T1", row.get("title"))
            for author in split_people(clean(row.get("authors"))):
                write_ris_line(handle, "AU", author)
            write_ris_line(handle, "PY", row.get("year"))
            write_ris_line(handle, "Y1", row.get("year"))
            write_ris_line(handle, "T2", journal)
            write_ris_line(handle, "JF", journal)
            write_ris_line(handle, "JO", journal)
            write_ris_line(handle, "JA", journal)
            write_ris_line(handle, "VL", row.get("volume"))
            write_ris_line(handle, "IS", row.get("issue"))
            write_ris_line(handle, "SP", start_page)
            write_ris_line(handle, "EP", end_page)
            write_ris_line(handle, "DO", row.get("doi"))
            write_ris_line(handle, "SN", row.get("issn"))
            write_ris_line(handle, "N2", row.get("abstract"))
            write_ris_line(handle, "UR", row.get("source_url"))
            write_ris_line(handle, "KW", "BatLit")
            write_ris_line(handle, "KW", "AMNH")
            write_ris_line(handle, "N1", f"BatLit metadata source: {clean(row.get('metadata_source'))}; evidence: {clean(row.get('evidence_sources'))}; confidence: {clean(row.get('confidence'))}")
            write_ris_line(handle, "L1", filename)
            handle.write("ER  - \n\n")


def write_ris_line(handle, tag: str, value: str | None) -> None:
    text = clean(value)
    if text:
        handle.write(f"{tag}  - {text}\n")


def write_bibtex(path: Path, rows: list[dict[str, str]]) -> None:
    used: set[str] = set()
    with path.open("w", encoding="utf-8", newline="") as handle:
        for row in rows:
            key = cite_key(row, used)
            handle.write(f"@{bib_type(row)}{{{key},\n")
            fields = {
                "title": clean(row.get("title")),
                "author": " and ".join(split_people(clean(row.get("authors")))),
                "year": clean(row.get("year")),
                "journal": clean(row.get("journal")),
                "volume": clean(row.get("volume")),
                "number": clean(row.get("issue")),
                "pages": clean(row.get("pages")),
                "doi": clean(row.get("doi")),
                "issn": clean(row.get("issn")),
                "url": clean(row.get("source_url")),
                "abstract": clean(row.get("abstract")),
                "file": clean(row.get("enhanced_filename")),
                "keywords": "BatLit; AMNH",
                "note": f"BatLit metadata source: {clean(row.get('metadata_source'))}; evidence: {clean(row.get('evidence_sources'))}; confidence: {clean(row.get('confidence'))}",
            }
            for name, value in fields.items():
                if value:
                    handle.write(f"  {name} = {{{value}}},\n")
            handle.write("}\n\n")


def write_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def row_from_pdf_metadata(pdf_path: Path) -> dict[str, str]:
    metadata = PdfReader(str(pdf_path)).metadata or {}
    authors = clean(metadata.get("/Author"))
    title = clean(metadata.get("/Title")) or pdf_path.stem
    return {
        "status": "embedded",
        "enhanced_filename": pdf_path.name,
        "title": title,
        "authors": authors,
        "year": clean(metadata.get("/BatLitYear")),
        "doi": clean(metadata.get("/DOI")),
        "journal": clean(metadata.get("/BatLitJournal")),
        "volume": clean(metadata.get("/BatLitVolume")),
        "issue": clean(metadata.get("/BatLitIssue")),
        "pages": clean(metadata.get("/BatLitPages")),
        "issn": clean(metadata.get("/BatLitISSN")),
        "abstract": clean(metadata.get("/BatLitAbstract")),
        "source_url": clean(metadata.get("/BatLitMetadataSourceURL")),
        "metadata_source": clean(metadata.get("/BatLitMetadataSource")) or "embedded PDF metadata fallback",
        "evidence_sources": clean(metadata.get("/BatLitEvidenceSources")),
        "confidence": clean(metadata.get("/BatLitMetadataConfidence")) or "embedded",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--enrichment-folder", required=True, help="AMNH metadata enrichment folder")
    parser.add_argument("--metadata-csv", required=True, help="Curated metadata CSV")
    parser.add_argument("--pdf-folder", default="Zotero_Ready_PDFs", help="Folder containing enhanced PDFs")
    parser.add_argument("--package-name", default="", help="Optional package folder name")
    args = parser.parse_args()

    enrichment = Path(args.enrichment_folder)
    metadata_csv = Path(args.metadata_csv)
    pdf_folder = enrichment / args.pdf_folder
    stamp = datetime.now().strftime("%Y%m%d")
    package_name = args.package_name or f"AMNH_{stamp}_Zotero_Import_Package"
    package = enrichment / package_name
    package.mkdir(parents=True, exist_ok=True)

    csv_rows_by_pdf: dict[str, dict[str, str]] = {}
    for row in read_csv(metadata_csv):
        confidence = clean(row.get("confidence")).lower()
        status = clean(row.get("status")).lower()
        filename = clean(row.get("enhanced_filename"))
        if confidence not in READY_CONFIDENCE or "embedded" not in status or not filename:
            continue
        csv_rows_by_pdf[filename] = row

    rows = []
    for source_pdf in sorted(pdf_folder.glob("*.pdf"), key=lambda path: path.name.lower()):
        row = csv_rows_by_pdf.get(source_pdf.name) or row_from_pdf_metadata(source_pdf)
        shutil.copy2(source_pdf, package / source_pdf.name)
        out = dict(row)
        out["enhanced_filename"] = source_pdf.name
        out["package_pdf"] = source_pdf.name
        rows.append(out)

    write_ris(package / f"{package_name}.ris", rows)
    write_bibtex(package / f"{package_name}.bib", rows)
    write_manifest(package / f"{package_name}_manifest.csv", rows)
    (package / "README_IMPORT.txt").write_text(
        "\n".join([
            "Zotero import package",
            "",
            "Use Zotero File > Import and select the .ris file in this folder.",
            "The RIS records include relative L1 links to the PDFs copied beside it.",
            "Dragging the PDFs alone may still leave scanned historical documents as standalone attachments because Zotero does not reliably use PDF document properties for parent-item metadata.",
            "",
            f"Records: {len(rows)}",
            f"Created: {datetime.now().isoformat(timespec='seconds')}",
            "",
        ]),
        encoding="utf-8",
    )
    print(f"Package: {package}")
    print(f"Records: {len(rows)}")


if __name__ == "__main__":
    main()
