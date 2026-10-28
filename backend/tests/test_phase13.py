"""Phase 13: imaging narratives become imaging_report proposals, not failed labs."""
import os
os.environ["DATABASE_URL"] = "sqlite:////tmp/test_phase13.db"
os.environ["STORAGE_ROOT"] = "/tmp/phr_docs_test13"
os.environ.setdefault("AUTH_DISABLED", "1")
import shutil
shutil.rmtree("/tmp/phr_docs_test13", ignore_errors=True)
os.makedirs("/tmp/phr_docs_test13", exist_ok=True)

import json
import pytest
from io import BytesIO
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from reportlab.pdfgen import canvas

from app.main import app
from app import main as mainmod
from app import processor as procmod
from app.database import get_db
from app.auth import hash_password
from app.document_class import classify_document, extract_imaging_reports
from app.models import (
    Base, Document, Encounter, EncounterType, Household, ImagingReport, LabReport, Profile,
    Proposal, ProposalStatus, ProposalType, User,
)

STORAGE = "/tmp/phr_docs_test13"
test_engine = create_engine(
    "sqlite:////tmp/test_phase13.db",
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

XR_LINES = [
    "Community Imaging Center",
    "EXAM: XR CHEST 1 VIEW PORTABLE",
    "Exam date: 2026-10-23",
    "HISTORY: Port placement.",
    "TECHNIQUE: Single frontal view of the chest.",
    "COMPARISON: None.",
    "FINDINGS: Right chest port catheter tip in the lower SVC.",
    "Lungs are clear. No pneumothorax.",
    "IMPRESSION: Port catheter tip in the lower SVC. No pneumothorax.",
    "Electronically signed by: Synthetic Radiologist MD",
]

BMP_LINES = [
    "Basic Metabolic Panel",
    "Collected: 2024-03-15",
    "Sodium 140 mmol/L 136-145",
    "Potassium 4.1 mmol/L 3.5-5.1",
    "Chloride 102 mmol/L 98-107",
    "Glucose 92 mg/dL 70-99",
]


@pytest.fixture(autouse=True)
def clean_db():
    app.dependency_overrides[get_db] = override_get_db
    mainmod.STORAGE_ROOT = STORAGE
    procmod.STORAGE_ROOT = STORAGE
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    from app.seed import load_analytes
    load_analytes(db)
    db.close()
    shutil.rmtree(STORAGE, ignore_errors=True)
    os.makedirs(STORAGE, exist_ok=True)
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


def _profile(name="Test"):
    return client.post("/profiles", json={"legal_name": name}).json()["id"]


def _upload(pid, filename, data, mime="application/pdf"):
    r = client.post(f"/profiles/{pid}/documents", files={"file": (filename, data, mime)})
    assert r.status_code == 200, r.text
    body = r.json()
    client.post(f"/jobs/{body['job_id']}/process")
    return body["document_id"]


def _doc_row(pid, doc_id):
    return next(d for d in client.get(f"/profiles/{pid}/documents").json() if d["id"] == doc_id)


def test_classifier_units():
    xr_text = "\n".join(XR_LINES)
    assert classify_document("2026-10-23 XR chest post port.pdf", xr_text) == "imaging"
    assert classify_document("report.pdf", xr_text) == "imaging"
    assert classify_document("labs.pdf", "\n".join(BMP_LINES)) == "lab"
    assert classify_document("labs.pdf", "\n".join(BMP_LINES), lab_lines=4) == "lab"
    assert classify_document("letter.txt", "Dear owner, your bill is due.") == "unknown"
    # Letterhead "US" and "MR" in body text are not modalities.
    assert classify_document("letter.txt", "MR# 12345\nMade in the US") == "unknown"
    # A lipid comment called Impression does not turn a parsed lab into imaging.
    lipid = "Lipid Panel\nCholesterol 180 mg/dL\nIMPRESSION: Desirable."
    assert classify_document("lipids.pdf", lipid, lab_lines=1) == "lab"


def test_extract_fields():
    [rep] = extract_imaging_reports("2026-10-23 XR chest post port.pdf", "\n".join(XR_LINES))
    assert rep["modality"] == "DX"
    assert rep["body_site"] == "chest"
    assert rep["laterality"] is None or rep["laterality"] == "right"
    assert rep["performed_at"] == "2026-10-23"
    assert rep["findings"].startswith("Right chest port")
    assert "Lungs are clear" in rep["findings"]
    assert rep["impression"].startswith("Port catheter tip")
    assert "Synthetic Radiologist" not in rep["impression"]
    assert rep["reporting_provider"].startswith("Synthetic Radiologist")
    assert rep["quote"].startswith("Port catheter tip")


def test_bare_headings_without_colons():
    text = "EXAM: MRI BRAIN\nFINDINGS\nNo mass.\nIMPRESSION\nNormal MRI of the brain.\n"
    [rep] = extract_imaging_reports("scan.pdf", text)
    assert rep["modality"] == "MR"
    assert rep["findings"] == "No mass."
    assert rep["impression"] == "Normal MRI of the brain."


def test_two_impressions_split_into_two_reports():
    text = "\n".join([
        "EXAM: CT HEAD WITHOUT CONTRAST",
        "FINDINGS: No hemorrhage.",
        "IMPRESSION: No acute intracranial abnormality.",
        "EXAM: XR LEFT KNEE 3 VIEWS",
        "FINDINGS: Mild joint space narrowing.",
        "IMPRESSION: Mild degenerative change.",
    ])
    reps = extract_imaging_reports("packet.pdf", text)
    assert [r["modality"] for r in reps] == ["CT", "DX"]
    assert reps[0]["body_site"] == "head"
    assert reps[1]["body_site"] == "knee"
    assert reps[1]["laterality"] == "left"


def test_xr_pdf_creates_imaging_proposal_not_lab_error():
    pid = _profile()
    doc_id = _upload(pid, "2026-10-23 XR chest post port.pdf", make_pdf(XR_LINES))
    row = _doc_row(pid, doc_id)
    assert row["job_status"] == "needs_review"
    assert not row["error"] or "No lab results found" not in row["error"]
    props = client.get(f"/profiles/{pid}/proposals").json()
    imaging = [p for p in props if p["type"] == "imaging_report"]
    assert len(imaging) == 1
    assert not [p for p in props if p["type"] == "lab_line"]
    p = imaging[0]
    assert p["document_id"] == doc_id
    assert p["payload"]["modality"] == "DX"
    assert "chest" in p["payload"]["body_site"]
    assert p["quote"].startswith("Port catheter tip")
    # Never auto-filed.
    db = TestingSessionLocal()
    assert db.query(ImagingReport).count() == 0
    db.close()


def test_accept_files_report_and_encounter_and_keeps_file():
    pid = _profile()
    doc_id = _upload(pid, "2026-10-23 XR chest post port.pdf", make_pdf(XR_LINES))
    prop = next(p for p in client.get(f"/profiles/{pid}/proposals").json() if p["type"] == "imaging_report")
    r = client.post(f"/proposals/{prop['id']}/accept")
    assert r.status_code == 200
    db = TestingSessionLocal()
    rep = db.query(ImagingReport).one()
    assert rep.profile_id == pid
    assert rep.source_document_id == doc_id
    assert rep.modality == "DX"
    assert rep.impression.startswith("Port catheter tip")
    enc = db.query(Encounter).filter(Encounter.id == rep.encounter_id).one()
    assert enc.type == EncounterType.imaging
    assert enc.start.date().isoformat() == "2026-10-23"
    assert db.query(Proposal).filter(Proposal.id == prop["id"]).one().status == ProposalStatus.accepted
    db.close()
    assert client.get(f"/documents/{doc_id}/file").status_code == 200
    lib = client.get(f"/profiles/{pid}/imaging-reports").json()
    assert lib["DX"][0]["source_document_id"] == doc_id


def test_reject_keeps_document():
    pid = _profile()
    doc_id = _upload(pid, "XR chest.pdf", make_pdf(XR_LINES))
    prop = client.get(f"/profiles/{pid}/proposals").json()[0]
    assert client.post(f"/proposals/{prop['id']}/reject").status_code == 200
    assert client.get(f"/profiles/{pid}/proposals").json() == []
    assert client.get(f"/documents/{doc_id}/file").status_code == 200
    db = TestingSessionLocal()
    assert db.query(ImagingReport).count() == 0
    db.close()


def test_bmp_pdf_still_auto_files_without_imaging():
    pid = _profile()
    doc_id = _upload(pid, "bmp.pdf", make_pdf(BMP_LINES))
    assert _doc_row(pid, doc_id)["job_status"] == "filed"
    assert client.get(f"/profiles/{pid}/proposals").json() == []
    db = TestingSessionLocal()
    assert db.query(LabReport).count() == 1
    db.close()


def test_labs_pdf_with_sodium_stays_lab_only():
    pid = _profile()
    _upload(pid, "labs.pdf", make_pdf(["Collected: 2024-03-15", "Sodium 140 mmol/L 136-145", "FooBar 1.2 mg/dL"]))
    props = client.get(f"/profiles/{pid}/proposals").json()
    assert props
    assert all(p["type"] == "lab_line" for p in props)


def test_unknown_document_gets_neutral_message():
    pid = _profile()
    doc_id = _upload(pid, "note.txt", b"Appointment reminder for next Tuesday.", "text/plain")
    row = _doc_row(pid, doc_id)
    assert row["job_status"] == "needs_review"
    assert "no imaging report" in row["error"].lower()
    assert not row["error"].startswith("No lab results found")


def test_imaging_named_file_without_text_gets_imaging_message():
    pid = _profile()
    doc_id = _upload(pid, "CT abdomen.txt", b"   ", "text/plain")
    row = _doc_row(pid, doc_id)
    assert row["job_status"] == "needs_review"
    assert "No lab results found" not in row["error"]
    assert "imaging" in row["error"].lower()
    assert client.get(f"/profiles/{pid}/proposals").json() == []


def test_manual_create_imaging_route():
    pid = _profile()
    doc_id = _upload(pid, "scan.txt", b"nothing useful here", "text/plain")
    r = client.post(f"/documents/{doc_id}/create-imaging", json={
        "modality": "US", "body_site": "abdomen", "performed_at": "2026-01-05",
        "findings": "Normal liver.", "impression": "Normal abdominal ultrasound.",
        "profile_id": 99999,
    })
    assert r.status_code == 200, r.text
    db = TestingSessionLocal()
    rep = db.query(ImagingReport).filter(ImagingReport.id == r.json()["imaging_report_id"]).one()
    assert rep.profile_id == pid  # body profile_id is ignored
    assert rep.source_document_id == doc_id
    assert rep.modality == "US"
    enc = db.query(Encounter).filter(Encounter.id == rep.encounter_id).one()
    assert enc.type == EncounterType.imaging
    db.close()
    assert client.post("/documents/999999/create-imaging", json={"modality": "DX"}).status_code == 404


def test_model_imaging_type_maps_to_imaging_report(monkeypatch):
    monkeypatch.setattr(procmod, "get_model_mode", lambda: "remote")
    monkeypatch.setattr(procmod, "call_model", lambda *a, **k: {"proposals": [
        {"type": "imaging_report", "modality": "DX", "impression": "Clear.", "quote": "Clear."},
    ]})
    pid = _profile()
    r = client.post(f"/profiles/{pid}/documents", files={"file": ("x.pdf", make_pdf(XR_LINES), "application/pdf")})
    db = TestingSessionLocal()
    from app.models import Job
    job = db.query(Job).filter(Job.id == r.json()["job_id"]).one()
    job.use_model = True
    db.commit()
    db.close()
    client.post(f"/jobs/{r.json()['job_id']}/process")
    props = client.get(f"/profiles/{pid}/proposals").json()
    assert [p["type"] for p in props] == ["imaging_report"]


def test_other_household_proposal_cannot_be_accepted():
    pid = _profile("Ours")
    _upload(pid, "XR chest.pdf", make_pdf(XR_LINES))

    db = TestingSessionLocal()
    h1 = db.query(Household).first()
    if not h1:
        h1 = Household(id=1, name="Home")
        db.add(h1)
        db.flush()
    db.add(User(household_id=h1.id, username="owner", password_hash=hash_password("x")))
    h2 = Household(name="Other house")
    db.add(h2)
    db.flush()
    other = Profile(household_id=h2.id, legal_name="Other")
    db.add(other)
    db.flush()
    other_doc = Document(
        profile_id=other.id, filename="secret.pdf", mime_type="application/pdf",
        sha256="abc", size_bytes=1, storage_path="x/secret.pdf",
    )
    db.add(other_doc)
    db.flush()
    foreign = Proposal(
        document_id=other_doc.id,
        profile_id=other.id,
        type=ProposalType.imaging_report,
        status=ProposalStatus.pending,
        payload=json.dumps({"modality": "DX", "impression": "x"}),
    )
    db.add(foreign)
    db.commit()
    foreign_id = foreign.id
    db.close()

    assert client.post(f"/proposals/{foreign_id}/accept").status_code == 404
    assert client.post(f"/proposals/{foreign_id}/reject").status_code == 404
    db = TestingSessionLocal()
    assert db.query(ImagingReport).count() == 0
    assert db.query(Proposal).filter(Proposal.id == foreign_id).one().status == ProposalStatus.pending
    db.close()
    ours = client.get(f"/profiles/{pid}/proposals").json()[0]
    assert client.post(f"/proposals/{ours['id']}/accept").status_code == 200
