# GeoDoc AI 0.3.1 — applied audit fixes

Физически применённые исправления по приложенному аудиту:

## Backend / security

- `/api/capabilities` возвращает реальное состояние backend, OCR, Vision, LLM, retrieval, demo mode и security.
- CORS больше не доверяет целым private-network диапазонам через regex; используются только explicit origins из `CORS_ORIGINS`.
- `CORS_ALLOW_CREDENTIALS=false` по умолчанию.
- Добавлен optional API key guard. Если `API_KEY` задан, защищены `/api/documents/*` и `/api/chat*`.
- Добавлен in-memory rate limiter для demo/staging.
- Upload validation проверяет safe filename, allowlist расширений, фактический размер и file signatures для PDF/Office/images.

## AI pipeline

- `build_user_prompt()` фильтрует metadata через `SAFE_METADATA_KEYS`.
- `preview_data_url`, `*_data_url`, base64/raw image fields больше не попадают в LLM context.
- Prompt JSON содержит `trust_boundary`: retrieved artifacts явно помечены как untrusted document context.
- Map answer больше не заявляет “карта прочитана”, если vision analysis не выполнен.

## Frontend / UX / a11y

- Header statuses OCR/Vision/Model строятся по `/api/capabilities`, а не hardcoded ready.
- Composer остаётся доступен на mobile breakpoint.
- Markdown list renderer создаёт `<ul><li>` вместо одиночных `<li>`.
- Entity chips теперь запускают реальные follow-up запросы.
- Нереализованные действия отображаются disabled, чтобы не вводить пользователя в заблуждение.
- Усилен контраст `--text-faint`.
- Часть англоязычных UX-labels переведена на русский.

## Verification

- Backend tests: `7 passed`.
- API smoke through FastAPI TestClient: health, capabilities, upload, documents/list, chat — passed.
- Frontend: `npm ci && npm run build` — passed; `npm audit --omit=dev` — 0 vulnerabilities.

## Known limitations

- Persistent Qdrant backend всё ещё не подключён как активный retrieval layer: `/api/capabilities` честно показывает `active_backend: local_in_memory`.
- AV/CDR scanning для upload не реализован в коде, так как требует внешней инфраструктуры. Текущий слой — базовая signature/size/filename защита.
- Viewer/export/fullscreen endpoints пока отсутствуют; соответствующие UI-действия намеренно disabled.
