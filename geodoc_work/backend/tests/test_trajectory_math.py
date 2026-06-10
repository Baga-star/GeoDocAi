from app.trajectory.math import (
    build_project_profile,
    compute_deviation_from_project,
    compute_interwell_separation,
    minimum_curvature,
    validate_survey_points,
)
from app.trajectory.models import DesignSegmentInput, SurveyStationInput


def test_minimum_curvature_vertical_golden_case():
    stations = [
        SurveyStationInput(md=0, inc=0, azi=0, approved=True, magnetic_declination=0),
        SurveyStationInput(md=1000, inc=0, azi=0, approved=True, magnetic_declination=0),
    ]
    points = minimum_curvature(stations)
    assert len(points) == 2
    assert points[-1].tvd == 1000
    assert points[-1].northing == 0
    assert points[-1].easting == 0


def test_validate_survey_rejects_non_monotonic_md_and_bad_angles():
    stations = [
        SurveyStationInput(md=100, inc=0, azi=0, approved=True),
        SurveyStationInput(md=90, inc=181, azi=361, approved=True),
    ]
    result = validate_survey_points(stations)
    assert result.status == "invalid"
    assert any("монотонно" in error for error in result.errors)
    assert any("Зенит" in error for error in result.errors)
    assert any("Азимут" in error for error in result.errors)


def test_build_project_profile_and_deviation():
    design = [
        DesignSegmentInput(start_md=0, end_md=100, start_inc=0, end_inc=0, start_azi=0, end_azi=0, approved=True),
    ]
    design_points = build_project_profile(design)
    actual = minimum_curvature([
        SurveyStationInput(md=0, inc=0, azi=0, approved=True, magnetic_declination=0),
        SurveyStationInput(md=100, inc=0, azi=0, approved=True, magnetic_declination=0),
    ])
    rows = compute_deviation_from_project(actual, design_points)
    assert rows[-1].distance_m == 0


def test_interwell_separation_pointwise_mvp():
    well_a = minimum_curvature([
        SurveyStationInput(md=0, inc=0, azi=0, approved=True, magnetic_declination=0),
        SurveyStationInput(md=100, inc=0, azi=0, approved=True, magnetic_declination=0),
    ])
    well_b = [p.model_copy(update={"easting": p.easting + 25}) for p in well_a]
    rows = compute_interwell_separation([("a", "A", well_a), ("b", "B", well_b)])
    assert len(rows) == 1
    assert rows[0].min_distance_m == 25
