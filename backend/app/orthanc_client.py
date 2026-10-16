"""Orthanc client. Streams DICOM bytes. No local pixel copy. Ports unpublished."""
import os
import httpx
from typing import Optional, Dict, Any

ORTHANC_URL = os.getenv("ORTHANC_URL", "http://orthanc:8042")
ORTHANC_USER = os.getenv("ORTHANC_USER", "orthanc")
ORTHANC_PASS = os.getenv("ORTHANC_PASS", "orthanc")

def upload_instance(data: bytes) -> Dict[str, Any]:
    """POST raw DICOM to Orthanc /instances. Returns Orthanc response JSON."""
    with httpx.Client(timeout=60.0, auth=(ORTHANC_USER, ORTHANC_PASS)) as client:
        r = client.post(f"{ORTHANC_URL}/instances", content=data, headers={"Content-Type": "application/dicom"})
        r.raise_for_status()
        return r.json()

def delete_study(orthanc_id: str) -> None:
    with httpx.Client(timeout=30.0, auth=(ORTHANC_USER, ORTHANC_PASS)) as client:
        client.delete(f"{ORTHANC_URL}/studies/{orthanc_id}")

def get_study(orthanc_id: str) -> Optional[Dict]:
    try:
        with httpx.Client(timeout=30.0, auth=(ORTHANC_USER, ORTHANC_PASS)) as client:
            r = client.get(f"{ORTHANC_URL}/studies/{orthanc_id}")
            if r.status_code == 200:
                return r.json()
    except Exception:
        pass
    return None
