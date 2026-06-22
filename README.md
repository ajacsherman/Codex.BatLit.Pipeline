# BatLit Pre-Zotero Deduplication Pipeline

This project is a pre-Zotero screening workflow for incoming literature PDFs. The goal is to OCR and inspect incoming PDFs before Zotero import, compare them against the BatLit corpus, and route each item into a clear review category.

## Current Prototype

The current prototype extracts DOI-like strings from PDFs in `incoming/`, compares them against BatLit's `refs.csv`, and writes a CSV report with inferred title, authors, DOI context, and BatLit match status.

## Folder Layout

```text
batlit-dedupe/
  index/                 BatLit reference indexes, such as refs.csv
  incoming/              PDFs waiting for screening
  processed/
    duplicates/          Confirmed duplicate PDFs
    likely_duplicates/   High-confidence possible duplicates
    new_literature/      New items ready for Zotero import
    manual_review/       Ambiguous or low-confidence cases
    non_bat_review/      Likely out-of-scope literature
  reports/               CSV/TSV review outputs
  scripts/               Reusable pipeline scripts
  work/                  Extracted text and intermediate files
```

## Run the DOI Report

From WSL:

```bash
cd "/mnt/c/Users/Aja/Dropbox (Personal)/Bat Co-roosting Project/Bat Lit Proj/Codex.BatLit.Pipeline/batlit-dedupe"
python3 scripts/batlit_doi_report.py
```

The script writes:

```text
reports/doi_match_report_with_metadata.csv
```

## Report Columns

```text
file                  PDF filename from incoming/
incoming_title        title inferred from first page text
incoming_authors      authors inferred from first page text
found_doi             DOI found in the PDF text
doi_context           front_matter, full_text, reference_list, none_found, or unknown
batlit_status         DOI_MATCH, NO_DOI_MATCH, or NO_DOI_FOUND
batlit_title          BatLit title, if matched
batlit_authors        BatLit authors, if matched
batlit_year_or_date   BatLit publication date, if matched
batlit_zotero_id      Zotero item identifier, if matched
batlit_attachment_id  BatLit attachment hash, if matched
```

## Planned Pipeline

```text
incoming PDFs
  -> raw file hash
  -> text extraction / OCR
  -> metadata extraction
  -> DOI and hash matching
  -> fuzzy citation matching
  -> BatLit relevance screening
  -> route to review folders
```

## Data Sources

- BatLit website: https://batlit.org/
- BatLit GitHub Pages repository: https://github.com/bat-literature/bat-literature.github.io
- BatLit Zenodo releases: https://zenodo.org/communities/batlit

## Notes

PDFs and generated reports are ignored by Git by default. This protects copyrighted PDFs and local review outputs from accidental publication.
