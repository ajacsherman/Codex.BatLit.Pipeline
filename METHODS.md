# Running Methods: BatLit Pre-Zotero Deduplication Pipeline

This document records the evolving methods used to screen incoming literature collections before Zotero ingestion.

## Current Collection

The current test collection is labeled `Bates 2026`, a set of PDFs shared by Paul Bates in 2026 and placed in `batlit-dedupe/incoming/`.

## Corpus Indexing

We built a lightweight BatLit literature fingerprint index from the BatLit reference export `index/refs.csv`. The index is stored independently of Zotero as `index/literature_fingerprint_index.csv` with timestamped archival copies. For each BatLit record, the index stores DOI, alternative DOI, title, normalized title, authors, normalized authors, first author, year, journal and publication fields, Zotero item URL, attachment identifiers, and extracted MD5 hashes where available. Placeholder columns are retained for future corpus-side page counts and first-page or first-ten-page text fingerprints.

## Incoming PDF Screening

Incoming PDFs are screened before Zotero import. The workflow computes MD5 and SHA256 hashes, extracts page count with `pdfinfo`, extracts text with `pdftotext`, and uses the first ten pages by default to infer title, authors, year, and DOI candidates. This change was made because books, older scans, and museum literature can place title-page or publication details several pages into the PDF. Full extracted text is also scanned for bat-relevance terms, including `bat`, `bats`, and `chiroptera`, and for non-bat context terms.

Text extraction is now method-aware. The workflow first scores native `pdftotext` output. If front-matter text is weak or unavailable, it can generate OCR alternatives with `ocrmypdf --skip-text` and `ocrmypdf --force-ocr`, then extract text from those OCR PDFs and keep the highest-scoring readable result. The selected extraction method, front-matter text score, full-text score, and OCR attempts are recorded in the dedupe report.

## AMNH Batch Handling

The AMNH papers are treated as a single source-level acquisition batch rather than being split into separate files by individual literature collection. The active naming convention is source-first and date-only, such as `AMNH_20260826`. AMNH duplicates are not expected because the original description citation list was previously compared with the existing BatLit corpus and cross-referenced against available online citation records. The pipeline still performs duplicate checks as a sanity audit, but AMNH runs use excerpt-aware matching. Exact file hashes can identify true duplicate PDFs. Shared title-page metadata, source-work DOI matches, or title/author/year matches are recorded as possible same-source excerpts rather than automatically routed as duplicates, because multiple species descriptions can come from different pages of the same book.

AMNH source PDFs are staged in `amnh_incoming/` rather than the shared `incoming/` folder. This keeps the AMNH acquisition batch separate from earlier workflow batches and prevents accidental rerouting of older Bates-era PDFs under an AMNH label. The Google Drive source folder is treated as an external handoff location; files must be downloaded or synced locally into `amnh_incoming/` before the pre-Zotero pipeline can process them.

For AMNH records with weak or missing citation metadata, the workflow creates a citation lookup packet using the first ten pages of extracted text. The packet records OCR-derived clues, a recommended search query, and review links for Google Scholar, Crossref, OpenAlex, Semantic Scholar, BHL, Internet Archive, and DOI lookup. Google Scholar is treated as a manual review target rather than an automated data source because it does not provide a stable public API for scripted harvesting. Structured metadata candidates from Crossref and OpenAlex are recorded separately and should only be embedded when confidence is high and the result is bibliographically plausible.

For historical scans and taxonomic excerpts, an additional citation-clue pass scans the first ten pages for species binomials, title-like lines, years, original-description phrases, type-locality phrases, specimen-language clues, and source-institution clues. When Mammal Diversity Database exports are available locally, candidate names are cross-referenced against Chiroptera accepted names and synonyms. These matches are used as search anchors, not as automatic citation replacements. A species name can identify the taxonomic object of interest while the PDF itself may be a catalog page, book excerpt, plate, or later revision. Therefore, the clue pass writes a review CSV and a metadata-to-embed template. Metadata is embedded into PDFs only when a row is explicitly approved or marked high-confidence/curated/verified.

The AMNH `Unknown, 1810.pdf` example showed that edited-book excerpts require parent-work and chapter-level parsing. The title page identified the parent work as `Natural History of Vampire Bats`, while the next page identified `Systematics and distribution` by Karl F. Koopman as the chapter. The body text contained taxonomic dates such as 1810, which should not be interpreted as the publication year. The workflow now treats edited-book title pages as parent-work evidence, scans adjacent pages for `Chapter` layout, chapter author, chapter title, and table-of-contents structure, and extracts distinctive body sentences for targeted online lookup. For book chapters, query construction prioritizes chapter author, chapter title, parent book title, and a distinctive quote over taxonomic years found in body text.

Handwritten annotations, such as curator notes on AMNH title pages, are valuable but not reliably available to normal text extraction. When OCR/text metadata remains weak, the first pages should be rendered to images and reviewed as part of the metadata-evidence packet. Any metadata inferred from annotations should be recorded as curated evidence before it is embedded into Zotero-ready PDFs.

Records with unresolved or suspicious metadata are now handled as an investigation queue rather than accepted as final. Queue triggers include `Unknown` filenames, blank authors, noisy reprint-stamp titles, missing years, invalid years, and plausible taxonomic years drawn from body text rather than publication metadata. The queue records the current embedded/routed metadata, the issue flags, first-ten-page text, rendered first-page evidence, detected edited-book/chapter layout, distinctive body quotes, and targeted search links. Text extraction is parsimonious and method-aware: native text is scored first, and `ocrmypdf --skip-text` or `ocrmypdf --force-ocr` are attempted only when front-matter text remains weak.

The metadata investigation queue now follows a staged evidence hierarchy. It first inspects the first three pages because AMNH reprint stamps, handwritten curator notes, author/title blocks, journal headers, and book-chapter title pages are usually visible there. PDF annotation text is extracted when available, and rendered page images are kept as visual evidence for annotations or layout not captured by OCR. If the first three pages do not provide enough evidence, the queue expands to the first ten pages. Only after local evidence is exhausted does the workflow rely on broader search links or distinctive full-text quote searches.

For records already flagged as weak, the queue can run a deeper OCR comparison even when native text is abundant. This is necessary for older scans where native text may contain many words but still misread title pages, author names, accents, tables of contents, or handwritten annotations. The workflow records the selected extraction method, front-matter text score, full-text score, and every OCR attempt so later metadata decisions remain auditable.

For contemporary AMNH and taxonomic-history batches, Mammal Diversity Database Chiroptera records are treated as a priority authority layer. Candidate names and synonyms extracted from the first ten pages should be cross-referenced against local MDD exports when available. MDD matches can identify the taxon, original-description authority, and authority links that help focus bibliographic searches, but they do not by themselves overwrite PDF metadata. Final embedding still requires a high-confidence structured match or curated evidence.

MDD and AMNH priority files should be stored under `index/mdd/`. The investigation queue accepts a flexible CSV via `--mdd-priority-csv`; it looks for citation, reference, authority, title, taxon, scientific-name, and query-like columns. When local PDF evidence overlaps with a priority-list row, the row is reported as an MDD priority match and its citation/search query is used ahead of generic web searches. If no local MDD priority file is configured, the report records that explicitly so the missing authority layer is visible rather than silently skipped.

The current local AMNH tracker is stored as `index/mdd/AMNH_Bat_Original_Descriptions_Tracker.csv`. It was copied from the earlier `bat_original_descriptions.csv` output and contains species, original name, author/date of original description, full citation, BHL/DOI/PDF link, BatLit status, and MDD taxon URL. Large reference sources such as the HMW 2019 reference-list PDF are stored locally under `index/reference_sources/` and are intentionally not committed to Git.

For future taxonomic-paper batches, the MDD data should be refreshed before the investigation queue is run. The current release should be checked at run time, downloaded, filtered to Chiroptera, and transformed into a priority citation file containing accepted names, synonyms, original names, authority species strings, `authoritySpeciesLink`, DOI/BHL/PDF links, and MDD taxon URLs. This priority file should then be used before Google Scholar, BHL, Crossref, OpenAlex, or quote-search fallbacks. The MDD version, release date, source URL, and fetch date should be recorded in the queue summary for reproducibility.

## Duplicate Classification

Incoming PDFs are first compared with the BatLit corpus using exact MD5 hash matches, DOI matches from front matter, and normalized title/author/year matches. The workflow also compares PDFs within the current incoming batch using the same evidence classes. Exact hash and DOI matches are treated as confirmed duplicates. Title/author/year matches are treated as likely duplicates for manual review. The report records whether a match came from the BatLit corpus or from the current incoming batch.

## Routing

After screening, files are copied into timestamped `processed_runs/` folders. Confirmed duplicates are routed to `duplicates/`; high-confidence possible duplicates are routed to `likely_duplicates/`; new candidate literature is routed to `new_literature/`; and likely out-of-scope items are routed to `non_bat_review/`. For Bates 2026, no files had text-extraction errors and no `failed_processing/` folder was produced.

## Duplicate-Omitted Review Sets

For Bates 2026, confirmed duplicates were omitted from the next-stage review folders. The folder `Deduplicated_new_literature/` contains candidate new literature for metadata review and Zotero ingestion. The folder `Deduplicated_likely_duplicates/` contains possible duplicates that should be reviewed manually before any Zotero import. Manifests are written inside each folder and as a combined run-level manifest.

## Metadata Embedding

After routing, bibliography metadata is embedded into the routed PDF copies using PDF document information fields. Embedded fields include title, author, DOI, year, BatLit decision, decision reason, original filename, hashes, and Zotero/BatLit match identifiers where available. This step is intended to make the routed PDFs easier to inspect and import into Zotero while preserving separate CSV/XLSX audit records.

Zotero testing with the AMNH batch showed that embedded PDF document properties alone are not enough for many scanned historical items. Zotero's retrieve-metadata workflow primarily uses text from the first pages plus online identifier and bibliographic lookup services, and it may leave older scans as standalone attachments even when the PDF contains curated document-info metadata. Therefore the pipeline now creates a Zotero import package for curated batches. The package keeps the metadata-enhanced PDFs together with a single RIS file, BibTeX file, CSV manifest, and import README. The RIS records include title, author, year, journal or source-work fields, volume, issue, pages, DOI/ISSN when available, abstract, source URL, BatLit provenance notes, and relative file links to the PDFs. For weak Zotero recognition cases, the preferred ingestion path is Zotero `File > Import` on the RIS file rather than dragging PDFs alone.

After manual Zotero testing, the RIS package was revised again because some records imported with only a parent title even though the curated CSV contained authors, journal, year, volume, issue, pages, and abstract. The RIS exporter now writes more Zotero-friendly journal fields (`T1`, `T2`, `JF`, `JO`, `JA`), writes both `PY` and `Y1`, splits page ranges into `SP` and `EP`, and writes abstracts as `N2`. The Lazell and Koopman 1985 Florida Scientist paper was used as the test case: the first two PDF pages contained the needed citation clues, and JSTOR stable record `https://www.jstor.org/stable/24319878` confirmed the full citation. The resolved CSV, RIS manifest, and embedded PDF provenance were updated to prefer the JSTOR stable citation record over the weaker aggregator link.

When citation metadata is improved after the initial run, the updated fields are embedded into Zotero-ready PDF copies rather than stored only in sidecar CSV files. For verified external or taxonomic-clue resolutions, embedded fields include title, author, year, DOI, journal, volume, issue, pages, ISSN, source URL, metadata source, and confidence label. Unverified clue rows remain in CSV review outputs and are not written into PDFs.

The final Zotero upload set is rebuilt from the curated embedded metadata report, not from preliminary routed filenames. A PDF is considered Zotero ready only when the report records `status=embedded` and a confidence label of `curated`, `verified`, or `high`. PDFs with unknown authors, placeholder titles, suspicious taxonomic years, or unverified MDD/search clues remain in `Needs_Metadata_Investigation_PDFs/`. During the 2026-08-27 AMNH rebuild, this stricter gate placed only the curated Koopman 1988 chapter in `Zotero_Ready_PDFs/` and moved the other 24 PDFs into the investigation folder.

On 2026-08-27, a first AMNH citation-resolution pass used local first-page/first-ten-page evidence plus MDD, BHL, Zenodo, Google Books, INIST/Pascal, and indexed scholarly reference lists to embed richer metadata into 21 additional PDFs. The active AMNH ready set therefore contains 22 PDFs with embedded citation metadata, source URLs, evidence-source notes, confidence labels, and short abstract/summary fields. The remaining unresolved records are `Orig, 2026.pdf`, `Unknown, 1959.pdf`, and `Unknown, 1973.pdf`; these remain in the investigation folder until enough evidence exists to embed metadata safely.

Superseded AMNH clue folders, stale queues, older ready/needs splits, troubleshooting copies, and stray document copies are archived under `batlit-dedupe/archive/`. Active metadata-enrichment folders should contain only current Zotero-ready PDFs, current needs-investigation PDFs, current resolved-metadata CSVs, and current queue/readme files.

## Plazi, BLR, And BHL Prior Art

The BatLit workflow overlaps with biodiversity-literature infrastructure developed by Plazi, Zenodo, Pensoft, and BHL. Plazi TreatmentBank liberates data from taxonomic publications and disseminates taxonomic treatments, treatment citations, figures, tables, material citations, bibliographic references, and links to GBIF and other biodiversity infrastructures. The Biodiversity Literature Repository (BLR) is the Zenodo-based FAIR repository for publications, treatments, and figures enhanced with persistent identifiers and rich metadata. Plazi tools such as GoldenGATE Imagine and services such as RefBank are relevant models for extraction, quality control, and reference cleanup.

BHL is especially relevant for historical bat literature because it provides open bibliographic metadata, article/part records, page metadata, OCR text, page images, and identifiers through API v3. Future BatLit metadata passes should query BHL title/item/part/page metadata before broad web searching when a PDF appears to be an older scan, BHL excerpt, reprint, or taxonomic original-description source.

These systems should be incorporated as authority and provenance layers rather than unreviewed replacements for human judgment. A BatLit resolved citation should record local PDF evidence, MDD/HMW taxonomic clue matches, BHL/BLR/Zenodo/RefBank identifiers where available, and external bibliographic sources used to support the final embedded metadata.

## Audit Outputs

The pipeline writes CSV and XLSX bibliographies for each routed folder, collection-level action logs, routing reports, dedupe reports, metadata embedding reports, and timestamped manifests. These files preserve the decisions made for each PDF and allow later reconstruction of what was added, excluded, or sent to manual review.

## Clean Rerun and Archive Policy

When a collection is reprocessed, the original incoming batch is treated as the source of truth and the full sequence is rerun: deduplication, routing, metadata embedding, curated metadata fallback, derived-folder synchronization, deduplicated review manifest creation, and collection action-log generation. Derived folders are not edited as independent sources; they are refreshed from the routed folders after metadata improvement.

For the Bates 2026 rerun on 2026-06-29, the active run folder is `processed_runs/20260629_111835_Bates_2026_rerun/`. The run retained 544 confirmed duplicates, 93 likely duplicates, 2,472 candidate new-literature PDFs, and 394 non-bat review PDFs. The Zotero upload set is `processed_runs/20260629_111835_Bates_2026_rerun/20260629_114341_zotero_upload/`, containing the metadata-enhanced new-literature PDFs only.

Superseded outputs are preserved under `archive/` rather than deleted. When Windows or Dropbox prevents moving a large folder, a non-destructive archive copy is created and the original is marked with `_SUPERSEDED_DO_NOT_USE.txt` until it can be retired.

## Citation Network Seed Extraction

A citation-network phase was added as an optional downstream step. The workflow scans duplicate-omitted review sets, extracts full text, identifies the cited-reference section using common headings such as `References`, `Literature cited`, and `Bibliography`, and splits that section into candidate reference strings. For each cited reference, the script records the source PDF, reference text, DOI when present, URL when present, year, guessed authors, guessed title, and a stable reference key. A separate edge-list file records source PDF to cited-reference relationships for network analysis.

This phase is intended first as a track-down and network-building aid. Automated downloading should be limited to clearly open-access PDFs or files explicitly obtained through authorized user or library access. Paywalled literature should be recorded as DOI/URL/title candidates for manual retrieval through the user's museum library VPN or other authorized access route.
