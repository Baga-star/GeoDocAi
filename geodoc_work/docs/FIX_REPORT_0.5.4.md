# GeoDoc AI v0.5.4 — readable text / OCR watermark cleanup

## Fixed
- Short entity questions such as “Жигулевский ярус” now bypass noisy LLM/table-only summaries and use deterministic evidence synthesis.
- Added PDF text cleanup for diagonal watermark fragments that were appearing as broken letters inside Russian words.
- Sources and answer markdown are cleaned before returning to the frontend.
- Noisy tables are no longer shown as if corrupted OCR letters were valid data; UI shows a warning and points to the source page instead.

## Why
Some scanned/text-layer PDFs contain diagonal approval stamps. pdfplumber can extract those stamps as isolated fragments (`Г`, `Б`, `ва`, `ро`, etc.) and mix them into normal geology prose.
