# BatLit Pre-Zotero Deduplication Pipeline

This project is a pre-Zotero screening workflow for incoming literature PDFs. The goal is to inspect incoming PDFs before Zotero import, compare them against the BatLit corpus, and route each item into a clear review category.

## Current Workflow

The current workflow screens PDFs in `batlit-dedupe/incoming/` against BatLit's published `refs.csv` index. It computes file hashes, extracts first-page and first-three-page text, detects front-matter DOI candidates, compares DOI and MD5 hashes against BatLit, and writes review reports.

The workflow currently makes high-confidence duplicate calls from:

```text
exact MD5 attachment hash matches
front-matter DOI matches
```

The workflow also checks for duplicates inside the current incoming batch using exact MD5 matches, front-matter DOI matches, and title/author/year matches.
The workflow also performs a conservative full-text bat relevance scan: PDFs with no obvious `bat`, `bats`, or `chiroptera` terms and with non-bat taxon/context terms are routed to `non_bat_review`.

## Folder Layout

```text
batlit-dedupe/
  collections/           Timestamped incoming-batch manifests and diffs
  index/                 BatLit reference indexes, such as refs.csv
  incoming/              PDFs waiting for screening
  processed/
    duplicates/          Confirmed duplicate PDFs
    likely_duplicates/   High-confidence possible duplicates
    new_literature/      New items ready for Zotero import
    manual_review/       Ambiguous or low-confidence cases
    non_bat_review/      Likely out-of-scope literature
    failed_processing/   Files that could not be processed
  processed_runs/        Clean timestamped routed output folders
  reports/               CSV/RIS review outputs
  scripts/               Reusable pipeline scripts
  work/                  Extracted text and intermediate files
  zotero_diffs/           Timestamped before/after Zotero collection diffs
```

## Build The Literature Fingerprint Index

The pipeline maintains a lightweight fingerprint index independent of Zotero itself. It is built from the BatLit reference export and can be checked before importing incoming PDFs into Zotero.

```bash
python3 scripts/batlit_build_fingerprint_index.py
```

The script writes:

```text
index/literature_fingerprint_index.csv
index/YYYYMMDD_HHMMSS_literature_fingerprint_index.csv
```

The index includes DOI, alternative DOI, title, normalized title, authors, first author, year, journal fields, Zotero item URLs, attachment identifiers, extracted MD5 hashes where available, and placeholder columns for future corpus-side page counts and text fingerprints.

## Snapshot a Newly Added Collection

Run this immediately after dropping a new batch of PDFs into `incoming/`:

```bash
python3 scripts/batlit_collection_diff.py --label "short collection name"
```

The script creates a timestamped folder:

```text
collections/YYYYMMDD_HHMMSS_short-collection-name/
  incoming_manifest.csv
  diff_added.csv
  diff_removed.csv
  diff_unchanged.csv
  summary.txt
```

These files are the durable batch ledger. They should stay in Git even after PDFs are routed, archived, deposited on Zenodo, or retired from workflow folders.

## Diff Zotero Before And After Import

Before adding a deduplicated collection to Zotero, export the target Zotero collection to CSV. After import and metadata review, export it again. Then run:

```bash
python3 scripts/batlit_zotero_collection_diff.py \
  --before path/to/zotero_before.csv \
  --after path/to/zotero_after.csv \
  --label "collection import name"
```

The script creates:

```text
zotero_diffs/YYYYMMDD_HHMMSS_collection-import-name/
  zotero_collection_diff.csv
  added.csv
  removed.csv
  changed.csv
  unchanged.csv
  summary.txt
```

This gives us a durable before/after audit trail for Zotero itself, separate from the PDF batch diff.

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

Copy both candidate new literature and known duplicates using `FirstAuthorLastName, Year.pdf` filenames:

```bash
python3 scripts/batlit_route_pdfs.py --copy --include-duplicates --rename-citation
```

Copy into a clean timestamped run folder instead of the mixed active `processed/` folders:

```bash
python3 scripts/batlit_route_pdfs.py \
  --copy \
  --include-duplicates \
  --rename-citation \
  --run-folder "YYYYMMDD_HHMMSS_batch-label"
```

This writes PDFs into:

```text
processed_runs/YYYYMMDD_HHMMSS_batch-label/
  duplicates/
  likely_duplicates/
  new_literature/
  non_bat_review/
  manual_review/
  failed_processing/
```

Each routed category folder also receives a bibliography in both CSV and Excel formats:

```text
bibliography.csv
bibliography.xlsx
YYYYMMDD_HHMMSS_bibliography.csv
YYYYMMDD_HHMMSS_bibliography.xlsx
```

The bibliography includes routed filename, original filename, decision, reason, title, authors, year, DOI, hashes, BatLit match fields, and bat-relevance fields.

The router writes:

```text
reports/routing_report.csv
reports/YYYYMMDD_HHMMSS_routing_report.csv
```

Prefer `--copy` until the review workflow is mature. The `--move` option exists, but should only be used after confirming the reports.

## Create Duplicate-Omitted Review Sets

After routing a clean run, create review folders that omit confirmed duplicates:

```bash
python3 scripts/batlit_create_deduplicated_review_sets.py \
  --run-folder "YYYYMMDD_HHMMSS_batch-label" \
  --collection-name "Collection label"
```

For Bates 2026, this created:

```text
processed_runs/20260623_132514_Bates_2026/Deduplicated_new_literature/
processed_runs/20260623_132514_Bates_2026/Deduplicated_likely_duplicates/
```

`Deduplicated_new_literature/` contains new Zotero candidates after confirmed duplicates have been omitted. `Deduplicated_likely_duplicates/` contains possible duplicates that should be reviewed manually before import. Each folder receives `deduplicated_review_manifest.csv`, and the run folder receives a combined `deduplicated_review_manifest.csv`.

## Report Failed Metadata Extraction

Create a CSV of PDFs needing better OCR, metadata cleanup, or manual citation search:

```bash
python3 scripts/batlit_failed_metadata_report.py
```

The script writes:

```text
processed/failed_processing/metadata_failed_processing.csv
processed/failed_processing/YYYYMMDD_HHMMSS_metadata_failed_processing.csv
```

Rows are flagged when title, author, year, or text extraction looks missing or suspicious.

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
batlit_match_scope    whether the match came from the BatLit corpus
incoming_batch_duplicate_status  primary or duplicate inside the incoming batch
incoming_batch_duplicate_reason  incoming-batch match basis
incoming_batch_primary_file      selected primary file for an incoming-batch duplicate set
incoming_batch_match_files       all files in the incoming-batch duplicate set
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
