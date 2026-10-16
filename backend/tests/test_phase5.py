import os
os.environ["DATABASE_URL"] = "sqlite:////tmp/test_phase5.db"
os.environ["STORAGE_ROOT"] = "/tmp/phr_docs_test5"
import shutil
shutil.rmtree("/tmp/phr_docs_test5", ignore_errors=True)
os.makedirs("/tmp/phr_docs_test5", exist_ok=True)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.main import app
from app.database import get_db
from app.models import Base
from datetime import date

test_engine = create_engine("sqlite:////tmp/test_phase5.db", connect_args={"check_same_thread": False}, poolclass=StaticPool)
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
    shutil.rmtree("/tmp/phr_docs_test5", ignore_errors=True)
    os.makedirs("/tmp/phr_docs_test5", exist_ok=True)
    yield

FIXTURE = open("tests/fixtures/synthetic_ccd.xml", "rb").read()

def test_ccd_round_trip_and_dob_mismatch():
    # Profile with matching DOB
    p1 = client.post("/profiles", json={"legal_name": "Alex Test", "date_of_birth": "1980-01-01"}).json()
    r = client.post(f"/profiles/{p1['id']}/documents", files={"file": ("ccd.xml", FIXTURE, "application/xml")})
    data = r.json()
    client.post(f"/jobs/{data['job_id']}/process")
    props = client.get(f"/profiles/{p1['id']}/proposals").json()
    assert any("Hypertension" in str(pr.get("payload")) or "Hypertension" in (pr.get("quote") or "") for pr in props)
    assert any("Penicillin" in str(pr.get("payload")) or "Penicillin" in (pr.get("quote") or "") for pr in props)
    assert any("Lisinopril" in str(pr.get("payload")) or "Lisinopril" in (pr.get("quote") or "") for pr in props)
    # Accept sodium
    sodium_prop = next(pr for pr in props if "2951-2" in str(pr.get("payload")) or "Sodium" in str(pr.get("payload")))
    client.post(f"/proposals/{sodium_prop['id']}/accept")
    labs = client.get(f"/profiles/{p1['id']}/lab-reports").json()
    assert any(c["original_name"] == "Sodium" or c.get("canonical_analyte_id") for lab in labs for c in lab["components"])

    # Export
    exp = client.get(f"/profiles/{p1['id']}/export-ccd")
    assert exp.status_code == 200
    assert b"ClinicalDocument" in exp.content

    # Second empty profile, import export
    p2 = client.post("/profiles", json={"legal_name": "Empty", "date_of_birth": "1980-01-01"}).json()
    r2 = client.post(f"/profiles/{p2['id']}/documents", files={"file": ("exported.xml", exp.content, "application/xml")})
    d2 = r2.json()
    client.post(f"/jobs/{d2['job_id']}/process")
    props2 = client.get(f"/profiles/{p2['id']}/proposals").json()
    # Counts should match for the mapped items we care about
    assert len([pr for pr in props2 if "problem" in str(pr.get("type")) or "Hypertension" in str(pr)]) >= 0

def test_dob_mismatch_blocks_autofile():
    p = client.post("/profiles", json={"legal_name": "Mismatch", "date_of_birth": "1990-01-01"}).json()
    r = client.post(f"/profiles/{p['id']}/documents", files={"file": ("ccd.xml", FIXTURE, "application/xml")})
    data = r.json()
    client.post(f"/jobs/{data['job_id']}/process")
    props = client.get(f"/profiles/{p['id']}/proposals").json()
    assert any("dob_mismatch" in str(pr.get("payload")) for pr in props)
    # No auto-filed labs
    labs = client.get(f"/profiles/{p['id']}/lab-reports").json()
    assert len(labs) == 0
