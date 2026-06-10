# Hackathon Plan

## Team Roles

| Task | Tool | Complexity |
| --- | --- | --- |
| Document upload and parsing | Docling + fallback loaders | Medium |
| Vector DB setup | Qdrant / local index | Medium |
| API integration | FastAPI + Qwen API | Medium |
| Frontend chat | React | Medium |
| Prompts and tuning | Qwen 3.6 | Medium |
| Security and deploy | Docker, on-premise network | High |

## Day 1

- Start local parser and demo index.
- Upload 3-5 test reports: PDF, Excel reserves table, Word conclusion and scanned image.
- Validate text extraction and chunk boundaries.
- Check demo fallback for well, reserve and horizon questions.

## Day 2

- Connect real Qwen credentials.
- Optionally enable Qdrant for persistent retrieval.
- Tune geology prompt on well, reserve and horizon questions.
- Polish UI and source references.
- Prepare demo script and failure fallback.

## Demo Script

1. Upload a scanned geological report or reserve table.
2. Ask: "Какой дебит скважины №12?"
3. Ask: "Сравни запасы по категориям C1 и C2."
4. Ask: "Найди все упоминания горизонта Ю1."
5. Show source chunks and explain that Docling handles parsing/OCR/tables, the backend indexes chunks, and Qwen generates domain-specific answers.
