from app.trajectory.extract import normalize_design_tables, normalize_survey_tables
from app.trajectory.models import CandidateTable, SourceProvenance


def test_normalize_survey_russian_columns_with_provenance():
    table = CandidateTable(
        columns=["Глубина по инструменту", "Зенит", "Азимут"],
        rows=[["0", "0", "0"], ["100,5", "10", "90"]],
        provenance=SourceProvenance(document_name="survey.pdf", page=12, table_title="Инклинометрия"),
    )
    stations, validation, _ = normalize_survey_tables([table], approved=True, magnetic_declination=7.1)
    assert validation.status == "ok"
    assert len(stations) == 2
    assert stations[1].md == 100.5
    assert stations[1].magnetic_declination == 7.1
    assert stations[1].provenance.page == 12
    assert stations[1].provenance.row_index == 2


def test_normalize_design_russian_columns():
    table = CandidateTable(
        columns=["Длина участка", "Начальный зенитный угол", "Конечный зенитный угол", "Начальный азимут", "Конечный азимут", "Коридор допуска"],
        rows=[["100", "0", "10", "0", "90", "5"]],
    )
    segments, validation, _ = normalize_design_tables([table], approved=True)
    assert validation.status == "ok"
    assert len(segments) == 1
    assert segments[0].start_md == 0
    assert segments[0].end_md == 100
    assert segments[0].tolerance_m == 5
