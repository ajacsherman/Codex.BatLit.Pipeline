# Running Methods: BatLit Pre-Zotero Deduplication Pipeline

This document records the evolving methods used to screen incoming literature collections before Zotero ingestion.

## Current Collection

The current test collection is labeled `Bates 2026`, a set of PDFs shared by Paul Bates in 2026 and placed in `batlit-dedupe/incoming/`.

## Corpus Indexing

We built a lightweight BatLit literature fingerprint index from the BatLit reference export `index/refs.csv`. The index is stored independently of Zotero as `index/literature_fingerprint_index.csv` with timestamped archival copies. For each BatLit record, the index stores DOI, alternative DOI, title, normalized title, authors, normalized authors, first author, year, journal and publication fields, Zotero item URL, attachment identifiers, and extracted MD5 hashes where available. Placeholder columns are retained for future corpus-side page counts and first-page or first-three-page text fingerprints.

## Incoming PDF Screening

Incoming PDFs are screened before Zotero import. The workflow computes MD5 and SHA256 hashes, extracts page count with `pdfinfo`, extracts text with `pdftotext`, and uses the first page to infer title, authors, and year. DOI candidates are extracted from the first three pages. Full extracted text is also scanned for bat-relevance terms, including `bat`, `bats`, and `chiroptera`, and for non-bat context terms.

## Duplicate Classification

Incoming PDFs are first compared with the BatLit corpus using exact MD5 hash matches, DOI matches from front matter, and normalized title/author/year matches. The workflow also compares PDFs within the current incoming batch using the same evidence classes. Exact hash and DOI matches are treated as confirmed duplicates. Title/author/year matches are treated as likely duplicates for manual review. The report records whether a match came from the BatLit corpus or from the current incoming batch.

## Routing

After screening, files are copied into timestamped `processed_runs/` folders. Confirmed duplicates are routed to `duplicates/`; high-confidence possible duplicates are routed to `likely_duplicates/`; new candidate literature is routed to `new_literature/`; and likely out-of-scope items are routed to `non_bat_review/`. For Bates 2026, no files had text-extraction errors and no `failed_processing/` folder was produced.

## Duplicate-Omitted Review Sets

For Bates 2026, confirmed duplicates were omitted from the next-stage review folders. The folder `Deduplicated_new_literature/` contains candidate new literature for metadata review and Zotero ingestion. The folder `Deduplicated_likely_duplicates/` contains possible duplicates that should be reviewed manually before any Zotero import. Manifests are written inside each folder and as a combined run-level manifest.

## Metadata Embedding

After routing, bibliography metadata is embedded into the routed PDF copies using PDF document information fields. Embedded fields include title, author, DOI, year, BatLit decision, decision reason, original filename, hashes, and Zotero/BatLit match identifiers where available. This step is intended to make the routed PDFs easier to inspect and import into Zotero while preserving separate CSV/XLSX audit records.

## Audit Outputs

The pipeline writes CSV and XLSX bibliographies for each routed folder, collection-level action logs, routing reports, dedupe reports, metadata embedding reports, and timestamped manifests. These files preserve the decisions made for each PDF and allow later reconstruction of what was added, excluded, or sent to manual review.

## Clean Rerun and Archive Policy

When a collection is reprocessed, the original incoming batch is treated as the source of truth and the full sequence is rerun: deduplication, routing, metadata embedding, curated metadata fallback, derived-folder synchronization, deduplicated review manifest creation, and collection action-log generation. Derived folders are not edited as independent sources; they are refreshed from the routed folders after metadata improvement.

For the Bates 2026 rerun on 2026-06-29, the active run folder is `processed_runs/20260629_111835_Bates_2026_rerun/`. The run retained 544 confirmed duplicates, 93 likely duplicates, 2,472 candidate new-literature PDFs, and 394 non-bat review PDFs. The Zotero upload set is `processed_runs/20260629_111835_Bates_2026_rerun/20260629_114341_zotero_upload/`, containing the metadata-enhanced new-literature PDFs only.

Superseded outputs are preserved under `archive/` rather than deleted. When Windows or Dropbox prevents moving a large folder, a non-destructive archive copy is created and the original is marked with `_SUPERSEDED_DO_NOT_USE.txt` until it can be retired.

## Citation Network Seed Extraction

A citation-network phase was added as an optional downstream step. The workflow scans duplicate-omitted review sets, extracts full text, identifies the cited-reference section using common headings such as `References`, `Literature cited`, and `Bibliography`, and splits that section into candidate reference strings. For each cited reference, the script records the source PDF, reference text, DOI when present, URL when present, year, guessed authors, guessed title, and a stable reference key. A separate edge-list file records source PDF to cited-reference relationships for network analysis.

This phase is intended first as a track-down and network-building aid. Automated downloading should be limited to clearly open-access PDFs or files explicitly obtained through authorized user or library access. Paywalled literature should be recorded as DOI/URL/title candidates for manual retrieval through the user's museum library VPN or other authorized access route.
