"""Phase 14: lab results matrix over time and unmatched original-name trends."""
import os

os.environ["DATABASE_URL"] = "sqlite:////tmp/test_phase14.db"
os.environ["STORAGE_ROOT"] = "/tmp/phr_docs_test14"
os.environ.setdefault("AUTH_DISABLED", "1")

import shutil

shutil.rmtree("/tmp/phr_docs_test14", ignore_errors=True)
os.makedirs("/tmp/phr_docs_test14", exist_ok=True)

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import get_db
from app.models import Base

test_engine = create_engine(
    "sqlite:////tmp/test_phase14.db",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_db():
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    from app.seed import load_analytes

    load_analytes(db)
    db.close()
    yield


def _profile(name="Test Person"):
    return client.post("/profiles", json={"legal_name": name}).json()


def _encounter(pid, when, reason="Lab"):
    return client.post(
        "/encounters",
        json={"profile_id": pid, "type": "lab", "start": when, "reason": reason},
    ).json()


def _lab(pid, enc_id, panel, when, components, reported_time=None):
    body = {
        "profile_id": pid,
        "encounter_id": enc_id,
        "panel_name": panel,
        "collection_time": when,
        "components": components,
    }
    if reported_time:
        body["reported_time"] = reported_time
    r = client.post("/lab-reports", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_two_dates_sodium_and_leukocytes():
    p = _profile()
    pid = p["id"]
    earlier = datetime(2026, 5, 1, 8, 0).isoformat()
    later = datetime(2026, 9, 21, 9, 0).isoformat()
    enc1 = _encounter(pid, earlier, "BMP")
    enc2 = _encounter(pid, later, "CMP+CBC")
    _lab(
        pid,
        enc1["id"],
        "BMP",
        earlier,
        [{"original_name": "Sodium", "value_text": "138", "unit_original": "mmol/L"}],
    )
    _lab(
        pid,
        enc2["id"],
        "CMP",
        later,
        [
            {"original_name": "Sodium", "value_text": "140", "unit_original": "mmol/L"},
            {"original_name": "Leukocytes", "value_text": "6.2", "unit_original": "10*3/uL"},
        ],
    )
    matrix = client.get(f"/profiles/{pid}/lab-matrix").json()
    assert matrix["dates"] == ["2026-09-21", "2026-05-01"]
    keys = [row["key"] for row in matrix["rows"]]
    sodium = next(row for row in matrix["rows"] if row["display_name"] == "Sodium")
    leukocytes = next(row for row in matrix["rows"] if row["display_name"] == "Leukocytes")
    assert sodium["kind"] == "canonical"
    assert set(sodium["cells"]) == {"2026-09-21", "2026-05-01"}
    assert sodium["cells"]["2026-09-21"]["value_text"] == "140"
    assert sodium["cells"]["2026-05-01"]["value_text"] == "138"
    assert set(leukocytes["cells"]) == {"2026-09-21"}
    assert leukocytes["cells"]["2026-09-21"]["value_text"] == "6.2"
    assert keys.index(sodium["key"]) < keys.index(leukocytes["key"])


def test_same_day_cmp_and_cbc_one_column():
    p = _profile()
    pid = p["id"]
    day = datetime(2026, 9, 21, 8, 0).isoformat()
    enc_cmp = _encounter(pid, day, "CMP")
    enc_cbc = _encounter(pid, datetime(2026, 9, 21, 8, 30).isoformat(), "CBC")
    _lab(
        pid,
        enc_cmp["id"],
        "CMP",
        day,
        [{"original_name": "Sodium", "value_text": "140", "unit_original": "mmol/L"}],
    )
    _lab(
        pid,
        enc_cbc["id"],
        "CBC",
        datetime(2026, 9, 21, 8, 30).isoformat(),
        [{"original_name": "Leukocytes", "value_text": "6.2", "unit_original": "10*3/uL"}],
    )
    matrix = client.get(f"/profiles/{pid}/lab-matrix").json()
    assert matrix["dates"] == ["2026-09-21"]
    sodium = next(row for row in matrix["rows"] if row["display_name"] == "Sodium")
    leukocytes = next(row for row in matrix["rows"] if row["display_name"] == "Leukocytes")
    assert "2026-09-21" in sodium["cells"]
    assert "2026-09-21" in leukocytes["cells"]


def test_unmatched_foobar_row():
    p = _profile()
    pid = p["id"]
    when = datetime(2026, 5, 1, 8, 0).isoformat()
    enc = _encounter(pid, when)
    _lab(
        pid,
        enc["id"],
        "Misc",
        when,
        [{"original_name": "FooBar", "value_text": "12", "unit_original": "ng/mL"}],
    )
    matrix = client.get(f"/profiles/{pid}/lab-matrix").json()
    unmatched = [row for row in matrix["rows"] if row["kind"] == "unmatched"]
    assert len(unmatched) == 1
    row = unmatched[0]
    assert row["canonical_analyte_id"] is None
    assert row["key"].startswith("original:")
    assert row["display_name"].lower() == "foobar"
    assert row["cells"]["2026-05-01"]["value_text"] == "12"
    trend = client.get(f"/profiles/{pid}/trends/original/FooBar").json()
    assert len(trend["points"]) == 1
    assert trend["points"][0]["original_value"] == "12"
    sodium = client.get(f"/profiles/{pid}/trends/Sodium").json()
    assert sodium["points"] == []


def test_mixed_unit_glucose_cells_keep_original_units():
    p = _profile()
    pid = p["id"]
    d1 = datetime(2026, 1, 10, 8, 0).isoformat()
    d2 = datetime(2026, 6, 10, 8, 0).isoformat()
    enc1 = _encounter(pid, d1)
    enc2 = _encounter(pid, d2)
    _lab(
        pid,
        enc1["id"],
        "CMP",
        d1,
        [{"original_name": "Glucose", "value_text": "100", "unit_original": "mg/dL"}],
    )
    _lab(
        pid,
        enc2["id"],
        "CMP",
        d2,
        [{"original_name": "Glucose", "value_text": "5.5", "unit_original": "mmol/L"}],
    )
    matrix = client.get(f"/profiles/{pid}/lab-matrix").json()
    glucose = next(row for row in matrix["rows"] if row["display_name"] == "Glucose")
    assert glucose["cells"]["2026-01-10"]["value_text"] == "100"
    assert glucose["cells"]["2026-01-10"]["unit_original"] == "mg/dL"
    assert glucose["cells"]["2026-06-10"]["value_text"] == "5.5"
    assert glucose["cells"]["2026-06-10"]["unit_original"] == "mmol/L"
    trend = client.get(f"/profiles/{pid}/trends/Glucose").json()
    units = {pt["original_unit"] for pt in trend["points"]}
    assert units == {"mg/dL", "mmol/L"}


def test_profile_isolation_matrix():
    p1 = _profile("A")
    p2 = _profile("B")
    when = datetime(2026, 5, 1, 8, 0).isoformat()
    enc1 = _encounter(p1["id"], when)
    _lab(
        p1["id"],
        enc1["id"],
        "BMP",
        when,
        [{"original_name": "Sodium", "value_text": "140", "unit_original": "mmol/L"}],
    )
    matrix2 = client.get(f"/profiles/{p2['id']}/lab-matrix").json()
    assert matrix2["dates"] == []
    assert matrix2["rows"] == []
    matrix1 = client.get(f"/profiles/{p1['id']}/lab-matrix").json()
    assert matrix1["dates"] == ["2026-05-01"]
    assert any(row["display_name"] == "Sodium" for row in matrix1["rows"])


def test_same_analyte_same_day_latest_wins_also_lists_other():
    p = _profile()
    pid = p["id"]
    morning = datetime(2026, 9, 21, 7, 0).isoformat()
    afternoon = datetime(2026, 9, 21, 15, 0).isoformat()
    enc1 = _encounter(pid, morning, "BMP")
    enc2 = _encounter(pid, afternoon, "CMP")
    first = _lab(
        pid,
        enc1["id"],
        "BMP",
        morning,
        [{"original_name": "Sodium", "value_text": "133", "unit_original": "mmol/L"}],
        reported_time=morning,
    )
    second = _lab(
        pid,
        enc2["id"],
        "CMP",
        afternoon,
        [{"original_name": "Sodium", "value_text": "140", "unit_original": "mmol/L"}],
        reported_time=afternoon,
    )
    matrix = client.get(f"/profiles/{pid}/lab-matrix").json()
    assert matrix["dates"] == ["2026-09-21"]
    sodium = next(row for row in matrix["rows"] if row["display_name"] == "Sodium")
    cell = sodium["cells"]["2026-09-21"]
    assert cell["value_text"] == "140"
    assert cell["report_id"] == second["id"]
    assert cell["also"] == [
        {"report_id": first["id"], "panel_name": "BMP", "value_text": "133"}
    ]


def test_null_collection_time_omitted_from_matrix():
    p = _profile()
    pid = p["id"]
    enc = _encounter(pid, datetime(2026, 5, 1, 8, 0).isoformat())
    r = client.post(
        "/lab-reports",
        json={
            "profile_id": pid,
            "encounter_id": enc["id"],
            "panel_name": "BMP",
            "collection_time": None,
            "components": [{"original_name": "Sodium", "value_text": "140", "unit_original": "mmol/L"}],
        },
    )
    assert r.status_code == 200
    matrix = client.get(f"/profiles/{pid}/lab-matrix").json()
    assert matrix["dates"] == []
    assert matrix["rows"] == []
    listed = client.get(f"/profiles/{pid}/lab-reports").json()
    assert len(listed) == 1


def test_original_trend_empty_points_not_404():
    p = _profile()
    r = client.get(f"/profiles/{p['id']}/trends/original/NoSuchThing")
    assert r.status_code == 200
    assert r.json()["points"] == []
