# GeoDoc AI 0.4.1 — UX cleanup and MapReader answer upgrade

## What was fixed

### Document management
- Added `DELETE /api/documents/{document_id}`.
- Added document removal from the local in-memory index.
- Added a delete control in the document list.
- After deletion, the frontend refreshes the document list and clears answers tied to the removed document.

### Header and confidence UI
- Removed OCR/Vision/LLM badges from the header.
- The header now shows only `Backend` status, as requested.
- Removed confidence badges from the active request and answer card. The backend still returns confidence internally, but the UI no longer exposes an unclear confidence pill.

### Visual titles and map naming
- Removed generated technical phrases such as `карта по визуальным признакам...` from titles and evidence cards.
- Added title sanitization in both backend and frontend.
- Map fallback title is now human-readable: `Структурная карта по кровле пласта`.

### MapReader / AI answers
- Added a local no-API MapReader layer for map-like images.
- Local MapReader now extracts visual evidence such as:
  - colored zones;
  - green/yellow area distribution;
  - blue contours/boundaries;
  - dark isolines/structural lines;
  - red point markers that likely represent wells or control points.
- Map answers now use a clearer structure:
  - `Краткий вывод`;
  - `Источник`;
  - `Легенда`;
  - `Контуры и изолинии`;
  - `Скважины / точки`;
  - `Наблюдения`;
  - `Ограничения` when needed.
- Qwen prompt instructions were updated so the model does not repeat internal classifier phrases and uses visual evidence more clearly.
- The answer override logic now rejects vague/bad map responses containing technical classifier leakage.

## Validation

```bash
cd backend && PYTHONPATH=. pytest -q
# 7 passed

cd frontend && npm ci --offline && npm run build
# TypeScript + Vite build passed

npm audit --omit=dev
# 0 vulnerabilities
```

## Remaining limitation

The new local MapReader can read visual structure from maps without external keys, but exact tiny labels, well numbers and isoline values still require a real high-quality Vision/OCR model and a good scan resolution.
