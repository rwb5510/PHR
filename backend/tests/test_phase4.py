import os
os.environ["DATABASE_URL"] = "sqlite:////tmp/test_phase4.db"
os.environ["STORAGE_ROOT"] = "/tmp/phr_docs_test"
import shutil
shutil.rmtree("/tmp/phr_docs_test", ignore_errors=True)
os.makedirs("/tmp/phr_docs_test", exist_ok=True)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.main import app
from app.database import get_db
from app.models import Base
from datetime import datetime
from io import BytesIO
from reportlab.pdfgen import canvas
from PIL import Image, ImageDraw, ImageFont

test_engine = create_engine(
    "sqlite:////tmp/test_phase4.db",
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
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    from app.seed import load_analytes
    load_analytes(db)
    db.close()
    shutil.rmtree("/tmp/phr_docs_test", ignore_errors=True)
    os.makedirs("/tmp/phr_docs_test", exist_ok=True)
    yield

def make_bmp_pdf() -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(50, 750, "BASIC METABOLIC PANEL")
    c.drawString(50, 730, "Collected: 2024-05-01")
    lines = [
        "Sodium 140 mmol/L (135-145)",
        "Potassium 4.2 mmol/L (3.5-5.1)",
        "Chloride 102 mmol/L (98-107)",
        "Bicarbonate 24 mmol/L (22-29)",
        "Glucose 95 mg/dL (70-100)",
        "Urea nitrogen 15 mg/dL (7-20)",
        "Creatinine 0.9 mg/dL (0.6-1.2)",
    ]
    y = 700
    for line in lines:
        c.drawString(50, y, line)
        y -= 20
    c.save()
    return buf.getvalue()

def make_scanned_image() -> bytes:
    img = Image.new("RGB", (400, 100), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((10, 40), "Sodium 138 mmol/L", fill="black")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def test_text_pdf_bmp_auto_files_and_source_opens():
    p = client.post("/profiles", json={"legal_name": "Test"}).json()
    pid = p["id"]
    pdf = make_bmp_pdf()
    r = client.post(f"/profiles/{pid}/documents", files={"file": ("bmp.pdf", pdf, "application/pdf")})
    assert r.status_code == 200
    data = r.json()
    assert "job_id" in data
    # process
    pr = client.post(f"/jobs/{data['job_id']}/process")
    assert pr.status_code == 200
    assert pr.json()["status"] in ("filed", "needs_review")
    # check labs
    labs = client.get(f"/profiles/{pid}/lab-reports").json()
    assert len(labs) >= 1
    report = labs[0]
    names = [c["original_name"] for c in report["components"]]
    assert "Sodium" in names
    assert "Potassium" in names
    assert report["source_document_id"] is not None
    # open source
    fr = client.get(f"/documents/{report['source_document_id']}/file")
    assert fr.status_code == 200
    assert fr.content.startswith(b"%PDF")

def test_scanned_image_gets_ocr():
    p = client.post("/profiles", json={"legal_name": "Test"}).json()
    pid = p["id"]
    img = make_scanned_image()
    r = client.post(f"/profiles/{pid}/documents", files={"file": ("scan.png", img, "image/png")})
    data = r.json()
    client.post(f"/jobs/{data['job_id']}/process")
    text_r = client.get(f"/documents/{data['document_id']}/text")
    assert text_r.status_code == 200
    body = text_r.json()
    assert body["ocr_used"] is True
    assert body["extracted_text"] and len(body["extracted_text"].strip()) > 5

def make_messy_lab_pdf() -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf)
    y = 800
    for line in [
        "REGIONAL REFERENCE LABORATORY",
        "123 Laboratory Drive  Anytown, ST 00000",
        "Phone: 800 555 0100  Fax: 800 555 0101",
        "CLIA # 11D1234567",
        "Patient: Pat Sample  DOB: 01/01/1980  Age: 45 years",
        "Date Collected: 2024-05-01",
        "COMPREHENSIVE METABOLIC PANEL",
        "Test Name  Result  Units  Reference Range",
        "Sodium 140 mmol/L (135-145)",
        "Potassium 4.2 mmol/L (3.5-5.1)",
        "Glucose 95 mg/dL (70-99)",
        "LDL Cholesterol 110 mg/dL",
        "Please see comments below.",
        "Laboratory Director: Jane Director, MD",
        "Page 1 of 2",
    ]:
        c.drawString(40, y, line)
        y -= 18
    c.save()
    return buf.getvalue()


def test_messy_pdf_files_bmp_and_ignores_letterhead():
    p = client.post("/profiles", json={"legal_name": "Test"}).json()
    pid = p["id"]
    pdf = make_messy_lab_pdf()
    r = client.post(f"/profiles/{pid}/documents", files={"file": ("messy.pdf", pdf, "application/pdf")})
    client.post(f"/jobs/{r.json()['job_id']}/process")
    labs = client.get(f"/profiles/{pid}/lab-reports").json()
    assert len(labs) >= 1
    names = [c["original_name"] for lab in labs for c in lab["components"]]
    assert "Sodium" in names
    assert "Potassium" in names
    assert "Glucose" in names
    assert all("Phone" not in n and "Director" not in n and "Page" not in n for n in names)
    props = client.get(f"/profiles/{pid}/proposals").json()
    quotes = " ".join((pr.get("quote") or "") + str(pr.get("payload")) for pr in props)
    assert "800 555" not in quotes
    assert "Page 1" not in quotes
    assert any("LDL" in (pr.get("quote") or "") or "LDL" in str(pr.get("payload")) for pr in props)
    assert all("LDL" not in c["original_name"] for lab in labs for c in lab["components"])


def test_unknown_analyte_in_inbox():
    p = client.post("/profiles", json={"legal_name": "Test"}).json()
    pid = p["id"]
    buf = BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(50, 750, "Collected: 2024-05-01")
    c.drawString(50, 730, "FooBar 1.2 mg/dL")
    c.save()
    pdf = buf.getvalue()
    r = client.post(f"/profiles/{pid}/documents", files={"file": ("unk.pdf", pdf, "application/pdf")})
    data = r.json()
    client.post(f"/jobs/{data['job_id']}/process")
    props = client.get(f"/profiles/{pid}/proposals").json()
    assert len(props) >= 1
    assert any("FooBar" in (pr.get("quote") or "") or "FooBar" in str(pr.get("payload")) for pr in props)
    labs = client.get(f"/profiles/{pid}/lab-reports").json()
    # unknown should not be charted
    assert all("FooBar" not in c["original_name"] for lab in labs for c in lab["components"])

def test_duplicate_upload_warning():
    p = client.post("/profiles", json={"legal_name": "Test"}).json()
    pid = p["id"]
    pdf = make_bmp_pdf()
    r1 = client.post(f"/profiles/{pid}/documents", files={"file": ("bmp.pdf", pdf, "application/pdf")})
    assert "job_id" in r1.json()
    r2 = client.post(f"/profiles/{pid}/documents", files={"file": ("bmp.pdf", pdf, "application/pdf")})
    assert r2.json().get("duplicate") is True
    assert "warning" in r2.json()
    docs = client.get(f"/profiles/{pid}/documents").json()
    assert len(docs) == 1

def make_column_lab_pdf() -> bytes:
    """Names, values, units, and ranges drawn as separate columns (real lab PDFs)."""
    buf = BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(40, 800, "REGIONAL REFERENCE LABORATORY")
    c.drawString(40, 782, "Phone: 800 555 0100  Fax: 800 555 0101")
    c.drawString(40, 764, "Date Collected: 05/01/2024")
    c.drawString(40, 746, "BASIC METABOLIC PANEL")
    c.drawString(40, 728, "Test Name")
    c.drawString(220, 728, "Result")
    c.drawString(300, 728, "Units")
    c.drawString(380, 728, "Reference Range")
    rows = [
        ("Sodium", "140", "mmol/L", "135-145"),
        ("Potassium", "4.2", "mmol/L", "3.5-5.1"),
        ("Chloride", "102", "mmol/L", "98-107"),
        ("Glucose", "95", "mg/dL", "70-99"),
    ]
    # Draw one column at a time so the content stream is not already row-wise.
    y0 = 710
    for i, (name, _, _, _) in enumerate(rows):
        c.drawString(40, y0 - i * 18, name)
    for i, (_, val, _, _) in enumerate(rows):
        c.drawString(220, y0 - i * 18, val)
    for i, (_, _, unit, _) in enumerate(rows):
        c.drawString(300, y0 - i * 18, unit)
    for i, (_, _, _, rng) in enumerate(rows):
        c.drawString(380, y0 - i * 18, rng)
    c.drawString(40, 620, "Laboratory Director: Jane Director, MD")
    c.drawString(40, 602, "Page 1 of 1")
    c.save()
    return buf.getvalue()


def test_column_layout_pdf_files_rows_not_letterhead():
    p = client.post("/profiles", json={"legal_name": "Test"}).json()
    pid = p["id"]
    pdf = make_column_lab_pdf()
    r = client.post(f"/profiles/{pid}/documents", files={"file": ("cols.pdf", pdf, "application/pdf")})
    client.post(f"/jobs/{r.json()['job_id']}/process")
    labs = client.get(f"/profiles/{pid}/lab-reports").json()
    names = [c["original_name"] for lab in labs for c in lab["components"]]
    assert "Sodium" in names
    assert "Potassium" in names
    assert "Glucose" in names
    assert all("Phone" not in n and "Director" not in n and "Page" not in n for n in names)
    props = client.get(f"/profiles/{pid}/proposals").json()
    blob = " ".join((pr.get("quote") or "") + str(pr.get("payload")) for pr in props)
    assert "800 555" not in blob
    assert "Page 1" not in blob


def test_reprocess_reruns_parse():
    p = client.post("/profiles", json={"legal_name": "Test"}).json()
    pid = p["id"]
    pdf = make_column_lab_pdf()
    r = client.post(f"/profiles/{pid}/documents", files={"file": ("cols.pdf", pdf, "application/pdf")})
    job_id = r.json()["job_id"]
    client.post(f"/jobs/{job_id}/process")
    first = client.get(f"/profiles/{pid}/lab-reports").json()
    assert len(first) >= 1
    rr = client.post(f"/jobs/{job_id}/retry")
    assert rr.status_code == 200
    assert rr.json()["status"] == "queued"
    client.post(f"/jobs/{job_id}/process")
    second = client.get(f"/profiles/{pid}/lab-reports").json()
    names = [c["original_name"] for lab in second for c in lab["components"]]
    assert "Sodium" in names


def test_worker_crash_mid_job_retryable():
    p = client.post("/profiles", json={"legal_name": "Test"}).json()
    pid = p["id"]
    pdf = make_bmp_pdf()
    r = client.post(f"/profiles/{pid}/documents", files={"file": ("bmp.pdf", pdf, "application/pdf")})
    data = r.json()
    doc_id = data["document_id"]
    job_id = data["job_id"]
    # simulate crash: mark processing without completing
    db = TestingSessionLocal()
    from app.models import Job, JobStatus
    job = db.query(Job).filter(Job.id == job_id).first()
    job.status = JobStatus.processing
    db.commit()
    db.close()
    # file still there
    fr = client.get(f"/documents/{doc_id}/file")
    assert fr.status_code == 200
    # retry
    rr = client.post(f"/jobs/{job_id}/retry")
    assert rr.status_code == 200
    assert rr.json()["status"] == "queued"
    # process succeeds
    pr = client.post(f"/jobs/{job_id}/process")
    assert pr.json()["status"] in ("filed", "needs_review")
    # file still there
    fr2 = client.get(f"/documents/{doc_id}/file")
    assert fr2.status_code == 200
