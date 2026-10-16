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
from app.models import Base, Problem, Allergy, Medication, LabComponent, LabReport

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

def count_for(profile_id, model):
    db = TestingSessionLocal()
    n = db.query(model).filter(model.profile_id == profile_id).count()
    db.close()
    return n

def test_ccd_round_trip_equal_counts():
    p1 = client.post("/profiles", json={"legal_name": "Alex Test", "date_of_birth": "1980-01-01"}).json()
    r = client.post(f"/profiles/{p1['id']}/documents", files={"file": ("ccd.xml", FIXTURE, "application/xml")})
    data = r.json()
    client.post(f"/jobs/{data['job_id']}/process")
    props = client.get(f"/profiles/{p1['id']}/proposals").json()
    # Accept all
    for pr in props:
        client.post(f"/proposals/{pr['id']}/accept")
    # Counts after accept
    p_count = count_for(p1["id"], Problem)
    a_count = count_for(p1["id"], Allergy)
    m_count = count_for(p1["id"], Medication)
    s_count = TestingSessionLocal().query(LabComponent).join(LabReport).filter(LabReport.profile_id == p1["id"], LabComponent.canonical_analyte_id.isnot(None)).count()
    assert p_count >= 1
    assert a_count >= 1
    assert m_count >= 1
    assert s_count >= 1

    # Export
    exp = client.get(f"/profiles/{p1['id']}/export-ccd")
    assert exp.status_code == 200
    assert b"ClinicalDocument" in exp.content
    assert b"Self-generated personal record" in exp.content

    # Second empty profile, import export
    p2 = client.post("/profiles", json={"legal_name": "Empty", "date_of_birth": "1980-01-01"}).json()
    r2 = client.post(f"/profiles/{p2['id']}/documents", files={"file": ("exported.xml", exp.content, "application/xml")})
    d2 = r2.json()
    client.post(f"/jobs/{d2['job_id']}/process")
    props2 = client.get(f"/profiles/{p2['id']}/proposals").json()
    for pr in props2:
        client.post(f"/proposals/{pr['id']}/accept")
    # Equal counts
    assert count_for(p2["id"], Problem) == p_count
    assert count_for(p2["id"], Allergy) == a_count
    assert count_for(p2["id"], Medication) == m_count
    s2 = TestingSessionLocal().query(LabComponent).join(LabReport).filter(LabReport.profile_id == p2["id"], LabComponent.canonical_analyte_id.isnot(None)).count()
    assert s2 == s_count

def test_dob_mismatch_blocks_autofile():
    p = client.post("/profiles", json={"legal_name": "Mismatch", "date_of_birth": "1990-01-01"}).json()
    r = client.post(f"/profiles/{p['id']}/documents", files={"file": ("ccd.xml", FIXTURE, "application/xml")})
    data = r.json()
    client.post(f"/jobs/{data['job_id']}/process")
    props = client.get(f"/profiles/{p['id']}/proposals").json()
    assert any("dob_mismatch" in str(pr.get("payload")) for pr in props)
    # No auto-filed rows
    assert count_for(p["id"], Problem) == 0
    assert count_for(p["id"], Allergy) == 0
    labs = client.get(f"/profiles/{p['id']}/lab-reports").json()
    assert len(labs) == 0
