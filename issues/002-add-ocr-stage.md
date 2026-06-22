# Add OCR Stage

## Goal

Automatically create searchable PDFs or sidecar text files for scanned PDFs.

## Candidate Tool

Use `ocrmypdf` for OCR and `pdftotext` for text extraction.

## Acceptance Criteria

- Detects whether a PDF already has extractable text.
- OCRs PDFs with poor or missing text.
- Preserves the original PDF.
- Writes derived OCR files to `work/ocr/`.
- Records OCR status in the report.
