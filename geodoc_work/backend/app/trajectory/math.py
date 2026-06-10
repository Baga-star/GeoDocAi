from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

from app.trajectory.models import (
    DesignSegmentInput,
    DeviationRow,
    ForecastRequest,
    ForecastResponse,
    SeparationRow,
    SurveyStationInput,
    TrajectoryPoint,
    ValidationResult,
)

_EPS = 1e-12


@dataclass(frozen=True)
class SurveyLike:
    md: float
    inc: float
    azi: float


def _inc(station: SurveyStationInput | SurveyLike | TrajectoryPoint) -> float:
    return float(getattr(station, "inc", getattr(station, "inclination", 0.0)))


def _azi(station: SurveyStationInput | SurveyLike | TrajectoryPoint) -> float:
    return float(getattr(station, "azi", getattr(station, "azimuth", 0.0)))


def validate_survey_points(stations: Iterable[SurveyStationInput]) -> ValidationResult:
    ordered = list(stations)
    warnings: list[str] = []
    errors: list[str] = []
    if len(ordered) < 2:
        errors.append("Для расчета траектории нужно минимум две станции инклинометрии.")
    last_md: float | None = None
    has_declination = False
    for index, station in enumerate(ordered, start=1):
        if last_md is not None and station.md <= last_md:
            errors.append(f"MD должна возрастать монотонно: строка {index} имеет MD={station.md}, предыдущая MD={last_md}.")
        last_md = station.md
        if not 0 <= station.inclination <= 180:
            errors.append(f"Зенитный угол вне диапазона [0, 180] в строке {index}: {station.inclination}.")
        if not 0 <= station.azimuth <= 360:
            errors.append(f"Азимут вне диапазона [0, 360] в строке {index}: {station.azimuth}.")
        if station.magnetic_declination is not None:
            has_declination = True
        if not station.approved:
            warnings.append(f"Станция MD={station.md} не подтверждена вручную.")
    if not has_declination:
        warnings.append("Магнитное склонение не найдено/не задано: расчет использует исходные азимуты без поправки.")
    status = "invalid" if errors else ("needs_approval" if any(not s.approved for s in ordered) else ("warning" if warnings else "ok"))
    return ValidationResult(status=status, warnings=warnings, errors=errors)


def _dogleg(inc1: float, azi1: float, inc2: float, azi2: float) -> float:
    i1 = math.radians(inc1)
    i2 = math.radians(inc2)
    a1 = math.radians(azi1)
    a2 = math.radians(azi2)
    cos_dl = math.cos(i1) * math.cos(i2) + math.sin(i1) * math.sin(i2) * math.cos(a2 - a1)
    return math.acos(max(-1.0, min(1.0, cos_dl)))


def _ratio_factor(dogleg: float) -> float:
    if abs(dogleg) < _EPS:
        return 1.0
    return 2.0 / dogleg * math.tan(dogleg / 2.0)


def minimum_curvature(stations: Iterable[SurveyStationInput | SurveyLike]) -> list[TrajectoryPoint]:
    """Compute wellbore coordinates with TVD positive downward.

    northing/easting use local tangent plane coordinates in meters:
    northing positive to north, easting positive to east.
    """
    ordered = sorted(list(stations), key=lambda s: float(s.md))
    if not ordered:
        return []
    first = ordered[0]
    output = [
        TrajectoryPoint(
            md=float(first.md),
            inc=_inc(first),
            azi=_azi(first),
            tvd=0.0,
            northing=0.0,
            easting=0.0,
            layer="actual",
            provenance=getattr(first, "provenance", None),
        )
    ]
    tvd = north = east = 0.0
    for prev, curr in zip(ordered, ordered[1:]):
        dmd = float(curr.md) - float(prev.md)
        if dmd < 0:
            raise ValueError("MD must be sorted increasingly")
        inc1 = math.radians(_inc(prev))
        inc2 = math.radians(_inc(curr))
        azi1 = math.radians(_azi(prev))
        azi2 = math.radians(_azi(curr))
        dl = _dogleg(_inc(prev), _azi(prev), _inc(curr), _azi(curr))
        rf = _ratio_factor(dl)
        tvd += dmd / 2.0 * (math.cos(inc1) + math.cos(inc2)) * rf
        north += dmd / 2.0 * (math.sin(inc1) * math.cos(azi1) + math.sin(inc2) * math.cos(azi2)) * rf
        east += dmd / 2.0 * (math.sin(inc1) * math.sin(azi1) + math.sin(inc2) * math.sin(azi2)) * rf
        output.append(
            TrajectoryPoint(
                md=float(curr.md),
                inc=_inc(curr),
                azi=_azi(curr),
                tvd=round(tvd, 6),
                northing=round(north, 6),
                easting=round(east, 6),
                layer="actual",
                provenance=getattr(curr, "provenance", None),
            )
        )
    return output


def compute_vertical_section(points: Iterable[TrajectoryPoint], profile_azimuth: float = 0.0) -> list[TrajectoryPoint]:
    angle = math.radians(profile_azimuth)
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    return [
        point.model_copy(update={"vertical_section": round(point.northing * cos_a + point.easting * sin_a, 6)})
        for point in points
    ]


def build_plan_view_series(points: Iterable[TrajectoryPoint]) -> list[dict[str, float]]:
    return [{"x": point.easting, "y": point.northing, "md": point.md, "tvd": point.tvd} for point in points]


def build_profile_view_series(points: Iterable[TrajectoryPoint], azimuth: float = 0.0) -> list[dict[str, float]]:
    with_vs = compute_vertical_section(points, azimuth)
    return [{"x": point.vertical_section or 0.0, "y": point.tvd, "md": point.md} for point in with_vs]


def build_3d_series(points: Iterable[TrajectoryPoint]) -> list[dict[str, float]]:
    return [{"x": point.easting, "y": point.northing, "z": point.tvd, "md": point.md} for point in points]


def build_project_profile(segments: Iterable[DesignSegmentInput]) -> list[TrajectoryPoint]:
    survey: list[SurveyLike] = []
    sorted_segments = sorted(list(segments), key=lambda s: (s.start_md or 0.0, s.end_md or 0.0))
    for index, segment in enumerate(sorted_segments):
        start_md = float(segment.start_md or 0.0)
        end_md = float(segment.end_md if segment.end_md is not None else start_md + float(segment.length or 0.0))
        start_inc = float(segment.start_inclination if segment.start_inclination is not None else 0.0)
        end_inc = float(segment.end_inclination if segment.end_inclination is not None else start_inc)
        start_azi = float(segment.start_azimuth if segment.start_azimuth is not None else 0.0)
        end_azi = float(segment.end_azimuth if segment.end_azimuth is not None else start_azi)
        if index == 0 or not survey or abs(survey[-1].md - start_md) > 1e-6:
            survey.append(SurveyLike(md=start_md, inc=start_inc, azi=start_azi))
        survey.append(SurveyLike(md=end_md, inc=end_inc, azi=end_azi))
    points = minimum_curvature(survey)
    return [p.model_copy(update={"layer": "design"}) for p in points]


def _distance3(a: TrajectoryPoint, b: TrajectoryPoint) -> float:
    return math.sqrt((a.tvd - b.tvd) ** 2 + (a.northing - b.northing) ** 2 + (a.easting - b.easting) ** 2)


def compute_deviation_from_project(actual: Iterable[TrajectoryPoint], design: Iterable[TrajectoryPoint]) -> list[DeviationRow]:
    design_points = list(design)
    rows: list[DeviationRow] = []
    if not design_points:
        return rows
    for point in actual:
        nearest = min(design_points, key=lambda d: _distance3(point, d))
        rows.append(
            DeviationRow(
                md=point.md,
                tvd=point.tvd,
                northing=point.northing,
                easting=point.easting,
                nearest_design_md=nearest.md,
                distance_m=round(_distance3(point, nearest), 6),
                delta_tvd=round(point.tvd - nearest.tvd, 6),
                delta_northing=round(point.northing - nearest.northing, 6),
                delta_easting=round(point.easting - nearest.easting, 6),
            )
        )
    return rows


def compute_interwell_separation(wells: Iterable[tuple[str, str, list[TrajectoryPoint]]]) -> list[SeparationRow]:
    items = [(wid, name, pts) for wid, name, pts in wells if pts]
    rows: list[SeparationRow] = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            well_a_id, well_a_name, points_a = items[i]
            well_b_id, well_b_name, points_b = items[j]
            best: tuple[float, TrajectoryPoint, TrajectoryPoint] | None = None
            for a in points_a:
                for b in points_b:
                    dist = _distance3(a, b)
                    if best is None or dist < best[0]:
                        best = (dist, a, b)
            rows.append(
                SeparationRow(
                    well_a_id=well_a_id,
                    well_a_name=well_a_name,
                    well_b_id=well_b_id,
                    well_b_name=well_b_name,
                    min_distance_m=round(best[0], 6) if best else None,
                    md_a=best[1].md if best else None,
                    md_b=best[2].md if best else None,
                )
            )
    return rows


def compute_forecast_placeholder_or_basic_mode(
    well_id: str,
    actual_points: list[TrajectoryPoint],
    request: ForecastRequest,
) -> ForecastResponse:
    if request.mode != "basic_hold":
        return ForecastResponse(
            status="needs_domain_rules",
            well_id=well_id,
            warnings=[
                "Для инженерного прогноза нужны доменные правила: BHA, DLS limits, steering model, target window, uncertainty model. Phase 1 возвращает service contract без выдуманной математики."
            ],
        )
    if len(actual_points) < 2 or request.target_md is None:
        return ForecastResponse(
            status="needs_domain_rules",
            well_id=well_id,
            warnings=["Для basic_hold нужен target_md и минимум две рассчитанные точки фактической траектории."],
        )
    last = actual_points[-1]
    if request.target_md <= last.md:
        return ForecastResponse(status="warning", well_id=well_id, series=[], warnings=["target_md должен быть больше последней MD."])
    synthetic: list[SurveyLike] = [SurveyLike(md=last.md, inc=last.inc, azi=last.azi)]
    md = last.md
    while md < request.target_md:
        md = min(request.target_md, md + request.step_m)
        synthetic.append(SurveyLike(md=md, inc=last.inc, azi=last.azi))
    rel = minimum_curvature(synthetic)
    forecast: list[TrajectoryPoint] = []
    for point in rel[1:]:
        forecast.append(
            point.model_copy(
                update={
                    "tvd": round(last.tvd + point.tvd, 6),
                    "northing": round(last.northing + point.northing, 6),
                    "easting": round(last.easting + point.easting, 6),
                    "layer": "forecast",
                }
            )
        )
    return ForecastResponse(status="warning", well_id=well_id, series=forecast, warnings=["Basic hold — только геометрическое продление последнего inc/azi, не доменная steering-модель."])
