import os
os.environ["DATABASE_URL"] = "sqlite:////tmp/test_phase6.db"
os.environ["STORAGE_ROOT"] = "/tmp/phr_docs_test6"
os.environ["LLM_MODE"] = "off"
import shutil
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
shutil.rmtree("/tmp/phr_docs_test6", ignore_errors=True)
os.makedirs("/tmp/phr_docs_test6", exist_ok=True)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.main import app
from app.database import get_db
from app.models import Base, LabReport
from app.model_client import update_settings, get_model_mode

test_engine = create_engine("sqlite:////tmp/test_phase6.db", connect_args={"check_same_thread": False}, poolclass=StaticPool)
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
    update_settings(mode="off", llm_autofile=False)
    yield

class FakeHandler(BaseHTTPRequestHandler):
    response_body = b""
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(self.response_body)
    def log_message(self, format, *args):
        pass

def start_fake(body: dict):
    FakeHandler.response_body = json.dumps({
        "choices": [{"message": {"content": json.dumps(body)}}]
    }).encode()
    server = HTTPServer(("127.0.0.1", 0), FakeHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, f"http://127.0.0.1:{server.server_port}"

def test_mode_off_no_outbound():
    assert get_model_mode() == "off"
    p = client.post("/profiles", json={"legal_name": "T"}).json()
    r = client.post(f"/profiles/{p['id']}/documents", files={"file": ("t.txt", b"Sodium 140 mmol/L", "text/plain")}, data={"use_model": "true"})
    data = r.json()
    client.post(f"/jobs/{data['job_id']}/process")
    # No model call happened; Phase 4 path still works
    assert client.get(f"/documents/{data['document_id']}/file").status_code == 200

def test_fake_server_creates_inbox_not_chart():
    body = {"proposals": [{"type": "lab_line", "original_name": "Sodium", "value_text": "140", "unit_original": "mmol/L", "quote": "Sodium 140"}]}
    server, url = start_fake(body)
    try:
        update_settings(mode="local", base_url=url, model="fake", llm_autofile=False)
        p = client.post("/profiles", json={"legal_name": "T"}).json()
        r = client.post(f"/profiles/{p['id']}/documents", files={"file": ("t.txt", b"text", "text/plain")}, data={"use_model": "true"})
        data = r.json()
        client.post(f"/jobs/{data['job_id']}/process")
        props = client.get(f"/profiles/{p['id']}/proposals").json()
        assert any(pr.get("from_model") for pr in props)
        labs = client.get(f"/profiles/{p['id']}/lab-reports").json()
        assert len(labs) == 0
    finally:
        server.shutdown()

def test_invalid_json_fails_extraction_keeps_file():
    server, url = start_fake({"not": "valid"})
    # Override to return non-JSON content
    FakeHandler.response_body = json.dumps({
        "choices": [{"message": {"content": "this is not json"}}]
    }).encode()
    try:
        update_settings(mode="local", base_url=url, model="fake", llm_autofile=False)
        p = client.post("/profiles", json={"legal_name": "T"}).json()
        r = client.post(f"/profiles/{p['id']}/documents", files={"file": ("t.txt", b"text", "text/plain")}, data={"use_model": "true"})
        data = r.json()
        pr = client.post(f"/jobs/{data['job_id']}/process")
        assert pr.json()["status"] == "failed"
        assert client.get(f"/documents/{data['document_id']}/file").status_code == 200
    finally:
        server.shutdown()

def test_autofile_on_does_not_file_impression():
    body = {"proposals": [{"type": "impression", "is_impression": True, "quote": "Normal study"}]}
    server, url = start_fake(body)
    try:
        update_settings(mode="local", base_url=url, model="fake", llm_autofile=True)
        p = client.post("/profiles", json={"legal_name": "T"}).json()
        r = client.post(f"/profiles/{p['id']}/documents", files={"file": ("t.txt", b"text", "text/plain")}, data={"use_model": "true"})
        data = r.json()
        client.post(f"/jobs/{data['job_id']}/process")
        labs = client.get(f"/profiles/{p['id']}/lab-reports").json()
        assert len(labs) == 0
        props = client.get(f"/profiles/{p['id']}/proposals").json()
        assert any(pr.get("from_model") for pr in props)
    finally:
        server.shutdown()
