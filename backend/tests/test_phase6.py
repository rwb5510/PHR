import os
os.environ["DATABASE_URL"] = "sqlite:////tmp/test_phase6.db"
os.environ["STORAGE_ROOT"] = "/tmp/phr_docs_test6"
os.environ["LLM_MODE"] = "off"
import shutil
shutil.rmtree("/tmp/phr_docs_test6", ignore_errors=True)
os.makedirs("/tmp/phr_docs_test6", exist_ok=True)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.main import app
from app.database import get_db
from app.models import Base

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
    db = TestingSessionLocal()
    for table in reversed(Base.metadata.sorted_tables):
        db.execute(table.delete())
    db.commit()
    db.close()
    from app.seed import load_analytes
    db = TestingSessionLocal()
    load_analytes(db)
    db.close()
    yield

def test_mode_off_no_model_call():
    from app.model_client import call_model, get_model_mode
    assert get_model_mode() == "off"
    result = call_model("Sodium 140", ["sodium"])
    assert result is None

def test_invalid_json_fails_extraction():
    from app.model_client import validate_model_output
    assert validate_model_output({"not": "valid"}) is False
    assert validate_model_output({"proposals": [{"type": "lab_line"}]}) is True
