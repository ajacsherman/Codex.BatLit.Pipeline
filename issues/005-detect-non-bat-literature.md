# Detect Likely Non-Bat Literature

## Goal

Flag papers that are unlikely to be relevant to BatLit before Zotero import.

## Candidate Signals

```text
bat
bats
Chiroptera
species names
bat-focused keywords
BatLit corpus title similarity
reference overlap with BatLit
```

## Acceptance Criteria

- Adds a `bat_relevance_status` column to reports.
- Routes likely out-of-scope items to `non_bat_review/`.
- Keeps uncertain items in `manual_review/`.
