"""Phase 12: household panel catalog and data management."""
import os

os.environ["DATABASE_URL"] = "sqlite:////tmp/test_phase12.db"
os.environ["STORAGE_ROOT"] = "/tmp/phr_docs_test12"
os.environ.setdefault("AUTH_DISABLED", "1")

import shutil

shutil.rmtree("/tmp/phr_docs_test12", ignore_errors=True)
os.makedirs("/tmp/phr_docs_test12", exist_ok=True)

import re
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app import main as mainmod
from app.database import get_db
from app.extraction import detect_panel_headers, detect_panel_name
from app.models import (
    Base,
    CanonicalAnalyte,
    Household,
    LabReport,
    PanelComponentDefinition,
    PanelDefinition,
)

test_engine = create_engine(
    "sqlite:////tmp/test_phase12.db",
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
STARTER_NAMES = {
    "CMP",
    "BMP",
    "CBC",
    "Lipid Panel",
    "Hemoglobin A1c",
    "TSH",
}


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


def seed_count() -> int:
    db = TestingSessionLocal()
    try:
        return db.query(CanonicalAnalyte).count()
    finally:
        db.close()


def new_profile() -> int:
    return client.post("/profiles", json={"legal_name": "Test"}).json()["id"]


def make_pdf(lines) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf)
    y = 780
    for line in lines:
        c.drawString(50, y, line)
        y -= 20
    c.save()
    return buf.getvalue()


def catalog():
    r = client.get("/panel-catalog")
    assert r.status_code == 200
    return r.json()


def test_empty_household_seeds_six_starter_panels():
    before = seed_count()
    data = catalog()
    names = {p["name"] for p in data["panels"]}
    assert names == STARTER_NAMES
    cmp_panel = next(p for p in data["panels"] if p["name"] == "CMP")
    cbc_panel = next(p for p in data["panels"] if p["name"] == "CBC")
    cmp_canonicals = {c["canonical_name"] for c in cmp_panel["components"]}
    cbc_canonicals = {c["canonical_name"] for c in cbc_panel["components"]}
    assert "Sodium" in cmp_canonicals
    assert "Leukocytes" in cbc_canonicals
    assert seed_count() == before


def test_import_json_merge_adds_unmatched_iron_panel():
    catalog()
    before = seed_count()
    body = {
        "version": 1,
        "panels": [
            {
                "name": "Iron panel",
                "aliases": ["iron studies"],
                "components": [{"sequence": 1, "alias": "ferritin"}],
            }
        ],
    }
    r = client.post("/panel-catalog/import?mode=merge", json=body)
    assert r.status_code == 200
    out = r.json()
    assert out["imported"] == 1
    iron = next(p for p in catalog()["panels"] if p["name"] == "Iron panel")
    assert "iron studies" in [a.lower() for a in iron["aliases"]]
    ferritin = iron["components"][0]
    assert ferritin["original_alias"] == "ferritin"
    assert ferritin["canonical_analyte_id"] is None
    assert any(u["alias"] == "ferritin" for u in out["unmatched_components"])
    assert seed_count() == before
    assert {p["name"] for p in catalog()["panels"]} >= STARTER_NAMES | {"Iron panel"}


def test_replace_does_not_delete_lab_reports():
    pid = new_profile()
    catalog()
    pdf = make_pdf([
        "Collected: 2026-09-21",
        "COMPREHENSIVE METABOLIC PANEL",
        "Sodium 140 mmol/L (135-145)",
        "Potassium 4.2 mmol/L (3.5-5.1)",
    ])
    up = client.post(
        f"/profiles/{pid}/documents",
        files={"file": ("labs.pdf", pdf, "application/pdf")},
    )
    assert up.status_code == 200
    assert client.post(f"/jobs/{up.json()['job_id']}/process").status_code == 200
    labs = client.get(f"/profiles/{pid}/lab-reports").json()
    assert labs
    report_ids = [lab["id"] for lab in labs]

    r = client.post(
        "/panel-catalog/import?mode=replace",
        json={
            "version": 1,
            "panels": [
                {
                    "name": "Custom",
                    "aliases": ["custom panel"],
                    "components": [{"sequence": 1, "alias": "sodium", "canonical_name": "Sodium"}],
                }
            ],
        },
    )
    assert r.status_code == 200
    names = {p["name"] for p in catalog()["panels"]}
    assert names == {"Custom"}
    still = client.get(f"/profiles/{pid}/lab-reports").json()
    assert [lab["id"] for lab in still] == report_ids
    db = TestingSessionLocal()
    try:
        assert db.query(LabReport).count() == len(report_ids)
    finally:
        db.close()


def test_template_csv_has_required_headers():
    r = client.get("/panel-catalog/template.csv")
    assert r.status_code == 200
    assert "attachment" in (r.headers.get("content-disposition") or "")
    assert "panel-catalog-template.csv" in (r.headers.get("content-disposition") or "")
    header = r.text.splitlines()[0]
    cols = [c.strip() for c in header.split(",")]
    assert cols == [
        "panel_name",
        "panel_aliases",
        "sequence",
        "component_alias",
        "canonical_name",
    ]


def test_template_json_has_starter_examples():
    r = client.get("/panel-catalog/template.json")
    assert r.status_code == 200
    assert "panel-catalog-template.json" in (r.headers.get("content-disposition") or "")
    data = r.json()
    assert data["version"] == 1
    assert {p["name"] for p in data["panels"]} == STARTER_NAMES


def test_fake_canonical_does_not_insert_analyte():
    catalog()
    before = seed_count()
    r = client.post(
        "/panel-catalog/import?mode=merge",
        json={
            "version": 1,
            "panels": [
                {
                    "name": "Magic panel",
                    "aliases": ["magic"],
                    "components": [
                        {"sequence": 1, "alias": "magic enzyme", "canonical_name": "MagicEnzyme"}
                    ],
                }
            ],
        },
    )
    assert r.status_code == 200
    unmatched = r.json()["unmatched_components"]
    assert any(u.get("canonical_name") == "MagicEnzyme" for u in unmatched)
    magic = next(p for p in catalog()["panels"] if p["name"] == "Magic panel")
    assert magic["components"][0]["canonical_analyte_id"] is None
    assert seed_count() == before
    db = TestingSessionLocal()
    try:
        assert db.query(CanonicalAnalyte).filter(CanonicalAnalyte.name == "MagicEnzyme").first() is None
        assert db.query(CanonicalAnalyte).filter(CanonicalAnalyte.loinc == "MagicEnzyme").first() is None
    finally:
        db.close()


def test_detect_panel_name_still_returns_cmp_with_catalog_alias():
    catalog()
    extra = [
        (re.compile(r"COMPREHENSIVE METABOLIC PANEL", re.I), "CMP"),
    ]
    text = "COMPREHENSIVE METABOLIC PANEL\nSodium 140 mmol/L (135-145)\n"
    assert detect_panel_name(text, extra) == "CMP"
    assert detect_panel_headers(text, extra)[0]["name"] == "CMP"
    assert detect_panel_name(text) == "CMP"


def test_catalog_alias_used_when_parsing_document():
    pid = new_profile()
    catalog()
    client.post(
        "/panel-catalog/import?mode=merge",
        json={
            "version": 1,
            "panels": [
                {
                    "name": "Quest Super CMP",
                    "aliases": ["quest super cmp"],
                    "components": [
                        {"sequence": 1, "alias": "sodium", "canonical_name": "Sodium"}
                    ],
                }
            ],
        },
    )
    pdf = make_pdf([
        "Collected: 2026-09-21",
        "QUEST SUPER CMP",
        "Sodium 140 mmol/L (135-145)",
    ])
    up = client.post(
        f"/profiles/{pid}/documents",
        files={"file": ("quest.pdf", pdf, "application/pdf")},
    )
    assert client.post(f"/jobs/{up.json()['job_id']}/process").status_code == 200
    labs = client.get(f"/profiles/{pid}/lab-reports").json()
    assert [lab["panel_name"] for lab in labs] == ["Quest Super CMP"]


def test_unknown_component_stays_in_review_inbox():
    pid = new_profile()
    catalog()
    client.post(
        "/panel-catalog/import?mode=merge",
        json={
            "version": 1,
            "panels": [
                {
                    "name": "Iron panel",
                    "aliases": ["iron studies"],
                    "components": [{"sequence": 1, "alias": "ferritin"}],
                }
            ],
        },
    )
    pdf = make_pdf([
        "Collected: 2026-09-21",
        "IRON STUDIES",
        "Ferritin 40 ng/mL (10-150)",
    ])
    up = client.post(
        f"/profiles/{pid}/documents",
        files={"file": ("iron.pdf", pdf, "application/pdf")},
    )
    assert client.post(f"/jobs/{up.json()['job_id']}/process").status_code == 200
    labs = client.get(f"/profiles/{pid}/lab-reports").json()
    assert labs == []
    props = client.get(f"/profiles/{pid}/proposals").json()
    assert any(p["payload"]["original_name"] == "Ferritin" for p in props)


def test_other_household_panels_are_hidden():
    catalog()
    db = TestingSessionLocal()
    try:
        h2 = Household(name="Other house")
        db.add(h2)
        db.flush()
        other = PanelDefinition(household_id=h2.id, name="Secret panel", aliases="secret")
        db.add(other)
        db.flush()
        db.add(PanelComponentDefinition(
            panel_definition_id=other.id,
            sequence=1,
            original_alias="hidden",
        ))
        db.commit()
    finally:
        db.close()
    names = {p["name"] for p in catalog()["panels"]}
    assert "Secret panel" not in names


def test_catalog_requires_login_when_auth_on(monkeypatch):
    monkeypatch.setattr(mainmod, "AUTH_DISABLED", False)
    r = client.get("/panel-catalog")
    assert r.status_code in (401, 403)


def test_delete_panel_leaves_filed_labs():
    pid = new_profile()
    data = catalog()
    cmp_id = next(p["id"] for p in data["panels"] if p["name"] == "CMP")
    pdf = make_pdf([
        "Collected: 2026-09-21",
        "COMPREHENSIVE METABOLIC PANEL",
        "Sodium 140 mmol/L (135-145)",
    ])
    up = client.post(
        f"/profiles/{pid}/documents",
        files={"file": ("cmp.pdf", pdf, "application/pdf")},
    )
    client.post(f"/jobs/{up.json()['job_id']}/process")
    assert client.delete(f"/panel-catalog/{cmp_id}").status_code == 200
    names = {p["name"] for p in catalog()["panels"]}
    assert "CMP" not in names
    labs = client.get(f"/profiles/{pid}/lab-reports").json()
    assert any(lab["panel_name"] == "CMP" for lab in labs)


def test_csv_upload_merge():
    catalog()
    csv_body = (
        "panel_name,panel_aliases,sequence,component_alias,canonical_name\n"
        'Iron panel,"iron studies",1,ferritin,\n'
    )
    r = client.post(
        "/panel-catalog/import?mode=merge",
        files={"file": ("panels.csv", csv_body, "text/csv")},
    )
    assert r.status_code == 200
    names = {p["name"] for p in catalog()["panels"]}
    assert "Iron panel" in names
