from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from app.trajectory.models import DesignSegmentInput, SourceProvenance, SurveyStationInput, TrajectoryPoint

DB_PATH = Path(__file__).resolve().parents[3] / ".data" / "trajectory.sqlite3"


class TrajectoryStore:
    def __init__(self, path: Path = DB_PATH) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS wells (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    surface_northing REAL DEFAULT 0,
                    surface_easting REAL DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(project_id, name)
                );
                CREATE TABLE IF NOT EXISTS source_document_links (
                    id TEXT PRIMARY KEY,
                    document_id TEXT,
                    document_name TEXT,
                    page INTEGER,
                    artifact_id TEXT,
                    table_title TEXT,
                    row_index INTEGER,
                    bbox_json TEXT,
                    raw_json TEXT
                );
                CREATE TABLE IF NOT EXISTS survey_stations (
                    id TEXT PRIMARY KEY,
                    well_id TEXT NOT NULL REFERENCES wells(id) ON DELETE CASCADE,
                    md REAL NOT NULL,
                    inc REAL NOT NULL,
                    azi REAL NOT NULL,
                    magnetic_declination REAL,
                    approved INTEGER DEFAULT 0,
                    source_link_id TEXT REFERENCES source_document_links(id),
                    raw_json TEXT
                );
                CREATE TABLE IF NOT EXISTS design_segments (
                    id TEXT PRIMARY KEY,
                    well_id TEXT NOT NULL REFERENCES wells(id) ON DELETE CASCADE,
                    start_md REAL,
                    end_md REAL,
                    length REAL,
                    start_inc REAL,
                    end_inc REAL,
                    start_azi REAL,
                    end_azi REAL,
                    tolerance_m REAL,
                    circle_radius_m REAL,
                    magnetic_declination REAL,
                    approved INTEGER DEFAULT 0,
                    source_link_id TEXT REFERENCES source_document_links(id),
                    raw_json TEXT
                );
                CREATE TABLE IF NOT EXISTS computed_trajectory_points (
                    id TEXT PRIMARY KEY,
                    well_id TEXT NOT NULL REFERENCES wells(id) ON DELETE CASCADE,
                    layer TEXT NOT NULL,
                    md REAL NOT NULL,
                    inc REAL NOT NULL,
                    azi REAL NOT NULL,
                    tvd REAL NOT NULL,
                    northing REAL NOT NULL,
                    easting REAL NOT NULL,
                    vertical_section REAL,
                    source_link_id TEXT REFERENCES source_document_links(id),
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS deviation_results (
                    id TEXT PRIMARY KEY,
                    well_id TEXT NOT NULL REFERENCES wells(id) ON DELETE CASCADE,
                    payload_json TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS separation_results (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    payload_json TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS export_jobs (
                    id TEXT PRIMARY KEY,
                    well_id TEXT NOT NULL REFERENCES wells(id) ON DELETE CASCADE,
                    status TEXT NOT NULL,
                    payload_json TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    def reset_for_tests(self) -> None:
        with self.connect() as conn:
            for table in [
                "export_jobs",
                "separation_results",
                "deviation_results",
                "computed_trajectory_points",
                "design_segments",
                "survey_stations",
                "source_document_links",
                "wells",
                "projects",
            ]:
                conn.execute(f"DELETE FROM {table}")

    def get_or_create_project(self, name: str, project_id: str | None = None) -> str:
        with self.connect() as conn:
            if project_id:
                row = conn.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone()
                if row:
                    return str(row["id"])
                conn.execute("INSERT INTO projects(id, name) VALUES (?, ?)", (project_id, name))
                return project_id
            row = conn.execute("SELECT id FROM projects WHERE name = ?", (name,)).fetchone()
            if row:
                return str(row["id"])
            pid = str(uuid.uuid4())
            conn.execute("INSERT INTO projects(id, name) VALUES (?, ?)", (pid, name))
            return pid

    def get_or_create_well(self, project_id: str, name: str, well_id: str | None = None) -> str:
        with self.connect() as conn:
            if well_id:
                row = conn.execute("SELECT id FROM wells WHERE id = ?", (well_id,)).fetchone()
                if row:
                    return str(row["id"])
                conn.execute("INSERT INTO wells(id, project_id, name) VALUES (?, ?, ?)", (well_id, project_id, name))
                return well_id
            row = conn.execute("SELECT id FROM wells WHERE project_id = ? AND name = ?", (project_id, name)).fetchone()
            if row:
                return str(row["id"])
            wid = str(uuid.uuid4())
            conn.execute("INSERT INTO wells(id, project_id, name) VALUES (?, ?, ?)", (wid, project_id, name))
            return wid

    def list_projects(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM projects ORDER BY created_at, name").fetchall()
            return [dict(row) for row in rows]

    def list_wells(self, project_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM wells WHERE project_id = ? ORDER BY name", (project_id,)).fetchall()
            return [dict(row) for row in rows]

    def get_well(self, well_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT w.*, p.name AS project_name FROM wells w JOIN projects p ON p.id = w.project_id WHERE w.id = ?", (well_id,)).fetchone()
            return dict(row) if row else None

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            if project_id == "default":
                row = conn.execute("SELECT * FROM projects ORDER BY created_at LIMIT 1").fetchone()
            else:
                row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
            return dict(row) if row else None

    def save_source(self, provenance: SourceProvenance | None) -> str | None:
        if provenance is None:
            return None
        source_id = str(uuid.uuid4())
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO source_document_links(id, document_id, document_name, page, artifact_id, table_title, row_index, bbox_json, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_id,
                    provenance.document_id,
                    provenance.document_name,
                    provenance.page,
                    provenance.artifact_id,
                    provenance.table_title,
                    provenance.row_index,
                    json.dumps(provenance.bbox, ensure_ascii=False) if provenance.bbox else None,
                    json.dumps(provenance.raw, ensure_ascii=False),
                ),
            )
        return source_id

    def _source_from_id(self, source_id: str | None) -> SourceProvenance | None:
        if not source_id:
            return None
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM source_document_links WHERE id = ?", (source_id,)).fetchone()
        if not row:
            return None
        raw = dict(row)
        return SourceProvenance(
            document_id=raw.get("document_id"),
            document_name=raw.get("document_name"),
            page=raw.get("page"),
            artifact_id=raw.get("artifact_id"),
            table_title=raw.get("table_title"),
            row_index=raw.get("row_index"),
            bbox=json.loads(raw["bbox_json"]) if raw.get("bbox_json") else None,
            raw=json.loads(raw["raw_json"]) if raw.get("raw_json") else {},
        )

    def replace_survey(self, well_id: str, stations: list[SurveyStationInput]) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM survey_stations WHERE well_id = ?", (well_id,))
        for station in stations:
            self.add_survey_station(well_id, station)

    def add_survey_station(self, well_id: str, station: SurveyStationInput) -> str:
        sid = str(uuid.uuid4())
        source_id = self.save_source(station.provenance)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO survey_stations(id, well_id, md, inc, azi, magnetic_declination, approved, source_link_id, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sid,
                    well_id,
                    station.md,
                    station.inclination,
                    station.azimuth,
                    station.magnetic_declination,
                    1 if station.approved else 0,
                    source_id,
                    json.dumps(station.raw, ensure_ascii=False),
                ),
            )
        return sid

    def list_survey(self, well_id: str) -> list[SurveyStationInput]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM survey_stations WHERE well_id = ? ORDER BY md", (well_id,)).fetchall()
        stations: list[SurveyStationInput] = []
        for row in rows:
            data = dict(row)
            stations.append(
                SurveyStationInput(
                    md=data["md"],
                    inc=data["inc"],
                    azi=data["azi"],
                    magnetic_declination=data.get("magnetic_declination"),
                    approved=bool(data.get("approved")),
                    provenance=self._source_from_id(data.get("source_link_id")),
                    raw=json.loads(data["raw_json"]) if data.get("raw_json") else {},
                )
            )
        return stations

    def replace_design(self, well_id: str, segments: list[DesignSegmentInput]) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM design_segments WHERE well_id = ?", (well_id,))
        for segment in segments:
            self.add_design_segment(well_id, segment)

    def add_design_segment(self, well_id: str, segment: DesignSegmentInput) -> str:
        sid = str(uuid.uuid4())
        source_id = self.save_source(segment.provenance)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO design_segments(id, well_id, start_md, end_md, length, start_inc, end_inc, start_azi, end_azi, tolerance_m, circle_radius_m, magnetic_declination, approved, source_link_id, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sid,
                    well_id,
                    segment.start_md,
                    segment.end_md,
                    segment.length,
                    segment.start_inclination,
                    segment.end_inclination,
                    segment.start_azimuth,
                    segment.end_azimuth,
                    segment.tolerance_m,
                    segment.circle_radius_m,
                    segment.magnetic_declination,
                    1 if segment.approved else 0,
                    source_id,
                    json.dumps(segment.raw, ensure_ascii=False),
                ),
            )
        return sid

    def list_design(self, well_id: str) -> list[DesignSegmentInput]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM design_segments WHERE well_id = ? ORDER BY start_md, end_md", (well_id,)).fetchall()
        segments: list[DesignSegmentInput] = []
        for row in rows:
            data = dict(row)
            segments.append(
                DesignSegmentInput(
                    start_md=data.get("start_md"),
                    end_md=data.get("end_md"),
                    length=data.get("length"),
                    start_inc=data.get("start_inc"),
                    end_inc=data.get("end_inc"),
                    start_azi=data.get("start_azi"),
                    end_azi=data.get("end_azi"),
                    tolerance_m=data.get("tolerance_m"),
                    circle_radius_m=data.get("circle_radius_m"),
                    magnetic_declination=data.get("magnetic_declination"),
                    approved=bool(data.get("approved")),
                    provenance=self._source_from_id(data.get("source_link_id")),
                    raw=json.loads(data["raw_json"]) if data.get("raw_json") else {},
                )
            )
        return segments

    def replace_computed(self, well_id: str, layer: str, points: list[TrajectoryPoint]) -> None:
        # Save provenance before opening the write transaction to avoid nested sqlite writers.
        source_ids = [self.save_source(point.provenance) for point in points]
        with self.connect() as conn:
            conn.execute("DELETE FROM computed_trajectory_points WHERE well_id = ? AND layer = ?", (well_id, layer))
            for point, source_id in zip(points, source_ids):
                conn.execute(
                    """
                    INSERT INTO computed_trajectory_points(id, well_id, layer, md, inc, azi, tvd, northing, easting, vertical_section, source_link_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        well_id,
                        layer,
                        point.md,
                        point.inc,
                        point.azi,
                        point.tvd,
                        point.northing,
                        point.easting,
                        point.vertical_section,
                        source_id,
                    ),
                )

    def list_computed(self, well_id: str, layer: str = "actual") -> list[TrajectoryPoint]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM computed_trajectory_points WHERE well_id = ? AND layer = ? ORDER BY md",
                (well_id, layer),
            ).fetchall()
        return [
            TrajectoryPoint(
                md=row["md"],
                inc=row["inc"],
                azi=row["azi"],
                tvd=row["tvd"],
                northing=row["northing"],
                easting=row["easting"],
                vertical_section=row["vertical_section"],
                layer=row["layer"],
                provenance=self._source_from_id(row["source_link_id"]),
            )
            for row in rows
        ]

    def list_sources_for_well(self, well_id: str) -> list[SourceProvenance]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT s.* FROM source_document_links s
                JOIN survey_stations ss ON ss.source_link_id = s.id
                WHERE ss.well_id = ?
                UNION
                SELECT DISTINCT s.* FROM source_document_links s
                JOIN design_segments ds ON ds.source_link_id = s.id
                WHERE ds.well_id = ?
                """,
                (well_id, well_id),
            ).fetchall()
        output: list[SourceProvenance] = []
        for row in rows:
            data = dict(row)
            output.append(
                SourceProvenance(
                    document_id=data.get("document_id"),
                    document_name=data.get("document_name"),
                    page=data.get("page"),
                    artifact_id=data.get("artifact_id"),
                    table_title=data.get("table_title"),
                    row_index=data.get("row_index"),
                    bbox=json.loads(data["bbox_json"]) if data.get("bbox_json") else None,
                    raw=json.loads(data["raw_json"]) if data.get("raw_json") else {},
                )
            )
        return output


trajectory_store = TrajectoryStore()
