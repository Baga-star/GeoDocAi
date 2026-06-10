# GeoDoc AI Redesign — Basalt Atlas

## 1. Visual direction

**Basalt Atlas** turns GeoDoc AI from a chat-first prototype into a professional geology workspace. The interface combines GIS shell layout, scientific editorial calm, data-table ergonomics and evidence-first provenance.

The mood is premium scientific software: basalt and graphite surfaces, layered panels, restrained azurite and hydro accents, lithology ochre for geologic context, crisp vector icons, subtle contour/grid patterns and no emoji-based UI language.

## 2. Design principles

1. **Evidence first**: tables, figures and maps are primary objects. The AI summary supports evidence; it does not replace it.
2. **Scientific premium**: no neon, no cyberpunk, no decorative glow, no playful AI patterns.
3. **Geological identity**: stratigraphy layers, contour lines, drill trajectory, map grids and core-sample geometry define the visual language.
4. **Provenance is visible**: every artifact exposes type, document, page, confidence and extraction status.
5. **Data-heavy by default**: wide tables, sticky headers, frozen first column, density modes and horizontal scrolling are core UX.
6. **Accessible and calm**: high contrast, focus states, semantic labels, keyboard-friendly tabs and predictable panel order.

## 3. Information architecture

### Global shell

- **Top header**: brand, active document, quick search, backend/OCR/model status.
- **Action rail**: upload, overview, tables, figures, maps, sources, settings.
- **Evidence panel**: upload dropzone, indexed documents, entity chips, linked artifact cards, demo verification questions.
- **Main canvas**: overview, table workspace, figure viewer, map workspace, document pages, sources.
- **Copilot panel**: query composer, answer summary, provenance stack, follow-up actions and recent context.

### Tabs

- Overview: answer summary plus strongest evidence cards.
- Tables: first-class table workspace.
- Figures: clean viewer for sections, schemes, columns and diagrams.
- Maps: geospatial viewer with legend and coordinates.
- Pages: source-page grouping.
- Sources: expandable provenance cards.

## 4. User flows

### Upload and index

1. User drops PDF, DOCX, Excel, CSV or image.
2. UI shows pipeline: Upload, Parse, OCR, Artifacts, Index, Ready.
3. Documents list updates with counts for tables, figures and maps.
4. User asks a geology-specific question.
5. Workspace routes to the best artifact-first tab.

### Table-first question

1. User asks about physical-mechanical properties, intervals, depth, strata or units.
2. Main canvas opens Tables tab.
3. Table toolbar provides search, filter, export and full-screen mode.
4. Copilot explains summary and provenance.
5. Sources tab can expand exact chunks.

### Figure/map question

1. User asks about cross-section, lithology, structural map, contour or wells.
2. Main canvas opens Figures or Maps tab.
3. Viewer shows title, source, page, metadata, legend and linked entities.
4. User can open source page or compare related artifacts.

## 5. Wireframes

### Desktop

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ Brand  Active document                 Quick search       Backend OCR Model │
├──────┬────────────────┬────────────────────────────────┬──────────────────┤
│ Rail │ Evidence panel │ Main canvas                     │ Copilot panel    │
│      │ Docs           │ Summary bar                     │ Question         │
│      │ Artifacts      │ Tabs                            │ Answer summary   │
│      │ Filters        │ Table/Figure/Map/Page viewer    │ Provenance       │
│      │ Sources        │                                │ Follow-ups       │
└──────┴────────────────┴────────────────────────────────┴──────────────────┘
```

### Tablet

```text
┌─────────────────────────────────────────┐
│ Brand + quick status                    │
├──────┬──────────────────────────────────┤
│ Rail │ Main canvas                      │
│      │ Tabs + artifact workspace        │
└──────┴──────────────────────────────────┘
Evidence and Copilot become drawers/bottom panels.
```

### Mobile

```text
┌──────────────────────────────┐
│ Header                       │
├──────────────────────────────┤
│ Canvas                       │
│ Tables scroll horizontally   │
├──────────────────────────────┤
│ Bottom action rail           │
└──────────────────────────────┘
Copilot becomes a bottom sheet pattern.
```

## 6. High-fidelity mockup coverage in code

The current implementation contains coded high-fidelity states for:

- upload empty state with geological illustration;
- evidence-first shell layout;
- summary bar with confidence and artifact counts;
- table workspace with toolbar, density switch, sticky header and frozen first column;
- figure viewer with metadata side panel;
- map workspace with legend and coordinate strip;
- source/provenance disclosure cards;
- responsive desktop/laptop/tablet/mobile behavior.

## 7. Design system

### Color tokens

#### Basalt Dark

- `--bg-app`: application background.
- `--bg-basalt`: canvas background.
- `--surface-canvas`: central workspace surface.
- `--surface-panel`: panel surface.
- `--surface-raised`: nested card surface.
- `--surface-elevated`: higher emphasis surface.
- `--line-subtle`, `--line-default`, `--line-strong`: separators.
- `--text-primary`: limestone white.
- `--text-secondary`: muted mineral gray.
- `--text-muted`, `--text-faint`: low-emphasis text.
- `--accent-azurite`: primary action and active state.
- `--accent-hydro`: geospatial/map accent.
- `--accent-lithology`: geology/context accent.
- `--accent-copper`: warning and partial OCR.
- `--accent-moss`: success and verified source.

#### Field Notebook Light

A light token block is included as `[data-theme="field-notebook-light"]`. It reuses semantic roles instead of random new colors.

### Typography

- Sans: system Inter-style stack for interface and Russian/Kazakh readability.
- Mono: SFMono/Roboto Mono stack for coordinates, units, page metadata and numeric values.
- Hierarchy: eyebrow, heading, summary, body, caption, source metadata.

### Spacing and radii

- Radius scale: `--radius-xs`, `--radius-sm`, `--radius-md`, `--radius-lg`, `--radius-xl`.
- Panels use 16-18px internal padding.
- Dense cards use 8-12px rhythm.
- Tables use mode-dependent padding.

### Icon rules

- Lucide vector icons only.
- No emoji in buttons, cards, statuses, table labels or onboarding.
- Icons are 13-20px in dense UI, 24-34px in illustration and empty-state UI.
- Technical, flat, high-legibility style.

### Illustration rules

- Inline SVG illustrations based on stratigraphic layers, contour lines, map grids, rock surfaces and drilling trajectory.
- Used in upload, empty states and viewer placeholders.
- Never placed behind dense tables or long text where readability can suffer.

### Motion rules

- Short, functional transitions only.
- Upload progress and spinner are the only active motion states.
- `prefers-reduced-motion` is respected.

### Component states

- Interactive states: default, hover, active, disabled, focus-visible.
- Confidence states: high, medium, low.
- Source states: verified, OCR, AI-derived, low confidence.
- Upload states: idle, uploading, success, error, dragging.

## 8. Component inventory

- `AppShell`
- `TopHeader`
- `ActionRail`
- `EvidencePanel`
- `CanvasWorkspace`
- `CopilotPanel`
- `SummaryBar`
- `WorkspaceTabs`
- `UploadDropzone`
- `ArtifactCard`
- `SourceDisclosure`
- `TableWorkspace`
- `FigureWorkspace`
- `MapWorkspace`
- `PagesWorkspace`
- `SourcesWorkspace`
- `QueryComposer`
- `StatusPill`
- `ConfidenceChip`
- `ProvenanceChip`
- `EmptyArtifactState`
- `GeologyIllustration`

## 9. React/CSS implementation structure

Current compact hackathon structure keeps everything inside `src/main.tsx` and `src/styles.css`. For production, split into:

```text
src/
  app/App.tsx
  api/client.ts
  design/tokens.css
  design/themes.css
  components/shell/TopHeader.tsx
  components/shell/ActionRail.tsx
  components/evidence/EvidencePanel.tsx
  components/evidence/ArtifactCard.tsx
  components/workspace/CanvasWorkspace.tsx
  components/workspace/TableWorkspace.tsx
  components/workspace/FigureWorkspace.tsx
  components/workspace/MapWorkspace.tsx
  components/copilot/CopilotPanel.tsx
  components/upload/UploadDropzone.tsx
  components/illustrations/GeologyIllustration.tsx
  lib/artifacts.ts
  lib/markdown.tsx
```

### CSS naming

Use component-level BEM-like names:

- `.top-header`
- `.action-rail`
- `.evidence-panel`
- `.canvas-shell`
- `.workspace-block`
- `.artifact-card.table`
- `.source-disclosure.map`
- `.data-table-wrap.analytical`

### State variants

Use semantic class variants:

- `.online`, `.offline`, `.checking`, `.ready`
- `.high`, `.medium`, `.low`
- `.uploading`, `.success`, `.error`, `.dragging`
- `.table`, `.figure`, `.map`, `.text`

## 10. Keep, delete, replace

### Keep

- Existing backend API contract.
- Upload flow.
- `/documents/list` document counters.
- `/chat` structured response with `tables`, `figures`, `maps`, `sources`, `confidence`.
- Local artifact rendering logic.

### Delete completely

- Chat-first dashboard as the primary product model.
- Emoji labels in tables, source cards, statuses and onboarding.
- Single generic sidebar as the main navigation.
- Generic SaaS blue everywhere.
- Tables as small nested message cards.

### Replace with

- Shell layout with rail, evidence panel, canvas and copilot.
- Real vector icon system.
- Evidence-first artifact cards.
- Dedicated table, figure and map workspaces.
- Role-based color tokens and responsive drawers/bottom sheet behavior.
