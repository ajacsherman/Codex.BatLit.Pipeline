# Route PDFs Into Review Folders

## Goal

Move or copy incoming PDFs into review categories after scoring.

## Categories

```text
duplicates/
likely_duplicates/
new_literature/
manual_review/
non_bat_review/
failed_processing/
```

## Acceptance Criteria

- Default behavior copies files rather than moving them.
- Produces a routing report.
- Never deletes input PDFs.
- Can run in dry-run mode.
