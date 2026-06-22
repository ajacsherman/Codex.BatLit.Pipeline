# Build BatLit Fingerprint Index

## Goal

Create a lightweight index independent of Zotero that can be used to screen incoming PDFs before import.

## Proposed Fields

```text
batlit_corpus_version
zotero_item_id
zotero_attachment_id
attachment_hash_md5
doi
normalized_title
normalized_authors
year
journal
volume
issue
pages
page_count
first_page_text_fingerprint
first_3_pages_text_fingerprint
```

## Acceptance Criteria

- Reads BatLit `refs.csv`.
- Writes a portable SQLite or CSV index.
- Supports exact DOI lookup.
- Supports exact attachment hash lookup.
- Documents how to regenerate the index.
