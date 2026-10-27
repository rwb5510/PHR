import os

os.environ["DATABASE_URL"] = "sqlite:////tmp/test_phase9.db"
os.environ["STORAGE_ROOT"] = "/tmp/phr_docs_test9"
os.environ.setdefault("AUTH_DISABLED", "1")

import shutil

shutil.rmtree("/tmp/phr_docs_test9", ignore_errors=True)
os.makedirs("/tmp/phr_docs_test9", exist_ok=True)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from io import BytesIO
from reportlab.pdfgen import canvas

from app.main import app
from app import main as mainmod
from app.database import get_db
from app.models import Base, Document, Household, Profile, User
from app.auth import hash_password
from app.documents import content_disposition_type, resolve_media_type


def test_previewable_types_resolve_inline():
    assert resolve_media_type("lab.pdf", "application/octet-stream") == "application/pdf"
    assert content_disposition_type("application/pdf") == "inline"
    assert content_disposition_type("image/png") == "inline"
    assert content_disposition_type("text/plain; charset=utf-8") == "inline"
    assert content_disposition_type("application/vnd.ms-excel") == "attachment"

STORAGE = "/tmp/phr_docs_test9"
test_engine = create_engine(
    "sqlite:////tmp/test_phase9.db",
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
    mainmod.STORAGE_ROOT = STORAGE
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    from app.seed import load_analytes

    load_analytes(db)
    db.close()
    shutil.rmtree(STORAGE, ignore_errors=True)
    os.makedirs(STORAGE, exist_ok=True)
    yield


def make_unknown_lab_pdf() -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(50, 750, "Collected: 2024-05-01")
    c.drawString(50, 730, "FooBar 1.2 mg/dL")
    c.save()
    return buf.getvalue()


def _upload_unknown_lab():
    p = client.post("/profiles", json={"legal_name": "Test"}).json()
    pid = p["id"]
    pdf = make_unknown_lab_pdf()
    r = client.post(f"/profiles/{pid}/documents", files={"file": ("unk.pdf", pdf, "application/pdf")})
    assert r.status_code == 200
    data = r.json()
    client.post(f"/jobs/{data['job_id']}/process")
    return pid, data["document_id"]


def test_file_served_inline_with_pdf_bytes():
    pid, doc_id = _upload_unknown_lab()
    fr = client.get(f"/documents/{doc_id}/file")
    assert fr.status_code == 200
    assert fr.content.startswith(b"%PDF")
    disp = (fr.headers.get("content-disposition") or "").lower()
    assert "inline" in disp
    assert "attachment" not in disp
    assert (fr.headers.get("content-type") or "").startswith("application/pdf")
    head = client.head(f"/documents/{doc_id}/file")
    assert head.status_code == 200
    assert "inline" in (head.headers.get("content-disposition") or "").lower()
    props = client.get(f"/profiles/{pid}/proposals").json()
    assert len(props) >= 1
    assert props[0]["document_id"] == doc_id
    assert props[0].get("quote")


def test_extracted_text_contains_proposal_quote():
    pid, doc_id = _upload_unknown_lab()
    props = client.get(f"/profiles/{pid}/proposals").json()
    quote = next((pr["quote"] for pr in props if pr.get("quote")), None)
    assert quote
    text_r = client.get(f"/documents/{doc_id}/text")
    assert text_r.status_code == 200
    body = text_r.json()
    extracted = body.get("extracted_text") or ""
    assert quote.strip()[:12].lower() in extracted.lower() or "foobar" in extracted.lower()
    assert body.get("filename") == "unk.pdf"
    assert "pdf" in (body.get("mime_type") or "").lower()


def test_proposal_list_includes_document_id_and_quote():
    pid, doc_id = _upload_unknown_lab()
    props = client.get(f"/profiles/{pid}/proposals").json()
    assert props
    for pr in props:
        assert "document_id" in pr
        assert pr["document_id"] == doc_id
        assert "quote" in pr


def test_missing_document_is_404():
    client.post("/profiles", json={"legal_name": "Test"})
    assert client.get("/documents/999999/file").status_code == 404
    assert client.get("/documents/999999/text").status_code == 404


def test_missing_file_on_disk_is_404():
    pid, doc_id = _upload_unknown_lab()
    db = TestingSessionLocal()
    doc = db.query(Document).filter(Document.id == doc_id).first()
    path = os.path.join(STORAGE, doc.storage_path)
    os.remove(path)
    db.close()
    r = client.get(f"/documents/{doc_id}/file")
    assert r.status_code == 404
    assert r.json()["detail"] == "file missing"


def test_other_household_document_is_404():
    home = client.post("/profiles", json={"legal_name": "Ours"}).json()
    pdf = make_unknown_lab_pdf()
    ours = client.post(
        f"/profiles/{home['id']}/documents",
        files={"file": ("ours.pdf", pdf, "application/pdf")},
    ).json()
    client.post(f"/jobs/{ours['job_id']}/process")

    db = TestingSessionLocal()
    h1 = db.query(Household).first()
    if not h1:
        h1 = Household(name="Home")
        db.add(h1)
        db.flush()
    db.add(User(household_id=h1.id, username="owner", password_hash=hash_password("x")))
    h2 = Household(name="Other house")
    db.add(h2)
    db.flush()
    other_profile = Profile(household_id=h2.id, legal_name="Other")
    db.add(other_profile)
    db.flush()
    rel = f"{other_profile.id}/secret.pdf"
    full = os.path.join(STORAGE, rel)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "wb") as f:
        f.write(pdf)
    secret = Document(
        profile_id=other_profile.id,
        filename="secret.pdf",
        mime_type="application/pdf",
        sha256="abc",
        size_bytes=len(pdf),
        storage_path=rel,
        extracted_text="secret line",
    )
    db.add(secret)
    db.commit()
    secret_id = secret.id
    other_pid = other_profile.id
    db.close()

    assert client.get(f"/documents/{secret_id}/file").status_code == 404
    assert client.get(f"/documents/{secret_id}/text").status_code == 404
    assert client.get(f"/profiles/{other_pid}/proposals").status_code == 404
    ours_file = client.get(f"/documents/{ours['document_id']}/file")
    assert ours_file.status_code == 200
    ours_props = client.get(f"/profiles/{home['id']}/proposals")
    assert ours_props.status_code == 200


def test_proposals_are_profile_filtered():
    a = client.post("/profiles", json={"legal_name": "A"}).json()
    b = client.post("/profiles", json={"legal_name": "B"}).json()
    pdf = make_unknown_lab_pdf()
    ra = client.post(f"/profiles/{a['id']}/documents", files={"file": ("a.pdf", pdf, "application/pdf")})
    client.post(f"/jobs/{ra.json()['job_id']}/process")
    props_a = client.get(f"/profiles/{a['id']}/proposals").json()
    props_b = client.get(f"/profiles/{b['id']}/proposals").json()
    assert len(props_a) >= 1
    assert props_b == []
    assert all(pr["document_id"] == ra.json()["document_id"] for pr in props_a)
