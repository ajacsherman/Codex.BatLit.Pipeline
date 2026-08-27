# AMNH Recovery Plan - 2026-08-27

This file is the current operating plan after the AMNH/Zotero metadata failure.

## What Went Wrong

The AMNH scan workflow moved too quickly from PDF cleanup to metadata embedding and Zotero import. It did not enforce a separate online-availability audit before treating AMNH scans as uniquely valuable local objects.

The Lazell and Koopman 1985 paper exposed the failure. The scan contained enough title-page evidence, and the paper has a JSTOR stable record, but the pipeline initially accepted weaker citation evidence and focused on Zotero import behavior rather than first asking whether the paper was already available online.

## New Required Gate

Every AMNH/taxonomic batch now requires an online availability audit before Zotero import or metadata packaging.

The audit must distinguish:

- `already_in_batlit`
- `jstor_record_found`
- `online_scan_candidate_found`
- `online_metadata_or_identifier_found`
- `api_candidates_need_review`
- `needs_online_review`

The key output for the current AMNH batch is:

```text
batlit-dedupe/metadata_enrichment/AMNH_20260827/AMNH_20260827_online_availability_audit_with_apis.csv
```

Current AMNH audit summary:

```text
jstor_record_found: 1
online_metadata_or_identifier_found: 3
online_scan_candidate_found: 3
already_in_batlit: 1
api_candidates_need_review: 12
```

`api_candidates_need_review` means a service returned a possible result, but title similarity was too low to trust automatically.

## What To Do Today

1. Stop testing PDF drag-and-drop in Zotero for AMNH scans.
2. Open the online availability audit CSV.
3. Review rows in this order:
   - `already_in_batlit`
   - `jstor_record_found`
   - `online_scan_candidate_found`
   - `online_metadata_or_identifier_found`
   - `api_candidates_need_review`
   - `needs_online_review`
4. For each row, decide whether the AMNH scan is:
   - redundant because BatLit/Zenodo/BHL/JSTOR/IA already has it;
   - useful as a better scan;
   - useful because it is an excerpt from a larger source;
   - useful because it has annotations or archival context;
   - still unresolved.
5. Only after that, generate Zotero records from curated metadata.

## Zotero Import Rule

For these historical/taxonomic records, Zotero should receive citation records directly from BatLit-curated data, not infer them from PDFs.

Preferred import files, in order:

```text
AMNH_20260827_Zotero_Import_Package_metadata_only.csl.json
AMNH_20260827_Zotero_Import_Package_metadata_only.ris
```

PDF attachment comes after parent citation records are safely created.

## Source Hierarchy

For AMNH and taxonomic literature, use this evidence order:

1. Existing BatLit/Zotero/Zenodo record.
2. Exact title + author + year online match.
3. MDD/HMW/Zijlstra/original-description tracker.
4. BHL/BioStor/Internet Archive online scans.
5. JSTOR or publisher stable record.
6. Crossref/OpenAlex only if title similarity is high.
7. Google Scholar/manual title search.
8. Local PDF first 3 pages, then first 10 pages.
9. Distinctive quote search.
10. Manual review.

## Non-Negotiable Rule

No AMNH scan should be called "new literature" or "Zotero-ready" until online availability and BatLit corpus status have been recorded.
