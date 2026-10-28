"""Phase 11: several panels printed on one document file as several lab reports."""
import os
os.environ["DATABASE_URL"] = "sqlite:////tmp/test_phase11.db"
os.environ["STORAGE_ROOT"] = "/tmp/phr_docs_test11"
import shutil
shutil.rmtree("/tmp/phr_docs_test11", ignore_errors=True)
os.makedirs("/tmp/phr_docs_test11", exist_ok=True)

import pytest
from io import BytesIO
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from reportlab.pdfgen import canvas

from app.main import app
from app.database import get_db
from app.models import Base, Encounter, EncounterType, LabReport

test_engine = create_engine(
    "sqlite:////tmp/test_phase11.db",
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


def make_pdf(lines) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf)
    y = 780
    for line in lines:
        c.drawString(50, y, line)
        y -= 20
    c.save()
    return buf.getvalue()


CMP_THEN_CBC = [
    "Collected: 2026-09-21",
    "COMPREHENSIVE METABOLIC PANEL",
    "Sodium 140 mmol/L (135-145)",
    "Potassium 4.2 mmol/L (3.5-5.1)",
    "Glucose 95 mg/dL (70-99)",
    "COMPLETE BLOOD COUNT",
    "WBC 6.2 10*3/uL (3.8-10.8)",
    "Hemoglobin 13.5 g/dL (11.7-15.5)",
]


def upload_and_process(pid: int, lines, name="labs.pdf") -> dict:
    r = client.post(
        f"/profiles/{pid}/documents",
        files={"file": (name, make_pdf(lines), "application/pdf")},
    )
    assert r.status_code == 200
    data = r.json()
    assert client.post(f"/jobs/{data['job_id']}/process").status_code == 200
    return data


def new_profile() -> int:
    return client.post("/profiles", json={"legal_name": "Test"}).json()["id"]


def reports_by_panel(pid: int) -> dict:
    labs = client.get(f"/profiles/{pid}/lab-reports").json()
    return {lab["panel_name"]: [c["original_name"] for c in lab["components"]] for lab in labs}


def test_cmp_then_cbc_files_two_reports_on_one_encounter():
    pid = new_profile()
    upload_and_process(pid, CMP_THEN_CBC)
    by_panel = reports_by_panel(pid)
    assert set(by_panel) == {"CMP", "CBC"}
    assert {"Sodium", "Potassium", "Glucose"} <= set(by_panel["CMP"])
    assert {"WBC", "Hemoglobin"} <= set(by_panel["CBC"])
    assert "WBC" not in by_panel["CMP"]
    assert "Sodium" not in by_panel["CBC"]

    db = TestingSessionLocal()
    try:
        encs = db.query(Encounter).filter(
            Encounter.profile_id == pid, Encounter.type == EncounterType.lab
        ).all()
        assert len(encs) == 1
        reports = db.query(LabReport).filter(LabReport.profile_id == pid).all()
        assert {r.encounter_id for r in reports} == {encs[0].id}
    finally:
        db.close()


def test_bmp_document_still_one_report_named_bmp():
    pid = new_profile()
    upload_and_process(pid, [
        "BASIC METABOLIC PANEL",
        "Collected: 2024-05-01",
        "Sodium 140 mmol/L (135-145)",
        "Potassium 4.2 mmol/L (3.5-5.1)",
    ])
    assert list(reports_by_panel(pid)) == ["BMP"]


def test_reprocess_does_not_duplicate_panels():
    pid = new_profile()
    data = upload_and_process(pid, CMP_THEN_CBC)
    assert client.post(f"/jobs/{data['job_id']}/retry").status_code == 200
    client.post(f"/jobs/{data['job_id']}/process")
    labs = client.get(f"/profiles/{pid}/lab-reports").json()
    assert sorted(lab["panel_name"] for lab in labs) == ["CBC", "CMP"]


def test_proposal_payload_carries_line_panel():
    pid = new_profile()
    upload_and_process(pid, CMP_THEN_CBC[:-1] + ["MysteryCount 7.1 10*3/uL"])
    props = client.get(f"/profiles/{pid}/proposals").json()
    mystery = next(p for p in props if p["payload"]["original_name"] == "MysteryCount")
    assert mystery["payload"]["panel_name"] == "CBC"


def test_accepting_cbc_line_does_not_append_to_cmp():
    pid = new_profile()
    upload_and_process(pid, [
        "Collected: 2026-09-21",
        "COMPREHENSIVE METABOLIC PANEL",
        "Sodium 140 mmol/L (135-145)",
        "COMPLETE BLOOD COUNT",
        "MysteryCount 7.1 10*3/uL",
    ])
    assert list(reports_by_panel(pid)) == ["CMP"]
    prop = client.get(f"/profiles/{pid}/proposals").json()[0]
    assert prop["payload"]["panel_name"] == "CBC"
    assert client.post(f"/proposals/{prop['id']}/accept").status_code == 200

    by_panel = reports_by_panel(pid)
    assert by_panel["CMP"] == ["Sodium"]
    assert by_panel["CBC"] == ["MysteryCount"]
    db = TestingSessionLocal()
    try:
        reports = db.query(LabReport).filter(LabReport.profile_id == pid).all()
        assert len({r.encounter_id for r in reports}) == 1
    finally:
        db.close()


def test_accepting_two_lines_of_one_panel_shares_a_report():
    pid = new_profile()
    upload_and_process(pid, [
        "Collected: 2026-09-21",
        "COMPLETE BLOOD COUNT",
        "MysteryCount 7.1 10*3/uL",
        "OtherCount 2.2 10*3/uL",
    ])
    for prop in client.get(f"/profiles/{pid}/proposals").json():
        assert client.post(f"/proposals/{prop['id']}/accept").status_code == 200
    by_panel = reports_by_panel(pid)
    assert list(by_panel) == ["CBC"]
    assert sorted(by_panel["CBC"]) == ["MysteryCount", "OtherCount"]
