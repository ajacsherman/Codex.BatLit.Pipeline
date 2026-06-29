# File Inventory

This folder is a human-readable guide to the BatLit pipeline project structure. It describes what the main folders and generated files are for. It is not an inventory of every PDF; the PDF-level inventories live in the routed bibliographies and collection action logs.

## Project Root

| Path | Description |
| --- | --- |
| `README.md` | Main project overview and command guide for the pre-Zotero BatLit deduplication pipeline. |
| `.gitignore` | Prevents local PDFs, extracted text, generated outputs, and other large or private workflow artifacts from being committed accidentally. |
| `.github/` | GitHub project metadata and issue templates/workflows, if added. |
| `issues/` | Local project planning notes and GitHub issue drafts/records. |
| `File Inventory/` | Human-readable descriptions of folders and files in this project. |
| `batlit-dedupe/` | Main working directory for the BatLit pre-Zotero deduplication pipeline. |

## Main Pipeline Folder: `batlit-dedupe/`

| Path | Description |
| --- | --- |
| `incoming/` | Drop zone for a newly supplied collection of PDFs before screening. Current collection: `Bates 2026`, shared by Paul Bates in 2026. |
| `index/` | Lightweight comparison indexes used before Zotero import, including BatLit reference exports such as `refs.csv`. |
| `index/literature_fingerprint_index.csv` | Lightweight BatLit fingerprint index used for pre-Zotero comparison. Includes DOI, title, authors, year, normalized fields, Zotero links, and available attachment MD5 hashes. |
| `reports/` | Latest and timestamped CSV/RIS reports produced by dedupe, routing, DOI extraction, metadata staging, and related checks. |
| `work/` | Cached extracted text and intermediate files used by scripts. These are reproducible working files, not final review outputs. |
| `collections/` | Timestamped manifests and diffs for incoming batches, used to record what changed when a new collection was added. |
| `zotero_diffs/` | Before/after Zotero collection comparison outputs, used after deduplicated items are added to Zotero. |
| `citation_network/` | Optional downstream citation-network outputs, including cited-reference candidate spreadsheets and edge lists extracted from routed PDFs. |
| `processed/` | Older active/mixed processed folders. Prefer `processed_runs/` for clean timestamped review outputs. |
| `processed_runs/` | Clean timestamped routing outputs. Each run keeps its own duplicates, likely duplicates, new literature, manual review, and non-bat review folders. |
| `collection_tracking/` | Collection-level action logs and summaries that record what happened to each file in a named collection. |
| `scripts/` | Reusable Python scripts that run the pipeline. |

## Current Clean Run: `processed_runs/20260629_111835_Bates_2026_rerun/`

| Folder/File | Description |
| --- | --- |
| `duplicates/` | PDFs from the Bates 2026 incoming collection that matched the existing BatLit corpus or another item in the incoming batch by exact file hash or DOI. These should not be imported into Zotero as new literature. |
| `likely_duplicates/` | PDFs from Bates 2026 that are high-confidence possible duplicates, generally from title/author/year matching. These need human confirmation before import. |
| `new_literature/` | PDFs from Bates 2026 that did not match BatLit or another incoming-batch item and passed the current bat-relevance screen. These are candidates for Zotero ingestion after metadata review. |
| `Deduplicated_new_literature/` | Duplicate-omitted copy of Bates 2026 `new_literature` for next-stage metadata review and Zotero ingestion. |
| `non_bat_review/` | PDFs from Bates 2026 sorted out because the extracted text did not show bat-relevance terms such as `bat`, `bats`, or `chiroptera`, and/or showed non-bat context terms. These should be reviewed for scope before import. |
| `Deduplicated_likely_duplicates/` | Duplicate-omitted Bates 2026 likely duplicate review set. These are possible duplicates that need manual confirmation before any Zotero import. |
| `manual_review/` | Ambiguous PDFs, such as files with extraction failures or insufficient metadata, that need a manual decision before import. This folder may be absent or empty in a run if no files land there. |
| `failed_processing/` | Files that could not be processed cleanly enough for routine routing. These need better OCR, repair, or manual citation searching. This folder may be absent or empty in a run if no files land there. |
| `bibliography.csv` / `bibliography.xlsx` inside each category | Category-specific bibliography and routing metadata for the PDFs in that folder. |
| `metadata_embedding_report.csv` | Report showing which routed PDFs had metadata embedded into the PDF document info fields. |

## Current Zotero Upload Folder

| Path | Description |
| --- | --- |
| `batlit-dedupe/processed_runs/20260629_111835_Bates_2026_rerun/20260629_114341_zotero_upload/` | Timestamped Zotero-ready upload folder containing metadata-enhanced PDFs from `new_literature/` only. Confirmed duplicates, likely duplicates, and non-bat review items are omitted. |

## Superseded Bates Run

| Path | Description |
| --- | --- |
| `batlit-dedupe/archive/20260629_114508_oldBates_remaining/` | Non-destructive archive copy of the superseded `20260623_132514_Bates_2026` run. This was used because Dropbox/Windows would not release the original folder for moving. |
| `batlit-dedupe/processed_runs/20260623_132514_Bates_2026/_SUPERSEDED_DO_NOT_USE.txt` | Marker left in the old run folder showing that it has been superseded and should not be used as the current collection output. |

## Bates 2026 Collection Tracking

| Path | Description |
| --- | --- |
| `batlit-dedupe/collection_tracking/Bates_2026/latest_action_log.csv` | Spreadsheet-style CSV with one row per Bates 2026 incoming PDF. It records the action taken, routed folder, duplicate reference if applicable, decision reason, title/authors/year/DOI, hashes, and BatLit match fields. |
| `batlit-dedupe/collection_tracking/Bates_2026/latest_action_summary.csv` | Compact summary of Bates 2026 decisions and routing actions. |
| `batlit-dedupe/collection_tracking/Bates_2026/*_action_log.csv` | Timestamped retained copies of the Bates 2026 action log. |
| `batlit-dedupe/collection_tracking/Bates_2026/*_action_summary.csv` | Timestamped retained copies of the Bates 2026 action summary. |

## Key Scripts

| Script | Description |
| --- | --- |
| `scripts/batlit_collection_diff.py` | Creates timestamped manifests and diffs when a new set of PDFs is added to `incoming/`. |
| `scripts/batlit_build_fingerprint_index.py` | Builds the lightweight BatLit literature fingerprint index from `refs.csv` for pre-Zotero comparison. |
| `scripts/batlit_dedupe_workflow.py` | Screens incoming PDFs against BatLit and the current incoming batch using hashes, DOI extraction, title/author/year matching, and bat-relevance terms. |
| `scripts/batlit_route_pdfs.py` | Copies or moves screened PDFs into review folders and creates per-folder bibliography CSV/XLSX files. |
| `scripts/batlit_create_deduplicated_review_sets.py` | Creates duplicate-omitted new literature and likely duplicate review folders plus manifest CSVs for a processed run. |
| `scripts/batlit_collection_action_log.py` | Creates the collection-level action log and summary for a named collection such as Bates 2026. |
| `scripts/batlit_embed_pdf_metadata.py` | Embeds routed bibliography metadata into PDF document info fields for Zotero-friendly import. |
| `scripts/batlit_failed_metadata_report.py` | Reports PDFs with missing/suspicious title, author, year, or text extraction results. |
| `scripts/batlit_extract_cited_references.py` | Extracts cited-reference candidates from routed PDFs and writes a track-down spreadsheet plus citation edge list. |
| `scripts/batlit_doi_report.py` | Produces DOI-focused diagnostics for extracted DOI candidates. |
| `scripts/batlit_make_zotero_ris.py` | Creates a Zotero RIS staging file for candidate new literature. |
| `scripts/batlit_zotero_collection_diff.py` | Compares before/after Zotero collection exports and writes added/removed/changed/unchanged reports. |
