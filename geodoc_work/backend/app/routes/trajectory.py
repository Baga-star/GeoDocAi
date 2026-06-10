from __future__ import annotations

from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.models import DocumentArtifact
from app.security import require_api_key
from app.services.local_index import local_index
from app.trajectory.extract import artifact_to_candidate, normalize_design_tables, normalize_survey_tables
from app.trajectory.math import (
    build_project_profile,
    compute_deviation_from_project,
    compute_forecast_placeholder_or_basic_mode,
    compute_interwell_separation,
    compute_vertical_section,
    minimum_curvature,
    validate_survey_points,
)
from app.trajectory.models import (
    AutoImportTrajectoryRequest,
    AutoImportTrajectoryResponse,
    CandidateTable,
    DeviationResponse,
    ForecastRequest,
    ForecastResponse,
    ImportProjectProfileRequest,
    ImportProjectProfileResponse,
    ImportSurveyRequest,
    ImportSurveyResponse,
    ProjectSeries,
    ProjectTrajectoryResponse,
    RecalculateResponse,
    SeparationResponse,
    SeriesMeta,
    SurveyDataResponse,
    TrajectorySeriesResponse,
    TrajectoryStatus,
    TrajectoryTreeResponse,
    TreeNode,
    ValidationResult,
)
from app.trajectory.report import build_excel_report
from app.trajectory.store import trajectory_store

router = APIRouter(prefix="/trajectory", tags=["trajectory"], dependencies=[Depends(require_api_key)])


def _tables_from_request(request: ImportSurveyRequest | ImportProjectProfileRequest) -> list[CandidateTable]:
    tables: list[CandidateTable] = list(request.tables)
    if request.columns and request.rows:
        tables.append(CandidateTable(columns=request.columns, rows=request.rows))
    artifacts: list[DocumentArtifact] = []
    if request.artifact_id:
        artifact = local_index.get_artifact(request.artifact_id)
        if artifact:
            artifacts.append(artifact)
    elif request.document_id:
        artifacts.extend(local_index.artifacts_for_document(request.document_id, artifact_type="table"))
    for artifact in artifacts:
        candidate = artifact_to_candidate(artifact)
        if candidate:
            tables.append(candidate)
    return tables




def _document_tables(document_id: str | None = None) -> list[CandidateTable]:
    artifacts = local_index.artifacts_for_document(document_id, artifact_type="table")
    return [candidate for artifact in artifacts if (candidate := artifact_to_candidate(artifact)) is not None]


def _seed_demo_data() -> tuple[str, list[str]]:
    project_id = trajectory_store.get_or_create_project("Navigator Demo", "demo")
    wells = {
        "Well-A": [[0, 0, 0], [100, 0, 0], [200, 10, 90], [300, 18, 95], [420, 24, 98]],
        "Well-B": [[0, 0, 0], [120, 2, 45], [240, 8, 70], [360, 12, 75], [480, 14, 78]],
    }
    well_ids: list[str] = []
    for name, rows in wells.items():
        well_id = trajectory_store.get_or_create_well(project_id, name)
        stations, _, _ = normalize_survey_tables(
            [CandidateTable(columns=["MD", "Inc", "Azi"], rows=rows)],
            approved=True,
            magnetic_declination=0,
        )
        trajectory_store.replace_survey(well_id, stations)
        segments, _, _ = normalize_design_tables(
            [CandidateTable(
                columns=["Start MD", "End MD", "Start Inc", "End Inc", "Start Azi", "End Azi", "Corridor"],
                rows=[[0, 120, 0, 0, 0, 0, 10], [120, 300, 0, 15, 0, 90, 10], [300, 480, 15, 24, 90, 98, 12]],
            )],
            approved=True,
            magnetic_declination=0,
        )
        trajectory_store.replace_design(well_id, segments)
        _recalculate_well(well_id)
        well_ids.append(well_id)
    return project_id, well_ids

def _project_or_404(project_id: str) -> dict:
    project = trajectory_store.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Проект траекторий не найден")
    return project


def _well_or_404(well_id: str) -> dict:
    well = trajectory_store.get_well(well_id)
    if not well:
        raise HTTPException(status_code=404, detail="Скважина не найдена")
    return well


def _assert_approved(validation: ValidationResult) -> None:
    if validation.errors:
        raise HTTPException(
            status_code=422,
            detail={
                "message": f"Ошибки валидации: {'; '.join(validation.errors[:3])}",
                "errors": validation.errors,
                "warnings": validation.warnings,
            },
        )
    if validation.status == "needs_approval":
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Данные импортированы, но требуют подтверждения перед расчётом.",
                "warnings": validation.warnings,
            },
        )


def _recalculate_well(well_id: str) -> RecalculateResponse:
    _well_or_404(well_id)
    stations = trajectory_store.list_survey(well_id)
    validation = validate_survey_points(stations)
    _assert_approved(validation)
    actual = compute_vertical_section(minimum_curvature(stations), 0.0)
    trajectory_store.replace_computed(well_id, "actual", actual)

    design_segments = trajectory_store.list_design(well_id)
    design_points = []
    if design_segments:
        if any(not seg.approved for seg in design_segments):
            validation.warnings.append("Проектный профиль есть, но часть сегментов не подтверждена; design layer не пересчитан.")
        else:
            design_points = compute_vertical_section(build_project_profile(design_segments), 0.0)
            trajectory_store.replace_computed(well_id, "design", design_points)
    return RecalculateResponse(
        status=validation.status if validation.status != "needs_approval" else "ok",
        well_id=well_id,
        actual_points=len(actual),
        design_points=len(design_points),
        validation=validation,
    )


def _ensure_computed(well_id: str) -> None:
    if trajectory_store.list_computed(well_id, "actual"):
        return
    _recalculate_well(well_id)


@router.post("/import-survey", response_model=ImportSurveyResponse)
async def import_survey(request: ImportSurveyRequest) -> ImportSurveyResponse:
    tables = _tables_from_request(request)
    stations, validation, inferred_well = normalize_survey_tables(
        tables,
        approved=request.approved,
        magnetic_declination=request.magnetic_declination,
    )
    if validation.errors:
        return ImportSurveyResponse(project_id=request.project_id or "", well_id=request.well_id or "", imported=0, validation=validation)
    project_id = trajectory_store.get_or_create_project(request.project_name, request.project_id)
    well_id = trajectory_store.get_or_create_well(project_id, inferred_well or request.well_name, request.well_id)
    trajectory_store.replace_survey(well_id, stations)
    # Invalidate computed actual/design; final recalc is explicit after manual approval.
    trajectory_store.replace_computed(well_id, "actual", [])
    return ImportSurveyResponse(project_id=project_id, well_id=well_id, imported=len(stations), validation=validation, stations=stations)


@router.post("/import-project-profile", response_model=ImportProjectProfileResponse)
async def import_project_profile(request: ImportProjectProfileRequest) -> ImportProjectProfileResponse:
    tables = _tables_from_request(request)
    segments, validation, inferred_well = normalize_design_tables(
        tables,
        approved=request.approved,
        magnetic_declination=request.magnetic_declination,
    )
    if validation.errors:
        return ImportProjectProfileResponse(project_id=request.project_id or "", well_id=request.well_id or "", imported=0, validation=validation)
    project_id = trajectory_store.get_or_create_project(request.project_name, request.project_id)
    well_id = trajectory_store.get_or_create_well(project_id, inferred_well or request.well_name, request.well_id)
    trajectory_store.replace_design(well_id, segments)
    trajectory_store.replace_computed(well_id, "design", [])
    return ImportProjectProfileResponse(project_id=project_id, well_id=well_id, imported=len(segments), validation=validation, segments=segments)



@router.post("/import-from-documents", response_model=AutoImportTrajectoryResponse)
async def import_from_documents(request: AutoImportTrajectoryRequest) -> AutoImportTrajectoryResponse:
    tables = _document_tables(request.document_id)
    if not tables:
        return AutoImportTrajectoryResponse(
            status="warning",
            validation=ValidationResult(status="warning", warnings=["В document index нет таблиц для импорта."]),
            warnings=["Сначала загрузите документ с таблицей инклинометрии или проектного профиля."],
        )

    # --- Separate design tables from survey tables first ---
    design_tables: list[CandidateTable] = []
    survey_tables: list[CandidateTable] = []
    for table in tables:
        seg_test, _, _ = normalize_design_tables([table], approved=True, magnetic_declination=request.magnetic_declination)
        sta_test, _, _ = normalize_survey_tables([table], approved=True, magnetic_declination=request.magnetic_declination)
        if seg_test and not sta_test:
            design_tables.append(table)
        elif sta_test:
            survey_tables.append(table)

    if not survey_tables and not design_tables:
        return AutoImportTrajectoryResponse(
            status="invalid",
            validation=ValidationResult(status="invalid", errors=["Не найдены колонки MD/зенит/азимут или проектные сегменты."]),
            warnings=["Не найдены колонки MD/зенит/азимут или проектные сегменты."],
        )

    # --- Project name from document ---
    doc_name = None
    if tables and tables[0].provenance and tables[0].provenance.document_name:
        raw = tables[0].provenance.document_name
        doc_name = raw.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").strip()
    project_name = doc_name or request.project_name or "Импортированный проект"
    project_id = trajectory_store.get_or_create_project(project_name, request.project_id)

    # --- Parse shared design segments ---
    all_segments, design_val, design_inferred_well = normalize_design_tables(
        design_tables, approved=True, magnetic_declination=request.magnetic_declination,
    ) if design_tables else ([], ValidationResult(), None)

    total_survey = 0
    total_design = 0
    all_warnings: list[str] = list(design_val.warnings) if design_tables else []
    calc_errors: list[str] = []
    last_well_id: str | None = None
    well_ids_created: list[str] = []
    well_names_created: list[str] = []

    # --- Create ONE well per survey table ---
    for idx, table in enumerate(survey_tables):
        stations, sv, inferred_name = normalize_survey_tables(
            [table], approved=True, magnetic_declination=request.magnetic_declination,
        )
        all_warnings.extend(sv.warnings)
        if not stations:
            continue

        # Derive well name: from data > sheet title > sequential
        raw_title = (table.provenance.table_title or "") if table.provenance else ""
        sheet_name = raw_title.replace("Лист Excel: ", "").strip()
        well_name = (
            inferred_name
            or (sheet_name if sheet_name and sheet_name not in ("Sheet1", "Лист1") else None)
            or request.well_name
            or f"Скважина-{idx + 1}"
        )
        well_id = trajectory_store.get_or_create_well(project_id, well_name, None)
        trajectory_store.replace_survey(well_id, stations)
        trajectory_store.replace_computed(well_id, "actual", [])

        try:
            _recalculate_well(well_id)
        except HTTPException as exc:
            detail = exc.detail
            msg = detail.get("message", str(detail)) if isinstance(detail, dict) else str(detail)
            calc_errors.append(f"{well_name}: {msg}")
            all_warnings.extend(detail.get("warnings", []) if isinstance(detail, dict) else [])

        total_survey += len(stations)
        last_well_id = well_id
        well_ids_created.append(well_id)
        well_names_created.append(well_name)

    # --- Assign design only to the BEST-MATCHING well ---
    # If design has an inferred well name, find matching well; otherwise assign to first well only.
    if all_segments and well_ids_created:
        target_well_id: str | None = None
        if design_inferred_well:
            # Try to find matching well by name similarity
            dn = design_inferred_well.lower()
            for wid, wname in zip(well_ids_created, well_names_created):
                if dn in wname.lower() or wname.lower() in dn:
                    target_well_id = wid
                    break
        if target_well_id is None:
            # Default: assign only to first well (avoids polluting unrelated wells)
            target_well_id = well_ids_created[0]
        trajectory_store.replace_design(target_well_id, all_segments)
        trajectory_store.replace_computed(target_well_id, "design", [])
        total_design += len(all_segments)
        # Re-recalculate to include design
        try:
            _recalculate_well(target_well_id)
        except HTTPException:
            pass

    # If ONLY design tables (no survey), store them on a placeholder well
    if not survey_tables and all_segments:
        well_name = request.well_name or "Скважина-1"
        well_id = trajectory_store.get_or_create_well(project_id, well_name, request.well_id)
        trajectory_store.replace_design(well_id, all_segments)
        trajectory_store.replace_computed(well_id, "design", [])
        total_design += len(all_segments)
        last_well_id = well_id

    final_status: TrajectoryStatus = "ok" if not calc_errors else "warning"
    return AutoImportTrajectoryResponse(
        status=final_status,
        project_id=project_id,
        well_id=last_well_id,
        survey_imported=total_survey,
        design_imported=total_design,
        validation=ValidationResult(status=final_status, warnings=all_warnings, errors=calc_errors),
        warnings=all_warnings[:5] + calc_errors,   # limit noise
    )



@router.post("/seed-demo", response_model=AutoImportTrajectoryResponse)
async def seed_demo() -> AutoImportTrajectoryResponse:
    project_id, well_ids = _seed_demo_data()
    return AutoImportTrajectoryResponse(
        status="ok",
        project_id=project_id,
        well_id=well_ids[0] if well_ids else None,
        survey_imported=10,
        design_imported=6,
        validation=ValidationResult(status="ok"),
        warnings=["Demo данные добавлены только для проверки интерфейса. Их можно удалить, очистив backend/.data/trajectory.sqlite3."],
    )


@router.post("/recalculate/{well_id}", response_model=RecalculateResponse)
async def recalculate(well_id: str) -> RecalculateResponse:
    return _recalculate_well(well_id)


@router.get("/project/{project_id}/tree", response_model=TrajectoryTreeResponse)
async def project_tree(project_id: str) -> TrajectoryTreeResponse:
    project = trajectory_store.get_project(project_id)
    if not project:
        return TrajectoryTreeResponse(status="warning", project_id=None, nodes=[], warnings=["Пока нет импортированных траекторий."])
    wells = trajectory_store.list_wells(project["id"])
    well_nodes: list[TreeNode] = []
    for well in wells:
        wid = well["id"]
        well_nodes.append(
            TreeNode(
                id=wid,
                label=well["name"],
                type="well",
                children=[
                    TreeNode(id=f"{wid}:data", label="Данные", type="view", action="well-data", meta={"well_id": wid, "project_id": project["id"], "well_name": well["name"]}),
                    TreeNode(id=f"{wid}:plan", label="План", type="view", action="well-plan", meta={"well_id": wid, "project_id": project["id"], "well_name": well["name"]}),
                    TreeNode(id=f"{wid}:profile", label="Профиль", type="view", action="well-profile", meta={"well_id": wid, "project_id": project["id"], "well_name": well["name"]}),
                    TreeNode(id=f"{wid}:3d", label="3D", type="view", action="well-3d", meta={"well_id": wid, "project_id": project["id"], "well_name": well["name"]}),
                    TreeNode(id=f"{wid}:design", label="Проектный профиль", type="view", action="well-design", meta={"well_id": wid, "project_id": project["id"], "well_name": well["name"]}),
                    TreeNode(id=f"{wid}:deviation", label="Отклонение", type="view", action="well-deviation", meta={"well_id": wid, "project_id": project["id"], "well_name": well["name"]}),
                    TreeNode(id=f"{wid}:forecast", label="Прогноз", type="view", action="well-forecast", meta={"well_id": wid, "project_id": project["id"], "well_name": well["name"]}),
                    TreeNode(id=f"{wid}:excel", label="Excel", type="view", action="well-excel", meta={"well_id": wid, "project_id": project["id"], "well_name": well["name"]}),
                ],
            )
        )
    root = TreeNode(
        id=project["id"],
        label=project["name"],
        type="project",
        children=[
            TreeNode(
                id=f"{project['id']}:group",
                label="Группа скважин",
                type="group",
                children=[
                    TreeNode(id=f"{project['id']}:plan", label="Карта проекта", type="view", action="project-plan", meta={"project_id": project["id"]}),
                    TreeNode(id=f"{project['id']}:3d", label="3D", type="view", action="project-3d", meta={"project_id": project["id"]}),
                    TreeNode(id=f"{project['id']}:separation", label="Сближение", type="view", action="project-separation", meta={"project_id": project["id"]}),
                ],
            ),
            TreeNode(id=f"{project['id']}:wells", label="Скважины", type="group", children=well_nodes),
        ],
    )
    return TrajectoryTreeResponse(status="ok", project_id=project["id"], nodes=[root])


@router.get("/tree", response_model=TrajectoryTreeResponse)
async def first_tree() -> TrajectoryTreeResponse:
    projects = trajectory_store.list_projects()
    if not projects:
        return TrajectoryTreeResponse(status="warning", project_id=None, nodes=[], warnings=["Нет импортированных траекторий. Нажмите «Demo данные» для быстрого старта."])
    all_nodes: list[TreeNode] = []
    for project in projects:
        sub = await project_tree(project["id"])
        all_nodes.extend(sub.nodes)
    return TrajectoryTreeResponse(
        status="ok",
        project_id=projects[0]["id"],
        nodes=all_nodes,
        warnings=[],
    )


def _well_series_response(well_id: str, layer: str = "actual", azimuth: float = 0.0) -> TrajectorySeriesResponse:
    _well_or_404(well_id)
    _ensure_computed(well_id)
    points = trajectory_store.list_computed(well_id, layer)
    points = compute_vertical_section(points, azimuth)
    return TrajectorySeriesResponse(
        status="ok" if points else "warning",
        well_id=well_id,
        series=points,
        meta=SeriesMeta(display={"azimuth": azimuth, "layers": [layer]}),
        provenance=[p.provenance for p in points if p.provenance],
        warnings=[] if points else [f"Нет рассчитанного слоя {layer}."],
    )


@router.get("/well/{well_id}/data", response_model=SurveyDataResponse)
async def well_data(well_id: str) -> SurveyDataResponse:
    _well_or_404(well_id)
    stations = trajectory_store.list_survey(well_id)
    segments = trajectory_store.list_design(well_id)
    validation = validate_survey_points(stations) if stations else ValidationResult(status="warning", warnings=["Нет survey stations."])
    return SurveyDataResponse(status=validation.status, well_id=well_id, stations=stations, segments=segments, validation=validation)


@router.get("/well/{well_id}/plan", response_model=TrajectorySeriesResponse)
async def well_plan(well_id: str) -> TrajectorySeriesResponse:
    return _well_series_response(well_id, "actual")


@router.get("/well/{well_id}/profile", response_model=TrajectorySeriesResponse)
async def well_profile(well_id: str, azimuth: float = Query(0.0, ge=0, le=360)) -> TrajectorySeriesResponse:
    return _well_series_response(well_id, "actual", azimuth)


@router.get("/well/{well_id}/3d", response_model=TrajectorySeriesResponse)
async def well_3d(well_id: str) -> TrajectorySeriesResponse:
    return _well_series_response(well_id, "actual")


@router.get("/well/{well_id}/design", response_model=TrajectorySeriesResponse)
async def well_design(well_id: str, azimuth: float = Query(0.0, ge=0, le=360)) -> TrajectorySeriesResponse:
    _well_or_404(well_id)
    if not trajectory_store.list_computed(well_id, "design"):
        _recalculate_well(well_id)
    points = compute_vertical_section(trajectory_store.list_computed(well_id, "design"), azimuth)
    return TrajectorySeriesResponse(
        status="ok" if points else "warning",
        well_id=well_id,
        series=points,
        meta=SeriesMeta(display={"azimuth": azimuth, "layers": ["design"]}),
        warnings=[] if points else ["Проектный профиль не импортирован или не подтвержден."],
    )


@router.get("/well/{well_id}/deviation", response_model=DeviationResponse)
async def well_deviation(well_id: str) -> DeviationResponse:
    _well_or_404(well_id)
    _ensure_computed(well_id)
    actual = trajectory_store.list_computed(well_id, "actual")
    design = trajectory_store.list_computed(well_id, "design")
    if not design and trajectory_store.list_design(well_id):
        _recalculate_well(well_id)
        design = trajectory_store.list_computed(well_id, "design")
    rows = compute_deviation_from_project(actual, design)
    max_distance = max((row.distance_m or 0 for row in rows), default=None)
    return DeviationResponse(
        status="ok" if rows else "warning",
        well_id=well_id,
        rows=rows,
        max_distance_m=max_distance,
        warnings=[] if rows else ["Для отклонения нужен импортированный и подтвержденный проектный профиль."],
    )


@router.post("/well/{well_id}/forecast", response_model=ForecastResponse)
async def well_forecast(well_id: str, request: ForecastRequest) -> ForecastResponse:
    _well_or_404(well_id)
    _ensure_computed(well_id)
    actual = trajectory_store.list_computed(well_id, "actual")
    return compute_forecast_placeholder_or_basic_mode(well_id, actual, request)


def _project_series(project_id: str, layer: str = "actual") -> ProjectTrajectoryResponse:
    project = _project_or_404(project_id)
    warnings: list[str] = []
    series: list[ProjectSeries] = []
    for well in trajectory_store.list_wells(project["id"]):
        try:
            _ensure_computed(well["id"])
        except HTTPException as exc:
            warnings.append(f"{well['name']}: {exc.detail}")
            continue
        points = trajectory_store.list_computed(well["id"], layer)
        if points:
            series.append(ProjectSeries(well_id=well["id"], well_name=well["name"], layer=layer, points=points))
    return ProjectTrajectoryResponse(status="ok" if series else "warning", project_id=project["id"], series=series, warnings=warnings)


@router.get("/project/{project_id}/plan", response_model=ProjectTrajectoryResponse)
async def project_plan(project_id: str) -> ProjectTrajectoryResponse:
    return _project_series(project_id, "actual")


@router.get("/project/{project_id}/3d", response_model=ProjectTrajectoryResponse)
async def project_3d(project_id: str) -> ProjectTrajectoryResponse:
    return _project_series(project_id, "actual")


@router.get("/project/{project_id}/separation", response_model=SeparationResponse)
async def project_separation(project_id: str) -> SeparationResponse:
    project = _project_or_404(project_id)
    wells = []
    warnings: list[str] = []
    for well in trajectory_store.list_wells(project["id"]):
        try:
            _ensure_computed(well["id"])
        except HTTPException as exc:
            warnings.append(f"{well['name']}: {exc.detail}")
            continue
        wells.append((well["id"], well["name"], trajectory_store.list_computed(well["id"], "actual")))
    rows = compute_interwell_separation(wells)
    return SeparationResponse(status="ok" if rows else "warning", project_id=project["id"], rows=rows, warnings=warnings or ([] if rows else ["Нужно минимум две рассчитанные скважины."]))


@router.get("/well/{well_id}/report.xlsx")
async def well_report(well_id: str):
    well = _well_or_404(well_id)
    _ensure_computed(well_id)
    actual = compute_vertical_section(trajectory_store.list_computed(well_id, "actual"), 0.0)
    design = compute_vertical_section(trajectory_store.list_computed(well_id, "design"), 0.0)
    deviation_rows = compute_deviation_from_project(actual, design) if design else []
    separation_rows = compute_interwell_separation(
        [
            (w["id"], w["name"], trajectory_store.list_computed(w["id"], "actual"))
            for w in trajectory_store.list_wells(well["project_id"])
        ]
    )
    stations = trajectory_store.list_survey(well_id)
    survey_rows = [
        {
            "md": s.md,
            "inc": s.inclination,
            "azi": s.azimuth,
            "magnetic_declination": s.magnetic_declination,
            "approved": s.approved,
            "source": f"{s.provenance.document_name or ''} p.{s.provenance.page or ''} row {s.provenance.row_index or ''}" if s.provenance else "",
        }
        for s in stations
    ]
    warnings = validate_survey_points(stations).warnings
    payload = build_excel_report(
        project_name=well.get("project_name") or well.get("project_id"),
        well_name=well["name"],
        survey_rows=survey_rows,
        actual_points=actual,
        design_points=design,
        deviation_rows=deviation_rows,
        separation_rows=separation_rows,
        sources=trajectory_store.list_sources_for_well(well_id),
        warnings=warnings,
    )
    filename = f"trajectory_{well['name'].replace(' ', '_')}.xlsx"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(BytesIO(payload), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers=headers)
