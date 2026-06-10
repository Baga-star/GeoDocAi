# GeoDoc AI v0.5.2 — trajectory empty-state/import UX fix

## Problem
Trajectory mode opened correctly, but when trajectory storage had no survey/project-profile rows the UI looked like a broken blank module.

## Fix
- Added explicit empty state: explains that trajectory DB has no inclinometry data yet.
- Added `POST /api/trajectory/seed-demo` for one-click demo data.
- Added `POST /api/trajectory/import-from-documents` to scan existing indexed table artifacts and import trajectory-compatible tables.
- Added sidebar buttons:
  - Auto-import from uploaded documents
  - Demo data
  - Refresh tree
- Added tests for demo seeding and dynamic tree.

## Validation
- Backend tests: `17 passed`
- Frontend build: passed
- Frontend smoke: passed
