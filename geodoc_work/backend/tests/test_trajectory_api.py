from fastapi.testclient import TestClient

from app.main import app
from app.trajectory.store import trajectory_store

client = TestClient(app)


def setup_function():
    trajectory_store.reset_for_tests()


def _import_demo_well(name="Well-A"):
    payload = {
        "project_name": "Navigator Demo",
        "well_name": name,
        "approved": True,
        "magnetic_declination": 0,
        "columns": ["MD", "Inc", "Azi"],
        "rows": [[0, 0, 0], [100, 0, 0], [200, 10, 90]],
    }
    res = client.post("/api/trajectory/import-survey", json=payload)
    assert res.status_code == 200, res.text
    data = res.json()
    recalc = client.post(f"/api/trajectory/recalculate/{data['well_id']}")
    assert recalc.status_code == 200, recalc.text
    return data


def test_import_recalculate_plan_tree_and_report():
    data = _import_demo_well()
    tree = client.get(f"/api/trajectory/project/{data['project_id']}/tree")
    assert tree.status_code == 200
    assert tree.json()["nodes"][0]["children"][0]["children"][0]["label"] == "Карта проекта"

    plan = client.get(f"/api/trajectory/well/{data['well_id']}/plan")
    assert plan.status_code == 200
    assert len(plan.json()["series"]) == 3

    report = client.get(f"/api/trajectory/well/{data['well_id']}/report.xlsx")
    assert report.status_code == 200
    assert report.headers["content-type"].startswith("application/vnd.openxmlformats-officedocument")
    assert len(report.content) > 2000


def test_recalculate_requires_manual_approval():
    res = client.post("/api/trajectory/import-survey", json={
        "project_name": "Needs Approval",
        "well_name": "Well-1",
        "approved": False,
        "columns": ["MD", "Inc", "Azi"],
        "rows": [[0, 0, 0], [100, 0, 0]],
    })
    assert res.status_code == 200
    well_id = res.json()["well_id"]
    recalc = client.post(f"/api/trajectory/recalculate/{well_id}")
    assert recalc.status_code == 409


def test_project_separation():
    first = _import_demo_well("Well-A")
    second_payload = {
        "project_id": first["project_id"],
        "project_name": "Navigator Demo",
        "well_name": "Well-B",
        "approved": True,
        "magnetic_declination": 0,
        "columns": ["MD", "Inc", "Azi"],
        "rows": [[0, 0, 0], [100, 0, 0], [200, 0, 0]],
    }
    second = client.post("/api/trajectory/import-survey", json=second_payload).json()
    client.post(f"/api/trajectory/recalculate/{second['well_id']}")
    sep = client.get(f"/api/trajectory/project/{first['project_id']}/separation")
    assert sep.status_code == 200
    assert len(sep.json()["rows"]) == 1


def test_seed_demo_builds_dynamic_tree():
    res = client.post("/api/trajectory/seed-demo")
    assert res.status_code == 200, res.text
    assert res.json()["survey_imported"] == 10
    tree = client.get("/api/trajectory/tree")
    assert tree.status_code == 200
    payload = tree.json()
    labels = str(payload)
    assert "Well-A" in labels
    assert "Well-B" in labels
    assert "Карта проекта" in labels
