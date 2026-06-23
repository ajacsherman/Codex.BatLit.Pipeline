# Quickstart: Run The BatLit Pre-Zotero Pipeline

This guide is for someone applying the pipeline to a new collection of PDFs.

## 1. Install Required Tools

The pipeline uses Python 3 and Poppler command-line tools.

On Ubuntu or WSL:

```bash
sudo apt update
sudo apt install python3 poppler-utils
```

On macOS with Homebrew:

```bash
brew install python poppler
```

On Windows, the easiest path is WSL with the Ubuntu commands above.

## 2. Clone The Repository

```bash
git clone https://github.com/ajacsherman/Codex.BatLit.Pipeline.git
cd Codex.BatLit.Pipeline/batlit-dedupe
```

## 3. Initialize The Folder Structure

```bash
python3 scripts/batlit_setup_project.py
```

This creates the standard folders and checks for `pdftotext` and `pdfinfo`.

## 4. Add The BatLit Reference Index

Place the BatLit reference export at:

```text
batlit-dedupe/index/refs.csv
```

The current workflow expects the BatLit `refs.csv` fields used by the public BatLit/Zotero export, including title, authors, date, DOI, Zotero item URL, and attachment hash fields.

## 5. Add Incoming PDFs

Copy a new collection of PDFs into:

```text
batlit-dedupe/incoming/
```

Do not mix unrelated batches if you want collection-level action logs to stay clean.

## 6. Run The Whole Pipeline

From inside `batlit-dedupe/`:

```bash
python3 scripts/batlit_run_collection.py --collection-name "Collection Name"
```

Example:

```bash
python3 scripts/batlit_run_collection.py --collection-name "Bates 2026"
```

The runner performs these steps:

1. Snapshots the incoming collection.
2. Builds `index/literature_fingerprint_index.csv`.
3. Screens incoming PDFs against BatLit and the current incoming batch.
4. Routes PDFs into a timestamped `processed_runs/` folder.
5. Creates duplicate-omitted review folders.
6. Writes a collection action log.
7. Embeds metadata into routed PDF copies.
8. Creates a Zotero RIS staging file.

## 7. Review Outputs

The most useful outputs are:

```text
processed_runs/YYYYMMDD_HHMMSS_Collection_Name/
processed_runs/YYYYMMDD_HHMMSS_Collection_Name/Deduplicated_new_literature/
processed_runs/YYYYMMDD_HHMMSS_Collection_Name/Deduplicated_likely_duplicates/
collection_tracking/Collection_Name/latest_action_log.csv
reports/dedupe_report.csv
reports/routing_report.csv
reports/zotero_import_staging.ris
```

## 8. Interpret The Routing Folders

| Folder | Meaning |
| --- | --- |
| `duplicates/` | Confirmed duplicates by exact hash or DOI against BatLit or the incoming batch. |
| `likely_duplicates/` | Probable duplicates, usually title/author/year matches, requiring manual review. |
| `new_literature/` | Candidate new literature after corpus and incoming-batch checks. |
| `non_bat_review/` | Items that appear out of scope because extracted text lacks bat-relevance terms and/or contains non-bat context terms. |
| `manual_review/` | Ambiguous items needing human review. |
| `failed_processing/` | Files that could not be text-extracted or processed cleanly. |
| `Deduplicated_new_literature/` | Duplicate-omitted candidate import set. |
| `Deduplicated_likely_duplicates/` | Duplicate-omitted likely duplicate review set. |

## Notes

- The pipeline copies files by default; it does not delete incoming PDFs.
- Generated PDFs and large workflow outputs should not be committed to Git.
- CSV/XLSX bibliographies and action logs preserve the audit trail for each collection.

