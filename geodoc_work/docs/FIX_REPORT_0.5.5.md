# GeoDoc AI v0.5.5 — readable answer and UI cleanup

Fixed:
- Removed raw evidence/source sections from the main Answer tab unless the user explicitly asks for sources.
- Added stricter OCR/watermark noise filtering for Kargaly-style PDFs.
- Hidden corrupted table cells instead of showing broken letters as data.
- Preferred PyMuPDF prose extraction when pdfplumber text is contaminated by diagonal watermarks.
- Softened text colors and typography for dark UI readability.
- Removed the Backend online badge from the header.

Important: old indexed documents may still contain stale corrupted artifacts. Delete and re-upload the PDF after this update to rebuild a clean index.
