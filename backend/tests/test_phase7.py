import os
os.environ["DATABASE_URL"] = "sqlite:////tmp/test_phase7.db"
os.environ["STORAGE_ROOT"] = "/tmp/phr_docs_test7"
import shutil
from io import BytesIO
shutil.rmtree("/tmp/phr_docs_test7", ignore_errors=True)
os.makedirs("/tmp/phr_docs_test7", exist_ok=True)

import pytest
import pydicom
from pydicom.dataset import Dataset, FileDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.main import app
from app.database import get_db
from app.models import Base

test_engine = create_engine("sqlite:////tmp/test_phase7.db", connect_args={"check_same_thread": False}, poolclass=StaticPool)
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
    shutil.rmtree("/tmp/phr_docs_test7", ignore_errors=True)
    os.makedirs("/tmp/phr_docs_test7", exist_ok=True)
    yield

def make_synthetic_dicom() -> bytes:
    file_meta = Dataset()
    file_meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.2"
    file_meta.MediaStorageSOPInstanceUID = generate_uid()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = FileDataset("synthetic.dcm", {}, file_meta=file_meta, preamble=b"\0" * 128)
    ds.StudyInstanceUID = "1.2.3.4.5.6.7.8.9"
    ds.SeriesInstanceUID = "1.2.3.4.5.6.7.8.10"
    ds.SOPInstanceUID = generate_uid()
    ds.SOPClassUID = "1.2.840.10008.5.1.4.1.1.2"
    ds.Modality = "CT"
    ds.StudyDescription = "Synthetic CT"
    ds.StudyDate = "20240501"
    ds.PatientName = "Test^Synthetic"
    buf = BytesIO()
    pydicom.dcmwrite(buf, ds)
    return buf.getvalue()

def test_synthetic_dicom_appears_under_profile():
    p = client.post("/profiles", json={"legal_name": "A"}).json()
    dcm = make_synthetic_dicom()
    r = client.post(f"/profiles/{p['id']}/dicom", files={"file": ("study.dcm", dcm, "application/dicom")})
    assert r.status_code == 200
    studies = client.get(f"/profiles/{p['id']}/studies").json()
    assert len(studies) == 1
    assert studies[0]["modality"] == "CT"
    assert studies[0]["study_instance_uid"] == "1.2.3.4.5.6.7.8.9"
    # Bytes not on document volume
    assert not any(f.endswith(".dcm") for f in os.listdir("/tmp/phr_docs_test7") if os.path.isfile(os.path.join("/tmp/phr_docs_test7", f)))

def test_link_survives_refresh():
    p = client.post("/profiles", json={"legal_name": "A"}).json()
    dcm = make_synthetic_dicom()
    client.post(f"/profiles/{p['id']}/dicom", files={"file": ("study.dcm", dcm, "application/dicom")})
    studies = client.get(f"/profiles/{p['id']}/studies").json()
    study_id = studies[0]["id"]
    enc = client.post("/encounters", json={"profile_id": p["id"], "type": "imaging", "start": "2024-05-01T00:00:00"}).json()
    rep = client.post("/imaging-reports", json={"profile_id": p["id"], "encounter_id": enc["id"], "modality": "CT", "impression": "Normal"}).json()
    client.post(f"/studies/{study_id}/link", json={"imaging_report_id": rep["id"]})
    # Refresh
    studies2 = client.get(f"/profiles/{p['id']}/studies").json()
    assert any(l["imaging_report_id"] == rep["id"] for l in studies2[0]["links"])

def test_viewer_requires_session():
    r = client.get("/viewer/1.2.3.4.5.6.7.8.9")
    assert r.status_code == 401
    r2 = client.get("/viewer/1.2.3.4.5.6.7.8.9", cookies={"session": "test"})
    # May 404 if study not present, but not 401
    assert r2.status_code != 401

def test_second_profile_cannot_see_study():
    p1 = client.post("/profiles", json={"legal_name": "A"}).json()
    p2 = client.post("/profiles", json={"legal_name": "B"}).json()
    dcm = make_synthetic_dicom()
    client.post(f"/profiles/{p1['id']}/dicom", files={"file": ("study.dcm", dcm, "application/dicom")})
    studies_b = client.get(f"/profiles/{p2['id']}/studies").json()
    assert len(studies_b) == 0

def test_orthanc_ports_unpublished():
    # Compose file check: no ports published for orthanc
    with open("../docker-compose.yml") as f:
        text = f.read()
    assert "orthancteam/orthanc:24.10.2" in text
    # No "8042:8042" or "4242:4242" publish
    assert "8042:8042" not in text
    assert "4242:4242" not in text
