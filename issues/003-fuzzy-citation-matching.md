# Add Fuzzy Citation Matching

## Goal

Detect likely duplicates when DOI and file hash matching are not enough.

## Matching Signals

```text
normalized title
first author
year
journal
volume
pages
first page text fingerprint
```

## Acceptance Criteria

- Produces a transparent match score.
- Separates confirmed duplicates from likely duplicates.
- Routes ambiguous cases to manual review.
- Writes candidate BatLit matches into the CSV report.
