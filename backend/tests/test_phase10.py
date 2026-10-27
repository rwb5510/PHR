import os

os.environ["DATABASE_URL"] = "sqlite:////tmp/test_phase10.db"
os.environ["STORAGE_ROOT"] = "/tmp/phr_docs_test10"
os.environ.setdefault("AUTH_DISABLED", "1")

import shutil

shutil.rmtree("/tmp/phr_docs_test10", ignore_errors=True)
os.makedirs("/tmp/phr_docs_test10", exist_ok=True)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from io import BytesIO
from PIL import Image
from reportlab.pdfgen import canvas

from app.main import app
from app import main as mainmod
from app.database import get_db
from app.models import Base
from app.documents import content_disposition_type, resolve_media_type

STORAGE = "/tmp/phr_docs_test10"
test_engine = create_engine(
    "sqlite:////tmp/test_phase10.db",
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
    shutil.rmtree(STORAGE, ignore_errors=True)
    os.makedirs(STORAGE, exist_ok=True)
    yield


def make_pdf() -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(50, 750, "Collected: 2024-05-01")
    c.save()
    return buf.getvalue()


def make_image(fmt: str) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (20, 20), "white").save(buf, format=fmt)
    return buf.getvalue()


def upload(name: str, data: bytes, client_mime: str) -> int:
    pid = client.post("/profiles", json={"legal_name": "Test"}).json()["id"]
    r = client.post(f"/profiles/{pid}/documents", files={"file": (name, data, client_mime)})
    assert r.status_code == 200
    return r.json()["document_id"]


def fetch(doc_id: int):
    fr = client.get(f"/documents/{doc_id}/file")
    assert fr.status_code == 200
    disp = (fr.headers.get("content-disposition") or "").lower()
    ctype = (fr.headers.get("content-type") or "").lower()
    return fr, disp, ctype


@pytest.mark.parametrize(
    "name,data,client_mime,expected_type",
    [
        ("lab.pdf", make_pdf(), "application/pdf", "application/pdf"),
        ("scan.png", make_image("PNG"), "image/png", "image/png"),
        ("photo.jpg", make_image("JPEG"), "image/jpeg", "image/jpeg"),
        ("note.txt", b"Sodium 140 mmol/L\n", "text/plain", "text/plain"),
        ("note.md", b"# Visit\n", "application/octet-stream", "text/plain"),
    ],
)
def test_previewable_files_open_inline(name, data, client_mime, expected_type):
    doc_id = upload(name, data, client_mime)
    fr, disp, ctype = fetch(doc_id)
    assert fr.content == data
    assert disp.startswith("inline")
    assert "attachment" not in disp
    # Keep the original name so Save As from the viewer is sensible.
    assert name in disp
    assert ctype.startswith(expected_type)


def test_suffix_overrides_lying_client_mime():
    doc_id = upload("lab.pdf", make_pdf(), "text/plain")
    _, disp, ctype = fetch(doc_id)
    assert ctype.startswith("application/pdf")
    assert disp.startswith("inline")


def test_text_types_carry_utf8_charset():
    doc_id = upload("note.txt", "Größe 1.70 m\n".encode("utf-8"), "")
    _, _, ctype = fetch(doc_id)
    assert ctype.startswith("text/plain")
    assert "charset=utf-8" in ctype


def test_media_type_matrix():
    assert resolve_media_type("a.xml", None) == "application/xml"
    assert resolve_media_type("a.tiff", "application/octet-stream") == "image/tiff"
    assert resolve_media_type("a.csv", None).startswith("text/csv")
    assert resolve_media_type("a.json", None) == "application/json"
    assert resolve_media_type("a.bin", "image/png") == "image/png"
    assert resolve_media_type("noext", None) == "application/octet-stream"
    for previewable in ("application/xml", "application/json", "text/csv; charset=utf-8", "image/tiff"):
        assert content_disposition_type(previewable) == "inline"
    assert content_disposition_type(resolve_media_type("a.xls", None)) == "attachment"
    assert content_disposition_type(resolve_media_type("a.xlsx", None)) == "attachment"
    assert content_disposition_type("application/octet-stream") == "attachment"


def test_ccd_export_stays_attachment():
    pid = client.post("/profiles", json={"legal_name": "Test"}).json()["id"]
    r = client.get(f"/profiles/{pid}/export-ccd")
    assert r.status_code == 200
    assert (r.headers.get("content-disposition") or "").lower().startswith("attachment")
