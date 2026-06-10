from __future__ import annotations

import re
from typing import Any, Iterable

from app.models import DocumentArtifact
from app.trajectory.models import (
    CandidateTable,
    DesignSegmentInput,
    SourceProvenance,
    SurveyStationInput,
    ValidationResult,
)

_SPACE_RE = re.compile(r"\s+")
_NUM_RE = re.compile(r"[-+]?\d+(?:[\s\u00a0]?\d{3})*(?:[,.]\d+)?")

SURVEY_ALIASES = {
    "md": {
        "md", "measureddepth", "measured depth", "depth", "глубинапоинструменту", "глубина по инструменту",
        "измереннаяглубина", "измеренная глубина", "глубинаmd", "глубина", "mdм", "md,m", "md m",
        "глубинапоствол", "глубина по стволу", "глубинаствол", "гпи", "depthm",
    },
    "inc": {
        "inc", "inclination", "incl", "zenith", "зенит", "зенитныйугол", "зенитный угол",
        "наклон", "инклинация", "уголнаклона", "угол наклона", "incм", "incdeg",
        "уголзенита", "угол зенита", "зенитугол",
    },
    "azi": {
        "azi", "azimuth", "azim", "азимут", "дирекционныйугол", "дирекционный угол", "aziград", "azi deg",
        "азимутугол", "направление", "azimuthдег",
    },
    "magnetic_declination": {
        "магнитноесклонение", "магнитное склонение", "declination", "magneticdeclination", "mag decl",
    },
    "well_name": {"скважина", "well", "wellname", "well name", "номерскважины", "номер скважины"},
}

DESIGN_ALIASES = {
    "start_md": {"startmd", "start md", "mdstart", "начальнаяглубина", "начальная глубина", "mdот", "от", "md from"},
    "end_md": {"endmd", "end md", "mdend", "конечнаяглубина", "конечная глубина", "mdдо", "до", "md to"},
    "length": {"длинаучастка", "длина участка", "length", "sectionlength", "section length", "длина", "l"},
    "start_inc": {"начальныйзенитныйугол", "начальный зенитный угол", "startinc", "start inc", "incstart", "zenithstart"},
    "end_inc": {"конечныйзенитныйугол", "конечный зенитный угол", "endinc", "end inc", "incend", "zenithend"},
    "start_azi": {"начальныйазимут", "начальный азимут", "startazi", "start azi", "azistart"},
    "end_azi": {"конечныйазимут", "конечный азимут", "endazi", "end azi", "aziend"},
    "tolerance_m": {"коридордопуска", "коридор допуска", "tolerance", "corridor", "допуск", "tolerancem"},
    "circle_radius_m": {"радиускругадопуска", "радиус круга допуска", "radius", "circle radius", "радиус"},
    "magnetic_declination": {"магнитноесклонение", "магнитное склонение", "declination", "magneticdeclination"},
    "well_name": {"скважина", "well", "wellname", "well name", "номерскважины", "номер скважины"},
}


def canonical_col(value: str) -> str:
    value = value.strip().lower().replace("ё", "е")
    value = value.replace("°", " deg ").replace("град.", "град")
    value = re.sub(r"[()\[\]{}.,;:/\\_-]+", " ", value)
    value = _SPACE_RE.sub(" ", value).strip()
    compact = value.replace(" ", "")
    return compact or value


def match_alias(column: str, aliases: dict[str, set[str]]) -> str | None:
    compact = canonical_col(column)
    spaced = _SPACE_RE.sub(" ", column.strip().lower().replace("ё", "е"))
    for target, values in aliases.items():
        normalized = {canonical_col(v) for v in values} | {_SPACE_RE.sub(" ", v.lower()).strip() for v in values}
        if compact in normalized or spaced in normalized:
            return target
    # Loose contains match for noisy OCR headers.
    # Require min 4 chars to avoid short tokens like "md"(2), "inc"(3), "azi"(3)
    # matching as substrings inside design-column names like "startmd", "endinc".
    for target, values in aliases.items():
        for alias in values:
            a = canonical_col(alias)
            if a and len(a) >= 4 and len(compact) >= 4 and (a in compact or compact in a):
                return target
    return None


def parse_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text or text in {"-", "—", "n/a", "нет"}:
        return None
    text = text.replace("\u2212", "-").replace("−", "-")
    match = _NUM_RE.search(text.replace(" ", ""))
    if not match:
        return None
    number = match.group(0).replace("\u00a0", "").replace(" ", "").replace(",", ".")
    try:
        return float(number)
    except ValueError:
        return None


def rows_to_dicts(columns: list[str], rows: Iterable[list[Any] | dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict):
            output.append(row)
        else:
            output.append({columns[i] if i < len(columns) else f"col_{i + 1}": cell for i, cell in enumerate(row)})
    return output


def artifact_to_candidate(artifact: DocumentArtifact) -> CandidateTable | None:
    if artifact.artifact_type != "table" and not artifact.rows:
        return None
    return CandidateTable(
        columns=artifact.columns or [],
        rows=artifact.rows or [],
        provenance=SourceProvenance(
            document_id=artifact.document_id,
            document_name=artifact.document_name,
            page=artifact.page,
            artifact_id=artifact.id,
            table_title=artifact.title or artifact.caption,
            bbox=artifact.bbox,
        ),
    )


def normalize_survey_tables(
    tables: list[CandidateTable],
    *,
    default_provenance: SourceProvenance | None = None,
    approved: bool = False,
    magnetic_declination: float | None = None,
) -> tuple[list[SurveyStationInput], ValidationResult, str | None]:
    stations: list[SurveyStationInput] = []
    warnings: list[str] = []
    errors: list[str] = []
    inferred_well_name: str | None = None

    for table in tables:
        mapping: dict[str, str] = {}
        for col in table.columns:
            key = match_alias(col, SURVEY_ALIASES)
            if key:
                mapping[col] = key
        if not {"md", "inc", "azi"}.issubset(set(mapping.values())):
            warnings.append("Таблица пропущена: не найдены обязательные колонки MD/зенит/азимут.")
            continue
        for row_index, raw_row in enumerate(rows_to_dicts(table.columns, table.rows), start=1):
            normalized: dict[str, Any] = {}
            raw_copy = {str(k): v for k, v in raw_row.items()}
            for original_key, value in raw_row.items():
                target = mapping.get(str(original_key)) or match_alias(str(original_key), SURVEY_ALIASES)
                if not target:
                    continue
                normalized[target] = value
            if "well_name" in normalized and normalized["well_name"]:
                inferred_well_name = str(normalized["well_name"]).strip()
            md = parse_float(normalized.get("md"))
            inc = parse_float(normalized.get("inc"))
            azi = parse_float(normalized.get("azi"))
            row_decl = parse_float(normalized.get("magnetic_declination"))
            if md is None or inc is None or azi is None:
                warnings.append(f"Строка {row_index} пропущена: не хватает чисел MD/зенит/азимут.")
                continue
            provenance = (table.provenance or default_provenance or SourceProvenance()).model_copy(
                update={"row_index": row_index, "raw": raw_copy}
            )
            stations.append(
                SurveyStationInput(
                    md=md,
                    inc=inc,
                    azi=azi,
                    magnetic_declination=row_decl if row_decl is not None else magnetic_declination,
                    approved=approved,
                    provenance=provenance,
                    raw=raw_copy,
                )
            )

    if not stations:
        errors.append("Не удалось извлечь ни одной станции инклинометрии.")
    status = "invalid" if errors else ("warning" if warnings else "ok")
    return stations, ValidationResult(status=status, warnings=warnings, errors=errors), inferred_well_name


def normalize_design_tables(
    tables: list[CandidateTable],
    *,
    default_provenance: SourceProvenance | None = None,
    approved: bool = False,
    magnetic_declination: float | None = None,
) -> tuple[list[DesignSegmentInput], ValidationResult, str | None]:
    segments: list[DesignSegmentInput] = []
    warnings: list[str] = []
    errors: list[str] = []
    inferred_well_name: str | None = None

    for table in tables:
        mapping: dict[str, str] = {}
        for col in table.columns:
            key = match_alias(col, DESIGN_ALIASES)
            if key:
                mapping[col] = key
        values = set(mapping.values())
        has_depth = "length" in values or "end_md" in values
        if not has_depth or not ({"start_inc", "end_inc", "start_azi", "end_azi"} & values):
            warnings.append("Таблица проекта пропущена: не найдены проектные сегменты/углы.")
            continue
        for row_index, raw_row in enumerate(rows_to_dicts(table.columns, table.rows), start=1):
            normalized: dict[str, Any] = {}
            raw_copy = {str(k): v for k, v in raw_row.items()}
            for original_key, value in raw_row.items():
                target = mapping.get(str(original_key)) or match_alias(str(original_key), DESIGN_ALIASES)
                if target:
                    normalized[target] = value
            if "well_name" in normalized and normalized["well_name"]:
                inferred_well_name = str(normalized["well_name"]).strip()
            start_md = parse_float(normalized.get("start_md"))
            end_md = parse_float(normalized.get("end_md"))
            length = parse_float(normalized.get("length"))
            if end_md is None and start_md is not None and length is not None:
                end_md = start_md + length
            if start_md is None and segments and length is not None:
                start_md = segments[-1].end_md
                end_md = start_md + length if start_md is not None else end_md
            if start_md is None and not segments:
                start_md = 0.0
            if end_md is None and length is not None and start_md is not None:
                end_md = start_md + length
            if end_md is None:
                warnings.append(f"Проектная строка {row_index} пропущена: нет конечной MD или длины участка.")
                continue
            start_inc = parse_float(normalized.get("start_inc"))
            end_inc = parse_float(normalized.get("end_inc"))
            start_azi = parse_float(normalized.get("start_azi"))
            end_azi = parse_float(normalized.get("end_azi"))
            if start_inc is None:
                start_inc = segments[-1].end_inclination if segments else 0.0
            if end_inc is None:
                end_inc = start_inc
            if start_azi is None:
                start_azi = segments[-1].end_azimuth if segments else 0.0
            if end_azi is None:
                end_azi = start_azi
            provenance = (table.provenance or default_provenance or SourceProvenance()).model_copy(
                update={"row_index": row_index, "raw": raw_copy}
            )
            segments.append(
                DesignSegmentInput(
                    start_md=start_md,
                    end_md=end_md,
                    length=length,
                    start_inc=start_inc,
                    end_inc=end_inc,
                    start_azi=start_azi,
                    end_azi=end_azi,
                    tolerance_m=parse_float(normalized.get("tolerance_m")),
                    circle_radius_m=parse_float(normalized.get("circle_radius_m")),
                    magnetic_declination=parse_float(normalized.get("magnetic_declination")) or magnetic_declination,
                    approved=approved,
                    provenance=provenance,
                    raw=raw_copy,
                )
            )

    if not segments:
        errors.append("Не удалось извлечь ни одного проектного сегмента.")
    status = "invalid" if errors else ("warning" if warnings else "ok")
    return segments, ValidationResult(status=status, warnings=warnings, errors=errors), inferred_well_name
