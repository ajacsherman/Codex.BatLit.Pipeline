# BatLit Pre-Zotero Deduplication Pipeline

This project is a pre-Zotero screening workflow for incoming literature PDFs. The goal is to inspect incoming PDFs before Zotero import, compare them against the BatLit corpus, and route each item into a clear review category.

## Current Workflow

The current workflow screens PDFs in `batlit-dedupe/incoming/` against BatLit's published `refs.csv` index. It computes file hashes, extracts first-page and first-three-page text, detects front-matter DOI candidates, compares DOI and MD5 hashes against BatLit, and writes review reports.

The workflow currently makes high-confidence duplicate calls from:

```text
exact MD5 attachment hash matches
front-matter DOI matches
```

Fuzzy citation matching, OCR, and Bat relevance screening are planned next steps.

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
    failed_processing/   Files that could not be processed
  reports/               CSV/RIS review outputs
  scripts/               Reusable pipeline scripts
  work/                  Extracted text and intermediate files
```

## Run Full Dedupe Screening

From WSL:

```bash
cd "/mnt/c/Users/Aja/Dropbox (Personal)/Bat Co-roosting Project/Bat Lit Proj/Codex.BatLit.Pipeline/batlit-dedupe"
python3 scripts/batlit_dedupe_workflow.py
```

The script writes:

```text
reports/dedupe_report.csv
reports/dedupe_summary.txt
reports/zotero_metadata_staging.csv
```

## Create Zotero RIS Staging File

After running the dedupe workflow:

```bash
python3 scripts/batlit_make_zotero_ris.py
```

The script writes:

```text
reports/zotero_import_staging.ris
```

This RIS file is intended as a staging import for candidate new literature only. Title and author fields are inferred from PDF text and should be reviewed before final Zotero ingestion.

## Route PDFs Into Processed Folders

Preview routing without copying or moving files:

```bash
python3 scripts/batlit_route_pdfs.py
```

Preview routing including known duplicates:

```bash
python3 scripts/batlit_route_pdfs.py --include-duplicates
```

Copy candidate new literature into `processed/new_literature/` while leaving `incoming/` untouched:

```bash
python3 scripts/batlit_route_pdfs.py --copy
```

Copy both candidate new literature and known duplicates:

```bash
python3 scripts/batlit_route_pdfs.py --copy --include-duplicates
```

The router writes:

```text
reports/routing_report.csv
```

Prefer `--copy` until the review workflow is mature. The `--move` option exists, but should only be used after confirming the reports.

## Run DOI Context Report

For a DOI-focused diagnostic report:

```bash
python3 scripts/batlit_doi_report.py
```

The script writes:

```text
reports/doi_match_report_with_metadata.csv
```

This report is useful for distinguishing front-matter DOIs from DOI strings found in reference lists.

## Dedupe Report Columns

```text
decision              duplicate, new_literature, or manual_review
decision_reason       reason for the decision
file                  PDF filename from incoming/
size_bytes            PDF size in bytes
page_count            page count from pdfinfo
md5                   incoming PDF MD5 hash
sha256                incoming PDF SHA256 hash
incoming_title        title inferred from first page text
incoming_authors      authors inferred from first page text
incoming_year_guess   year inferred from first page text
front_matter_dois     DOI strings found on pages 1-3
batlit_match_count    number of BatLit matches
batlit_title          BatLit title, if matched
batlit_authors        BatLit authors, if matched
batlit_year_or_date   BatLit publication date, if matched
batlit_doi            BatLit DOI, if matched
batlit_zotero_id      Zotero item identifier, if matched
batlit_attachment_id  BatLit attachment hash, if matched
text_error            extraction error, if any
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
  -> Zotero-readable metadata staging
```

## Data Sources

- BatLit website: https://batlit.org/
- BatLit GitHub Pages repository: https://github.com/bat-literature/bat-literature.github.io
- BatLit Zenodo releases: https://zenodo.org/communities/batlit

## Notes

PDFs, extracted text, downloaded indexes, generated reports, and RIS staging files are ignored by Git by default. This protects copyrighted PDFs and local review outputs from accidental publication.
