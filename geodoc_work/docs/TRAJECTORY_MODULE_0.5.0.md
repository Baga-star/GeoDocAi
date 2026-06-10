# GeoDoc AI 0.5.0 — Trajectory Module

## Что добавлено

Добавлен отдельный bounded context `app/trajectory` для инженерного анализа траекторий скважин. Существующий document/RAG контур не переписан и не удален: `/api/documents/*`, `/api/chat`, `/api/health`, `/api/capabilities` остаются совместимыми.

## Архитектура

Backend:

- `backend/app/trajectory/extract.py` — normalization layer для survey/project profile таблиц, поддерживает русские и английские варианты колонок, сохраняет provenance на уровне строки.
- `backend/app/trajectory/math.py` — deterministic engineering calculations: validation, minimum curvature, plan/profile/3D series, project profile, deviation, interwell separation, forecast service contract/basic hold.
- `backend/app/trajectory/store.py` — SQLite persistence для Project, Well, SourceDocumentLink, SurveyStation, DesignSegment, ComputedTrajectoryPoint, DeviationResult, SeparationResult, ExportJob.
- `backend/app/trajectory/report.py` — Excel workbook: Summary, SurveyData, ComputedCoordinates, Plan, Profile, Design, Deviation, Separation, Sources, Warnings.
- `backend/app/routes/trajectory.py` — typed FastAPI endpoints.

Frontend:

- `frontend/src/features/trajectory/*` — отдельная feature-папка для режима «Траектории».
- `TrajectoryModeSwitch` — переключатель «Документы / Траектории».
- `TrajectoryNavigator` — автоматическое дерево Project → Group views → Wells → Well views.
- `PlanView`, `ProfileView`, `ThreeDView`, `DesignView`, `DeviationView`, `SeparationView`, `TrajectoryDataGrid`, `ExportReportButton`.
- Plotly используется в React через lightweight runtime loader CDN, чтобы не утяжелять npm-зависимости.

## API

- `POST /api/trajectory/import-survey`
- `POST /api/trajectory/import-project-profile`
- `POST /api/trajectory/recalculate/{well_id}`
- `GET /api/trajectory/project/{project_id}/plan`
- `GET /api/trajectory/project/{project_id}/3d`
- `GET /api/trajectory/project/{project_id}/separation`
- `GET /api/trajectory/project/{project_id}/tree`
- `GET /api/trajectory/tree`
- `GET /api/trajectory/well/{well_id}/data`
- `GET /api/trajectory/well/{well_id}/plan`
- `GET /api/trajectory/well/{well_id}/profile?azimuth=...`
- `GET /api/trajectory/well/{well_id}/3d`
- `GET /api/trajectory/well/{well_id}/design`
- `GET /api/trajectory/well/{well_id}/deviation`
- `POST /api/trajectory/well/{well_id}/forecast`
- `GET /api/trajectory/well/{well_id}/report.xlsx`

## Проверка

Backend:

```bash
cd backend
python -m pytest -q tests
```

Frontend:

```bash
cd frontend
npm install
npm run build
npm run test:smoke
```

## Быстрый manual check

1. Запустить backend:

```bash
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

2. Импортировать survey:

```bash
curl -X POST http://localhost:8001/api/trajectory/import-survey \
  -H "Content-Type: application/json" \
  -d '{
    "project_name":"Navigator Demo",
    "well_name":"Well-A",
    "approved":true,
    "magnetic_declination":0,
    "columns":["MD","Inc","Azi"],
    "rows":[[0,0,0],[100,0,0],[200,10,90],[300,20,95]]
  }'
```

3. Взять `well_id`, выполнить:

```bash
curl -X POST http://localhost:8001/api/trajectory/recalculate/<well_id>
```

4. Открыть frontend:

```bash
cd frontend
npm install
npm run dev
```

5. Переключиться в «Траектории» и проверить:

- дерево строится автоматически;
- «Карта проекта» открывает полный экран плана;
- «Профиль» открывает полный экран профиля;
- «3D» показывает траекторию;
- «Excel» скачивает workbook;
- в «Данные» виден provenance / source traceability.

## Phase 2 TODO

- uncertainty-aware collision avoidance вместо pointwise MVP separation;
- advanced forecast с BHA, DLS limits, steering model, target window;
- source-page deep links в UI;
- richer domain editing для проектных сегментов;
- серверный рендер Plotly-изображений для вставки в Excel;
- миграции Alembic/SQLAlchemy, если проект уйдет в production persistence.
