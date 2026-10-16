import os
os.environ["DATABASE_URL"] = "sqlite:////tmp/test_phase3.db"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.main import app
from app.database import get_db, engine as app_engine
from app.models import Base
from datetime import datetime

# Force app engine to use same file
test_engine = create_engine(
    "sqlite:////tmp/test_phase3.db",
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

app.dependency_overrides[get_db] = override_get_db
Base.metadata.create_all(bind=test_engine)

client = TestClient(app)

@pytest.fixture(autouse=True)
def clean_db():
    db = TestingSessionLocal()
    for table in reversed(Base.metadata.sorted_tables):
        db.execute(table.delete())
    db.commit()
    db.close()
    from app.seed import load_analytes
    db = TestingSessionLocal()
    load_analytes(db)
    db.close()
    yield

def test_cmp_bmp_sodium_series_and_cmp_only_kept():
    p = client.post("/profiles", json={"legal_name": "Test Person"}).json()
    pid = p["id"]
    now = datetime.utcnow().isoformat()
    enc1 = client.post("/encounters", json={
        "profile_id": pid, "type": "lab", "start": now, "reason": "BMP"
    }).json()
    enc2 = client.post("/encounters", json={
        "profile_id": pid, "type": "lab", "start": now, "reason": "CMP"
    }).json()
    bmp = client.post("/lab-reports", json={
        "profile_id": pid, "encounter_id": enc1["id"], "panel_name": "BMP",
        "components": [
            {"original_name": "Na", "value_text": "140", "unit_original": "mmol/L", "ref_low": 135, "ref_high": 145},
            {"original_name": "Sodium", "value_text": "141", "unit_original": "mEq/L", "ref_low": 135, "ref_high": 145},
        ]
    }).json()
    cmp = client.post("/lab-reports", json={
        "profile_id": pid, "encounter_id": enc2["id"], "panel_name": "CMP",
        "components": [
            {"original_name": "Sodium", "value_text": "139", "unit_original": "mmol/L"},
            {"original_name": "ALT", "value_text": "25", "unit_original": "U/L"},
        ]
    }).json()
    trend = client.get(f"/profiles/{pid}/trends/Sodium").json()
    sodium_points = [pt for pt in trend["points"] if pt.get("normalized_value") is not None]
    assert len(sodium_points) >= 2, f"got {len(sodium_points)} points: {trend}"
    assert any(c["original_name"] == "ALT" for c in cmp["components"])
    assert len(bmp["components"]) == 2
    assert len(cmp["components"]) == 2

def test_ldl_not_attached():
    p = client.post("/profiles", json={"legal_name": "P"}).json()
    enc = client.post("/encounters", json={"profile_id": p["id"], "type": "lab", "start": datetime.utcnow().isoformat()}).json()
    r = client.post("/lab-reports", json={
        "profile_id": p["id"], "encounter_id": enc["id"], "panel_name": "Lipid",
        "components": [{"original_name": "LDL", "value_text": "120", "unit_original": "mg/dL"}]
    }).json()
    assert r["components"][0]["canonical_analyte_id"] is None

def test_meq_sodium_normalizes_original_unit_preserved():
    p = client.post("/profiles", json={"legal_name": "P"}).json()
    enc = client.post("/encounters", json={"profile_id": p["id"], "type": "lab", "start": datetime.utcnow().isoformat()}).json()
    r = client.post("/lab-reports", json={
        "profile_id": p["id"], "encounter_id": enc["id"], "panel_name": "BMP",
        "components": [{"original_name": "Sodium", "value_text": "140", "unit_original": "mEq/L"}]
    }).json()
    c = r["components"][0]
    assert c["unit_original"] == "mEq/L"
    assert c["normalized_unit"] == "mmol/L"
    assert c["normalized_value"] == 140.0
    assert c["canonical_analyte_id"] is not None

def test_lt_0_1_not_numeric():
    p = client.post("/profiles", json={"legal_name": "P"}).json()
    enc = client.post("/encounters", json={"profile_id": p["id"], "type": "lab", "start": datetime.utcnow().isoformat()}).json()
    r = client.post("/lab-reports", json={
        "profile_id": p["id"], "encounter_id": enc["id"], "panel_name": "Other",
        "components": [{"original_name": "Something", "value_text": "<0.1", "unit_original": "ng/mL"}]
    }).json()
    c = r["components"][0]
    assert c["value_text"] == "<0.1"
    assert c["value_numeric"] is None
    assert c["normalized_value"] is None

def test_no_range_flag_unknown_displays():
    p = client.post("/profiles", json={"legal_name": "P"}).json()
    enc = client.post("/encounters", json={"profile_id": p["id"], "type": "lab", "start": datetime.utcnow().isoformat()}).json()
    r = client.post("/lab-reports", json={
        "profile_id": p["id"], "encounter_id": enc["id"], "panel_name": "BMP",
        "components": [{"original_name": "Sodium", "value_text": "140", "unit_original": "mmol/L"}]
    }).json()
    c = r["components"][0]
    assert c["abnormal_flag"] == "unknown"
    assert c["value_text"] == "140"

def test_order_links_separate_lab_same_day():
    p = client.post("/profiles", json={"legal_name": "P"}).json()
    day = datetime(2026, 10, 16, 10, 0).isoformat()
    visit = client.post("/encounters", json={
        "profile_id": p["id"], "type": "office_visit", "start": day, "reason": "Visit"
    }).json()
    lab = client.post("/encounters", json={
        "profile_id": p["id"], "type": "lab", "start": day, "reason": "Lab"
    }).json()
    assert visit["id"] != lab["id"]
    order = client.post("/orders", json={
        "profile_id": p["id"], "category": "lab", "name": "CMP",
        "ordered_at": day, "ordering_encounter_id": visit["id"]
    }).json()
    link = client.post(f"/orders/{order['id']}/link-result", json={"result_encounter_id": lab["id"]})
    assert link.status_code == 200
    orders = client.get(f"/encounters/{visit['id']}/orders").json()
    assert len(orders) == 1
    assert orders[0]["status"] == "completed"
    fulfilling = client.get(f"/encounters/{lab['id']}/fulfilling-orders").json()
    assert len(fulfilling) == 1

def test_profile_isolation():
    p1 = client.post("/profiles", json={"legal_name": "A"}).json()
    p2 = client.post("/profiles", json={"legal_name": "B"}).json()
    enc1 = client.post("/encounters", json={"profile_id": p1["id"], "type": "lab", "start": datetime.utcnow().isoformat()}).json()
    client.post("/lab-reports", json={
        "profile_id": p1["id"], "encounter_id": enc1["id"], "panel_name": "BMP",
        "components": [{"original_name": "Sodium", "value_text": "140", "unit_original": "mmol/L"}]
    })
    reports2 = client.get(f"/profiles/{p2['id']}/lab-reports").json()
    assert len(reports2) == 0
    trend2 = client.get(f"/profiles/{p2['id']}/trends/Sodium").json()
    assert len(trend2["points"]) == 0
    reports1 = client.get(f"/profiles/{p1['id']}/lab-reports").json()
    assert len(reports1) == 1
