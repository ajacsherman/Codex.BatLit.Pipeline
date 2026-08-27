# BatLit Pre-Zotero Deduplication Pipeline

This project is a pre-Zotero screening workflow for incoming literature PDFs. The goal is to inspect incoming PDFs before Zotero import, compare them against the BatLit corpus, and route each item into a clear review category.

For a fresh clone or a new user, start with `QUICKSTART.md`.

## Current Workflow

The current workflow screens PDFs in `batlit-dedupe/incoming/` against BatLit's published `refs.csv` index. It computes file hashes, extracts first-page and first-ten-page text, detects front-matter DOI candidates, compares DOI and MD5 hashes against BatLit, and writes review reports.

When native PDF text extraction is missing or weak, the dedupe workflow can try multiple text sources and keep the best readable result. It scores native `pdftotext` output first, then tries OCR-generated PDFs with `ocrmypdf --skip-text` and `ocrmypdf --force-ocr` when needed. The selected method and scores are recorded in `dedupe_report.csv`.

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

## Portable One-Command Run

After installing Python 3 and Poppler, initializing folders, adding `index/refs.csv`, and placing PDFs in `incoming/`, a user can run a complete collection workflow from inside `batlit-dedupe/`:

```bash
python3 scripts/batlit_run_collection.py --collection-name "Collection Name"
```

For AMNH batches, use one source-level collection label rather than splitting the papers into individual literature-collection files:

```bash
python3 scripts/batlit_run_collection.py --collection-name "AMNH"
```

AMNH source PDFs should be staged separately from earlier batches:

```text
batlit-dedupe/amnh_incoming/
```

The Google Drive folder must be downloaded or synced into `amnh_incoming/` before the pipeline can run. This prevents the AMNH batch from mixing with older PDFs still present in `batlit-dedupe/incoming/`.

This creates date-only source-first outputs such as:

```text
processed_runs/AMNH_YYYYMMDD/
collections/AMNH_YYYYMMDD/
collection_tracking/AMNH/AMNH_YYYYMMDD_action_log.csv
processed_runs/AMNH_YYYYMMDD/AMNH_YYYYMMDD_zotero_upload/
```

AMNH PDFs are still routed into the normal decision folders (`duplicates`, `likely_duplicates`, `new_literature`, `non_bat_review`, and review/failure folders if needed), but they are not split into separate files by source literature collection.

For AMNH, duplicates are not expected because the original description citation list was already compared with the existing BatLit corpus and cross-referenced against available online citation records. Duplicate detection still runs as an audit check, but AMNH runs use `--excerpt-mode`: exact file hashes can still identify a true duplicate, while shared title-page metadata or source-work DOI/title matches are recorded as possible same-source excerpts rather than routed as duplicates. This matters for books where multiple species descriptions come from different pages of the same source work.

For weak AMNH metadata, generate a citation lookup packet:

```bash
python3 scripts/batlit_prepare_external_metadata_lookup.py \
  --run-folder AMNH_YYYYMMDD \
  --folders new_literature \
  --pages 10
```

This writes front-matter clues and search links, including Google Scholar, Crossref, OpenAlex, Semantic Scholar, BHL, and Internet Archive. Google Scholar is used as a human-review link because it does not provide a stable public API for automated scraping.

For old scans and taxonomic excerpts, run the MDD/taxon clue scan. It scans the first ten pages for title-like lines, years, species names, original-description language, type-locality language, and museum/source clues, then creates targeted lookup links. If Mammal Diversity Database CSV exports are placed in `index/mdd/`, the scan cross-references candidate bat names and synonyms against Chiroptera records.

```bash
python3 scripts/batlit_mdd_citation_clues.py \
  --run-folder AMNH_YYYYMMDD \
  --folder new_literature \
  --pages 10 \
  --mdd-species-csv index/mdd/MDD_species.csv \
  --mdd-synonyms-csv index/mdd/MDD_species_synonyms.csv
```

This writes:

```text
metadata_enrichment/AMNH_YYYYMMDD/YYYYMMDD_HHMMSS_mdd_citation_clues/
  mdd_citation_clues.csv
  metadata_to_embed_template.csv
  summary.txt
metadata_enrichment/AMNH_YYYYMMDD/latest_mdd_citation_clues.csv
```

To embed verified metadata from the template, fill `metadata_to_embed_template.csv`, mark approved rows with `apply_metadata=yes` and `confidence=high`, `curated`, or `verified`, then run:

```bash
python3 scripts/batlit_mdd_citation_clues.py \
  --run-folder AMNH_YYYYMMDD \
  --folder new_literature \
  --resolved-csv path/to/metadata_to_embed_template.csv \
  --apply
```

The script embeds approved title, author, year, DOI, journal, volume, issue, pages, ISSN, source URL, and metadata-source fields into the routed PDF copies.

For edited books and AMNH excerpts, the clue scan also looks for book/chapter layout evidence across the first ten pages. A title page such as `Natural History of Vampire Bats` is treated as parent-work evidence, and a following `Chapter` page is scanned for chapter title, chapter author, table-of-contents structure, and distinctive body sentences. These clues are used to build search queries such as chapter author + chapter title + book title + a unique quoted sentence, which helps avoid false years pulled from taxonomic text, such as species-description dates.

Handwritten annotations on title pages are useful evidence but are not reliably captured by normal PDF text extraction. When metadata is weak, the workflow should render the first pages for visual review and keep the rendered pages with the clue packet so annotation evidence can be checked before embedding curated metadata.

Unknown authors, `Unknown` filenames, blank author fields, noisy reprint-stamp titles, and suspicious taxonomic years are not treated as finished Zotero-ready metadata. They should be sent to the metadata investigation queue:

```bash
python3 scripts/batlit_metadata_investigation_queue.py \
  --run-folder AMNH_YYYYMMDD \
  --folder new_literature \
  --pages 10 \
  --render-pages 2
```

The queue reuses the pipeline's parsimonious text strategy: native PDF text first, then OCR alternatives only when front-matter text is weak. It writes first-ten-page text, rendered first-page evidence for annotations/title layouts, issue flags, distinctive quote searches, and next-action notes. For collections like AMNH, most target papers are expected to be cited in Mammal Diversity Database Chiroptera species or family records, so MDD accepted names, synonyms, and authority links should be used as a priority lookup layer whenever local MDD CSV exports are available in `index/mdd/`.

For historical scans whose metadata is already flagged as weak, run the deeper OCR comparison:

```bash
python3 scripts/batlit_metadata_investigation_queue.py \
  --run-folder AMNH_YYYYMMDD \
  --folder new_literature \
  --pages 10 \
  --ocr-flagged-records
```

This tries OCR alternatives for queued records even when native text is abundant, because abundant OCR text can still be noisy enough to mislead title/author/year extraction.

To initialize/check a fresh workspace:

```bash
python3 scripts/batlit_setup_project.py
```

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

From inside `batlit-dedupe/`:

```bash
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

## Synchronize Run Outputs After Metadata Improvements

After any metadata pass that updates `new_literature/bibliography.csv` or embeds better metadata into routed PDFs, synchronize the derived folders and create a fresh upload-ready folder:

```bash
python3 scripts/batlit_sync_run_outputs.py \
  --run-folder "YYYYMMDD_HHMMSS_batch-label" \
  --collection-name "Collection label" \
  --make-upload-folder
```

This refreshes:

```text
Deduplicated_new_literature/
Deduplicated_likely_duplicates/
deduplicated_review_manifest.csv
sync_runs/YYYYMMDD_HHMMSS_sync_run_outputs/
YYYYMMDD_HHMMSS_enhanced_metadata_pdfs_for_zotero/
```

Use the newest `*_enhanced_metadata_pdfs_for_zotero/` folder for Zotero upload. The sync step does not change duplicate/non-bat/new-literature decisions; it keeps copied folders, manifests, bibliographies, and upload sets consistent after metadata improvements.

## Extract Cited References For Citation Network Review

To seed a citation network or create a track-down spreadsheet for cited literature:

```bash
python3 scripts/batlit_extract_cited_references.py \
  --run-folder "YYYYMMDD_HHMMSS_batch-label"
```

By default, this scans:

```text
Deduplicated_new_literature/
Deduplicated_likely_duplicates/
```

The script writes:

```text
citation_network/YYYYMMDD_HHMMSS_batch-label/cited_reference_candidates.csv
citation_network/YYYYMMDD_HHMMSS_batch-label/citation_edges.csv
citation_network/YYYYMMDD_HHMMSS_batch-label/summary.txt
```

`cited_reference_candidates.csv` is the human review spreadsheet. It includes source PDF, reference text, DOI, URL, year, guessed authors, guessed title, and a reference key. `citation_edges.csv` is a lightweight network edge list from each source PDF to each cited reference key.

The next enrichment layer should resolve citation candidates through DOI/title services and download only clearly open-access PDFs or files obtained through explicit user/library authorization. Paywalled PDFs should be listed with candidate links for manual retrieval through an authorized library/VPN workflow.

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
front_matter_dois     DOI strings found in the first 10 pages by default
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

## Clean Rerun Order

For a new or reprocessed collection, run the steps in this order so every folder and CSV reflects the same decision pass:

```bash
python3 scripts/batlit_dedupe_workflow.py --base . --front-matter-pages 10
python3 scripts/batlit_route_pdfs.py --base . --copy --include-duplicates --rename-citation --run-folder SOURCE_YYYYMMDD
python scripts/batlit_embed_pdf_metadata.py --base . --run-folder SOURCE_YYYYMMDD --apply
python scripts/batlit_apply_metadata_fallbacks.py --base . --run-folder SOURCE_YYYYMMDD --folder new_literature --apply
python scripts/batlit_sync_run_outputs.py --base . --run-folder SOURCE_YYYYMMDD --collection-name "Source name" --make-upload-folder --date-only
python scripts/batlit_create_deduplicated_review_sets.py --base . --run-folder SOURCE_YYYYMMDD --collection-name "Source name"
python scripts/batlit_collection_action_log.py --base . --collection-name "Source name" --run-folder SOURCE_YYYYMMDD --date-only
```

The sync step refreshes `Deduplicated_new_literature/`, `Deduplicated_likely_duplicates/`, the run-level deduplicated manifest, and a source/date-stamped `SOURCE_YYYYMMDD_zotero_upload/` folder containing the metadata-enhanced new-literature PDFs. Superseded run outputs are archived under `batlit-dedupe/archive/`; if Dropbox or Windows locks a large folder, create a non-destructive archive copy and mark the original with `_SUPERSEDED_DO_NOT_USE.txt`.

## Current Bates 2026 Rerun

The current clean rerun is:

```text
batlit-dedupe/processed_runs/20260629_111835_Bates_2026_rerun/
```

Current upload-ready PDFs for Zotero are in:

```text
batlit-dedupe/processed_runs/20260629_111835_Bates_2026_rerun/20260629_114341_zotero_upload/
```

The previous Bates run was archived to:

```text
batlit-dedupe/archive/20260629_114508_oldBates_remaining/
```

## Data Sources

- BatLit website: https://batlit.org/
- BatLit GitHub Pages repository: https://github.com/bat-literature/bat-literature.github.io
- BatLit Zenodo releases: https://zenodo.org/communities/batlit

## Notes

PDFs, extracted text, downloaded indexes, generated reports, and RIS staging files are ignored by Git by default. This protects copyrighted PDFs and local review outputs from accidental publication.
