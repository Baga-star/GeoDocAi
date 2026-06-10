from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

TrajectoryStatus = Literal["ok", "warning", "invalid", "needs_approval", "needs_domain_rules"]
TrajectoryLayer = Literal["actual", "design", "forecast"]


class SourceProvenance(BaseModel):
    document_id: str | None = None
    document_name: str | None = None
    page: int | None = None
    artifact_id: str | None = None
    table_title: str | None = None
    row_index: int | None = None
    bbox: list[float] | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class ValidationResult(BaseModel):
    status: TrajectoryStatus = "ok"
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class SurveyStationInput(BaseModel):
    md: float
    inclination: float = Field(alias="inc")
    azimuth: float = Field(alias="azi")
    magnetic_declination: float | None = None
    approved: bool = False
    provenance: SourceProvenance | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class DesignSegmentInput(BaseModel):
    start_md: float | None = None
    end_md: float | None = None
    length: float | None = None
    start_inclination: float | None = Field(default=None, alias="start_inc")
    end_inclination: float | None = Field(default=None, alias="end_inc")
    start_azimuth: float | None = Field(default=None, alias="start_azi")
    end_azimuth: float | None = Field(default=None, alias="end_azi")
    tolerance_m: float | None = None
    circle_radius_m: float | None = None
    magnetic_declination: float | None = None
    approved: bool = False
    provenance: SourceProvenance | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class CandidateTable(BaseModel):
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any] | dict[str, Any]] = Field(default_factory=list)
    provenance: SourceProvenance | None = None


class ImportSurveyRequest(BaseModel):
    project_id: str | None = None
    project_name: str = "Default trajectory project"
    well_id: str | None = None
    well_name: str = "Well-1"
    approved: bool = False
    magnetic_declination: float | None = None
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any] | dict[str, Any]] = Field(default_factory=list)
    tables: list[CandidateTable] = Field(default_factory=list)
    document_id: str | None = None
    artifact_id: str | None = None


class ImportProjectProfileRequest(BaseModel):
    project_id: str | None = None
    project_name: str = "Default trajectory project"
    well_id: str | None = None
    well_name: str = "Well-1"
    approved: bool = False
    magnetic_declination: float | None = None
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any] | dict[str, Any]] = Field(default_factory=list)
    tables: list[CandidateTable] = Field(default_factory=list)
    document_id: str | None = None
    artifact_id: str | None = None


class ImportSurveyResponse(BaseModel):
    project_id: str
    well_id: str
    imported: int
    validation: ValidationResult
    stations: list[SurveyStationInput] = Field(default_factory=list)


class ImportProjectProfileResponse(BaseModel):
    project_id: str
    well_id: str
    imported: int
    validation: ValidationResult
    segments: list[DesignSegmentInput] = Field(default_factory=list)




class AutoImportTrajectoryRequest(BaseModel):
    document_id: str | None = None
    project_id: str | None = None
    project_name: str = "Auto imported trajectory project"
    well_id: str | None = None
    well_name: str = "Well-1"
    approved: bool = False
    magnetic_declination: float | None = None


class AutoImportTrajectoryResponse(BaseModel):
    status: TrajectoryStatus = "ok"
    project_id: str | None = None
    well_id: str | None = None
    survey_imported: int = 0
    design_imported: int = 0
    validation: ValidationResult = Field(default_factory=ValidationResult)
    warnings: list[str] = Field(default_factory=list)


class TrajectoryPoint(BaseModel):
    md: float
    inc: float
    azi: float
    tvd: float
    northing: float
    easting: float
    vertical_section: float | None = None
    layer: TrajectoryLayer = "actual"
    provenance: SourceProvenance | None = None


class SeriesMeta(BaseModel):
    coordinate_system: str = "local tangent plane"
    depth_positive: Literal["down"] = "down"
    units: dict[str, str] = Field(default_factory=lambda: {"md": "m", "tvd": "m", "northing": "m", "easting": "m"})
    display: dict[str, Any] = Field(default_factory=dict)


class TrajectorySeriesResponse(BaseModel):
    status: TrajectoryStatus = "ok"
    project_id: str | None = None
    well_id: str | None = None
    series: list[TrajectoryPoint] = Field(default_factory=list)
    meta: SeriesMeta = Field(default_factory=SeriesMeta)
    provenance: list[SourceProvenance] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ProjectSeries(BaseModel):
    well_id: str
    well_name: str
    layer: TrajectoryLayer = "actual"
    points: list[TrajectoryPoint] = Field(default_factory=list)


class ProjectTrajectoryResponse(BaseModel):
    status: TrajectoryStatus = "ok"
    project_id: str
    series: list[ProjectSeries] = Field(default_factory=list)
    meta: SeriesMeta = Field(default_factory=SeriesMeta)
    warnings: list[str] = Field(default_factory=list)


class DeviationRow(BaseModel):
    md: float
    tvd: float
    northing: float
    easting: float
    nearest_design_md: float | None = None
    distance_m: float | None = None
    delta_tvd: float | None = None
    delta_northing: float | None = None
    delta_easting: float | None = None


class DeviationResponse(BaseModel):
    status: TrajectoryStatus = "ok"
    well_id: str
    rows: list[DeviationRow] = Field(default_factory=list)
    max_distance_m: float | None = None
    warnings: list[str] = Field(default_factory=list)


class SeparationRow(BaseModel):
    well_a_id: str
    well_a_name: str
    well_b_id: str
    well_b_name: str
    min_distance_m: float | None = None
    md_a: float | None = None
    md_b: float | None = None
    method: str = "pointwise_mvp"


class SeparationResponse(BaseModel):
    status: TrajectoryStatus = "ok"
    project_id: str
    rows: list[SeparationRow] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ForecastRequest(BaseModel):
    mode: Literal["contract", "basic_hold"] = "contract"
    target_md: float | None = None
    step_m: float = Field(default=30.0, gt=0, le=250)
    domain_rules: dict[str, Any] = Field(default_factory=dict)


class ForecastResponse(BaseModel):
    status: TrajectoryStatus = "needs_domain_rules"
    well_id: str
    series: list[TrajectoryPoint] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TreeNode(BaseModel):
    id: str
    label: str
    type: Literal["project", "group", "well", "view"]
    action: str | None = None
    children: list["TreeNode"] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class TrajectoryTreeResponse(BaseModel):
    status: TrajectoryStatus = "ok"
    project_id: str | None = None
    nodes: list[TreeNode] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RecalculateResponse(BaseModel):
    status: TrajectoryStatus = "ok"
    well_id: str
    actual_points: int = 0
    design_points: int = 0
    validation: ValidationResult = Field(default_factory=ValidationResult)


class SurveyDataResponse(BaseModel):
    status: TrajectoryStatus = "ok"
    well_id: str
    stations: list[SurveyStationInput] = Field(default_factory=list)
    segments: list[DesignSegmentInput] = Field(default_factory=list)
    validation: ValidationResult = Field(default_factory=ValidationResult)
