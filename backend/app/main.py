from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import Response, JSONResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, date
import hashlib
import os
import json
import uuid
import zipfile
import time
from io import BytesIO
import pydicom
import httpx
from .database import get_db, engine, SessionLocal
from .models import (
    Base, Profile, Encounter, Order, OrderResultLink, LabReport, LabComponent,
    CanonicalAnalyte, ImagingReport, OrderStatus, Document, Job, JobStatus,
    Proposal, ProposalStatus, ProposalType, EncounterType,
    Problem, Allergy, Medication, Immunization, Procedure, Vital,
    SocialHistory, FamilyHistory, MedicalEquipment,
    DicomStudy, DicomSeries, StudyLink, Appointment
)
from .orthanc_client import upload_instance, delete_study
from .schemas import (
    ProfileCreate, ProfileOut, EncounterCreate, EncounterOut,
    OrderCreate, OrderOut, LinkResult, LabReportCreate, LabReportOut,
    ImagingReportCreate, ImagingReportOut, TrendPoint
)
from .lab_matching import (
    match_analyte, compute_normalized, compute_abnormal_flag, is_plain_number
)
from .seed import load_analytes
from .extraction import MAX_UPLOAD_BYTES
from .processor import process_job, reset_document_outputs
from .ccda import build_ccd
from .model_client import get_settings, update_settings, get_model_mode
from .auth import AUTH_DISABLED, bootstrap, load_session, router as auth_router
from .chart_routes import router as chart_router
from .panel_catalog import router as panel_catalog_router, seed_all_empty_households
from .documents import (
    document_in_household,
    file_response_for_document,
    profile_in_household,
    session_household_id,
)

app = FastAPI(title="Household PHR")
app.include_router(auth_router)
app.include_router(chart_router)
app.include_router(panel_catalog_router)

STORAGE_ROOT = os.getenv("STORAGE_ROOT", "/data/documents")
os.makedirs(STORAGE_ROOT, exist_ok=True)

PUBLIC_PATHS = {"/health", "/login", "/logout", "/docs", "/openapi.json", "/redoc"}


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if AUTH_DISABLED:
        return await call_next(request)
    path = request.url.path
    if path in PUBLIC_PATHS or path.startswith("/docs") or path.startswith("/redoc") or path.startswith("/openapi"):
        return await call_next(request)
    token = request.cookies.get("session")
    if path.startswith("/viewer/"):
        if not token:
            return JSONResponse({"detail": "session required"}, status_code=401)
        return await call_next(request)
    db = SessionLocal()
    try:
        sess = load_session(db, token)
        if not sess or not sess.user:
            return JSONResponse({"detail": "login required"}, status_code=401)
        user = sess.user
        request.state.user = type("UserView", (), {
            "id": user.id,
            "household_id": user.household_id,
            "username": user.username,
            "password_hash": user.password_hash,
            "totp_enabled": user.totp_enabled,
            "totp_secret": user.totp_secret,
        })()
        request.state.auth_session = type("SessView", (), {
            "id": sess.id,
            "token": sess.token,
            "user_id": sess.user_id,
            "active_profile_id": sess.active_profile_id,
        })()
    finally:
        db.close()
    return await call_next(request)

@app.on_event("startup")
def startup():
    last_err = None
    for _ in range(30):
        try:
            Base.metadata.create_all(bind=engine)
            last_err = None
            break
        except Exception as exc:
            last_err = exc
            time.sleep(1)
    if last_err:
        raise last_err
    load_analytes()
    os.makedirs(STORAGE_ROOT, exist_ok=True)
    db = SessionLocal()
    try:
        bootstrap(db)
        seed_all_empty_households(db)
    finally:
        db.close()

@app.get("/health")
def health():
    orthanc_ok = False
    try:
        from .orthanc_client import ORTHANC_URL, ORTHANC_USER, ORTHANC_PASS
        r = httpx.get(f"{ORTHANC_URL}/system", auth=(ORTHANC_USER, ORTHANC_PASS), timeout=2.0)
        orthanc_ok = r.status_code == 200
    except Exception:
        pass
    return {"status": "ok", "orthanc": orthanc_ok}

# Profiles
@app.post("/profiles", response_model=ProfileOut)
def create_profile(p: ProfileCreate, request: Request, db: Session = Depends(get_db)):
    hid = 1
    user = getattr(request.state, "user", None)
    if user is not None:
        hid = user.household_id
    obj = Profile(household_id=hid, **p.dict())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj

@app.get("/profiles", response_model=List[ProfileOut])
def list_profiles(request: Request, db: Session = Depends(get_db)):
    q = db.query(Profile)
    user = getattr(request.state, "user", None)
    if user is not None:
        q = q.filter(Profile.household_id == user.household_id)
    return q.all()

# Encounters
@app.post("/encounters", response_model=EncounterOut)
def create_encounter(e: EncounterCreate, db: Session = Depends(get_db)):
    obj = Encounter(**e.dict())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj

@app.get("/profiles/{profile_id}/encounters", response_model=List[EncounterOut])
def list_encounters(profile_id: int, db: Session = Depends(get_db)):
    return db.query(Encounter).filter(Encounter.profile_id == profile_id).all()

@app.get("/encounters/{encounter_id}", response_model=EncounterOut)
def get_encounter(encounter_id: int, db: Session = Depends(get_db)):
    enc = db.query(Encounter).filter(Encounter.id == encounter_id).first()
    if not enc:
        raise HTTPException(404)
    return enc

# Orders
@app.post("/orders", response_model=OrderOut)
def create_order(o: OrderCreate, db: Session = Depends(get_db)):
    enc = db.query(Encounter).filter(Encounter.id == o.ordering_encounter_id, Encounter.profile_id == o.profile_id).first()
    if not enc:
        raise HTTPException(400, "ordering encounter not found or wrong profile")
    obj = Order(**o.dict(), status=OrderStatus.ordered)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj

@app.get("/encounters/{encounter_id}/orders", response_model=List[OrderOut])
def orders_for_encounter(encounter_id: int, db: Session = Depends(get_db)):
    return db.query(Order).filter(Order.ordering_encounter_id == encounter_id).all()

@app.post("/orders/{order_id}/link-result")
def link_result(order_id: int, body: LinkResult, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404)
    result_enc = db.query(Encounter).filter(Encounter.id == body.result_encounter_id, Encounter.profile_id == order.profile_id).first()
    if not result_enc:
        raise HTTPException(400, "result encounter not found or wrong profile")
    link = OrderResultLink(order_id=order_id, result_encounter_id=body.result_encounter_id)
    db.add(link)
    order.status = OrderStatus.completed
    db.commit()
    return {"ok": True, "status": "completed"}

@app.get("/encounters/{encounter_id}/fulfilling-orders")
def fulfilling_orders(encounter_id: int, db: Session = Depends(get_db)):
    links = db.query(OrderResultLink).filter(OrderResultLink.result_encounter_id == encounter_id).all()
    return [{"order_id": l.order_id, "name": l.order.name} for l in links]

# Labs
@app.post("/lab-reports", response_model=LabReportOut)
def create_lab_report(r: LabReportCreate, db: Session = Depends(get_db)):
    enc = db.query(Encounter).filter(Encounter.id == r.encounter_id, Encounter.profile_id == r.profile_id).first()
    if not enc:
        raise HTTPException(400, "encounter not found")
    report = LabReport(
        profile_id=r.profile_id,
        encounter_id=r.encounter_id,
        order_id=r.order_id,
        collection_time=r.collection_time,
        reported_time=r.reported_time,
        performing_lab=r.performing_lab,
        specimen=r.specimen,
        panel_name=r.panel_name,
        source_document_id=getattr(r, "source_document_id", None),
    )
    db.add(report)
    db.flush()
    analytes = db.query(CanonicalAnalyte).all()
    for seq, c in enumerate(r.components):
        value_num = None
        if is_plain_number(c.value_text):
            value_num = float(c.value_text.strip())
        matched = match_analyte(c.original_name, analytes)
        norm_val, norm_unit = None, None
        if matched and value_num is not None:
            norm_val, norm_unit = compute_normalized(matched, value_num, c.unit_original)
        flag = compute_abnormal_flag(value_num, c.ref_low, c.ref_high, c.printed_flag)
        comp = LabComponent(
            lab_report_id=report.id,
            sequence=seq,
            original_name=c.original_name,
            value_text=c.value_text,
            value_numeric=value_num,
            unit_original=c.unit_original,
            ref_low=c.ref_low,
            ref_high=c.ref_high,
            ref_text=c.ref_text,
            abnormal_flag=flag,
            canonical_analyte_id=matched.id if matched else None,
            normalized_value=norm_val,
            normalized_unit=norm_unit,
        )
        db.add(comp)
    db.commit()
    db.refresh(report)
    return report

@app.get("/lab-reports/{report_id}", response_model=LabReportOut)
def get_lab_report(report_id: int, db: Session = Depends(get_db)):
    report = db.query(LabReport).filter(LabReport.id == report_id).first()
    if not report:
        raise HTTPException(404)
    return report

@app.get("/profiles/{profile_id}/lab-reports", response_model=List[LabReportOut])
def list_lab_reports(profile_id: int, db: Session = Depends(get_db)):
    return db.query(LabReport).filter(LabReport.profile_id == profile_id).all()

@app.get("/profiles/{profile_id}/trends/{analyte_name}")
def analyte_trend(profile_id: int, analyte_name: str, db: Session = Depends(get_db)):
    analyte = db.query(CanonicalAnalyte).filter(CanonicalAnalyte.name.ilike(analyte_name)).first()
    if not analyte:
        raise HTTPException(404, "analyte not found")
    comps = (
        db.query(LabComponent)
        .join(LabReport)
        .filter(LabReport.profile_id == profile_id, LabComponent.canonical_analyte_id == analyte.id)
        .order_by(LabReport.collection_time)
        .all()
    )
    points = []
    for c in comps:
        points.append({
            "collected_at": c.report.collection_time.isoformat() if c.report.collection_time else None,
            "original_value": c.value_text,
            "original_unit": c.unit_original,
            "ref_low": c.ref_low,
            "ref_high": c.ref_high,
            "ref_text": c.ref_text,
            "normalized_value": c.normalized_value,
            "normalized_unit": c.normalized_unit,
            "panel_name": c.report.panel_name,
            "value_numeric": c.value_numeric,
            "source_document_id": c.report.source_document_id,
        })
    return {"analyte": analyte.name, "canonical_unit": analyte.ucum, "points": points}

# Imaging
@app.post("/imaging-reports", response_model=ImagingReportOut)
def create_imaging(i: ImagingReportCreate, db: Session = Depends(get_db)):
    obj = ImagingReport(**i.dict())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj

@app.get("/profiles/{profile_id}/imaging-reports")
def list_imaging(profile_id: int, db: Session = Depends(get_db)):
    reports = db.query(ImagingReport).filter(ImagingReport.profile_id == profile_id).order_by(ImagingReport.performed_at.desc()).all()
    groups = {}
    for r in reports:
        groups.setdefault(r.modality, []).append({
            "id": r.id, "performed_at": r.performed_at, "body_site": r.body_site,
            "impression": r.impression, "facility": r.facility,
            "source_document_id": r.source_document_id
        })
    return groups

# Documents
@app.get("/settings")
def get_settings_endpoint():
    s = get_settings()
    s["mode_off"] = s["mode"] == "off"
    s["llm_autofile_warning"] = "Unsafe: model proposals may auto-file. Default off."
    return s

@app.post("/settings")
def update_settings_endpoint(body: dict):
    return update_settings(
        mode=body.get("mode"),
        base_url=body.get("base_url"),
        model=body.get("model"),
        llm_autofile=body.get("llm_autofile"),
    )

@app.post("/profiles/{profile_id}/documents")
async def upload_document(
    profile_id: int,
    file: UploadFile = File(...),
    use_model: bool = Form(False),
    db: Session = Depends(get_db)
):
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(404, "profile not found")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"File exceeds {MAX_UPLOAD_BYTES // (1024*1024)} MB limit")
    sha = hashlib.sha256(data).hexdigest()
    existing = db.query(Document).filter(Document.profile_id == profile_id, Document.sha256 == sha).first()
    if existing:
        return {
            "duplicate": True,
            "warning": "This file is already stored. Open Documents and press Reprocess to parse it again.",
            "document_id": existing.id,
        }
    # store
    rel_path = f"{profile_id}/{uuid.uuid4().hex}_{file.filename}"
    full = os.path.join(STORAGE_ROOT, rel_path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "wb") as f:
        f.write(data)
    doc = Document(
        profile_id=profile_id,
        filename=file.filename or "upload",
        mime_type=file.content_type or "application/octet-stream",
        sha256=sha,
        size_bytes=len(data),
        storage_path=rel_path,
    )
    db.add(doc)
    db.flush()
    job = Job(document_id=doc.id, status=JobStatus.queued, use_model=use_model and get_model_mode() != "off")
    db.add(job)
    db.commit()
    db.refresh(doc)
    db.refresh(job)
    return {"document_id": doc.id, "job_id": job.id, "status": "queued"}

@app.get("/profiles/{profile_id}/documents")
def list_documents(profile_id: int, db: Session = Depends(get_db)):
    docs = db.query(Document).filter(Document.profile_id == profile_id).order_by(Document.created_at.desc()).all()
    out = []
    for d in docs:
        job = db.query(Job).filter(Job.document_id == d.id).order_by(Job.id.desc()).first()
        out.append({
            "id": d.id,
            "filename": d.filename,
            "mime_type": d.mime_type,
            "size_bytes": d.size_bytes,
            "page_count": d.page_count,
            "ocr_used": d.ocr_used,
            "created_at": d.created_at,
            "job_status": job.status.value if job else None,
            "job_id": job.id if job else None,
            "error": job.error_message if job else None,
        })
    return out

@app.api_route("/documents/{document_id}/file", methods=["GET", "HEAD"])
def get_document_file(document_id: int, request: Request, db: Session = Depends(get_db)):
    hid = session_household_id(request, db)
    doc = document_in_household(db, document_id, hid)
    path = os.path.join(STORAGE_ROOT, doc.storage_path)
    if not os.path.exists(path):
        raise HTTPException(404, "file missing")
    return file_response_for_document(path, doc)

@app.get("/documents/{document_id}/text")
def get_document_text(document_id: int, request: Request, db: Session = Depends(get_db)):
    hid = session_household_id(request, db)
    doc = document_in_household(db, document_id, hid)
    return {
        "extracted_text": doc.extracted_text,
        "ocr_used": doc.ocr_used,
        "page_count": doc.page_count,
        "filename": doc.filename,
        "mime_type": doc.mime_type,
    }

@app.post("/jobs/{job_id}/process")
def process_job_endpoint(job_id: int, db: Session = Depends(get_db)):
    """Sync process for tests / manual trigger. Worker uses the same function."""
    process_job(db, job_id)
    job = db.query(Job).filter(Job.id == job_id).first()
    return {"status": job.status.value if job else None}

@app.post("/jobs/{job_id}/retry")
def retry_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(404)
    if job.status not in (
        JobStatus.failed,
        JobStatus.processing,
        JobStatus.filed,
        JobStatus.needs_review,
    ):
        raise HTTPException(400, "only finished, failed, or stuck jobs can be reprocessed")
    reset_document_outputs(db, job.document_id)
    job.status = JobStatus.queued
    job.retry_count += 1
    job.error_message = None
    db.commit()
    return {"status": "queued"}

@app.get("/profiles/{profile_id}/proposals")
def list_proposals(profile_id: int, request: Request, db: Session = Depends(get_db)):
    hid = session_household_id(request, db)
    profile_in_household(db, profile_id, hid)
    props = db.query(Proposal).filter(
        Proposal.profile_id == profile_id,
        Proposal.status == ProposalStatus.pending
    ).order_by(Proposal.created_at.desc()).all()
    out = []
    for p in props:
        out.append({
            "id": p.id,
            "document_id": p.document_id,
            "type": p.type.value,
            "status": p.status.value,
            "payload": json.loads(p.payload),
            "quote": p.quote,
            "from_model": p.from_model,
            "created_at": p.created_at,
        })
    return out

@app.post("/proposals/{proposal_id}/accept")
def accept_proposal(proposal_id: int, db: Session = Depends(get_db)):
    prop = db.query(Proposal).filter(Proposal.id == proposal_id).first()
    if not prop or prop.status != ProposalStatus.pending:
        raise HTTPException(404)
    payload = json.loads(prop.payload)
    # For lab_line, create report + component if not already
    if prop.type == ProposalType.lab_line:
        coll = payload.get("collection_date")
        coll_dt = datetime.fromisoformat(coll) if coll else None
        panel_name = payload.get("panel_name") or "Reviewed Panel"
        doc_reports = db.query(LabReport).filter(
            LabReport.source_document_id == prop.document_id,
            LabReport.profile_id == prop.profile_id,
        )
        # Each printed panel keeps its own report; a CBC line never lands on the CMP.
        report = doc_reports.filter(LabReport.panel_name == panel_name).first()
        if not report:
            # Panels drawn together share one lab encounter. Without a printed date
            # the whole file is one draw, so any report on it gives the encounter.
            sibling = (
                doc_reports.filter(LabReport.collection_time == coll_dt).first()
                if coll_dt else doc_reports.first()
            )
            if sibling:
                enc_id = sibling.encounter_id
                coll_dt = coll_dt or sibling.collection_time
            else:
                coll_dt = coll_dt or datetime.utcnow()
                enc = Encounter(
                    profile_id=prop.profile_id,
                    type=EncounterType.lab,
                    start=coll_dt,
                    reason="Accepted from review",
                )
                db.add(enc)
                db.flush()
                enc_id = enc.id
            report = LabReport(
                profile_id=prop.profile_id,
                encounter_id=enc_id,
                collection_time=coll_dt,
                panel_name=panel_name,
                source_document_id=prop.document_id,
            )
            db.add(report)
            db.flush()
        value_num = None
        if is_plain_number(payload.get("value_text", "")):
            value_num = float(payload["value_text"])
        analytes = db.query(CanonicalAnalyte).all()
        matched = match_analyte(payload.get("original_name", ""), analytes)
        norm_val, norm_unit = None, None
        if matched and value_num is not None:
            norm_val, norm_unit = compute_normalized(matched, value_num, payload.get("unit_original"))
        flag = compute_abnormal_flag(
            value_num, payload.get("ref_low"), payload.get("ref_high"), payload.get("printed_flag")
        )
        seq = db.query(LabComponent).filter(LabComponent.lab_report_id == report.id).count()
        comp = LabComponent(
            lab_report_id=report.id,
            sequence=seq,
            original_name=payload.get("original_name", ""),
            value_text=payload.get("value_text", ""),
            value_numeric=value_num,
            unit_original=payload.get("unit_original"),
            ref_low=payload.get("ref_low"),
            ref_high=payload.get("ref_high"),
            ref_text=payload.get("ref_text"),
            abnormal_flag=flag,
            canonical_analyte_id=matched.id if matched else None,
            normalized_value=norm_val,
            normalized_unit=norm_unit,
        )
        db.add(comp)
    elif prop.type == ProposalType.problem:
        db.add(Problem(profile_id=prop.profile_id, display_name=payload.get("display_name", ""), source_document_id=prop.document_id))
    elif prop.type == ProposalType.allergy:
        db.add(Allergy(profile_id=prop.profile_id, substance=payload.get("substance", ""), source_document_id=prop.document_id))
    elif prop.type == ProposalType.medication:
        db.add(Medication(profile_id=prop.profile_id, name=payload.get("name", ""), source_document_id=prop.document_id))
    elif prop.type == ProposalType.immunization:
        db.add(Immunization(profile_id=prop.profile_id, vaccine_name=payload.get("vaccine_name", ""), source_document_id=prop.document_id))
    elif prop.type == ProposalType.procedure:
        db.add(Procedure(profile_id=prop.profile_id, name=payload.get("name", ""), source_document_id=prop.document_id))
    elif prop.type == ProposalType.vital:
        db.add(Vital(profile_id=prop.profile_id, type=payload.get("type", "vital"), value=payload.get("value", ""), unit=payload.get("unit"), source_document_id=prop.document_id))
    elif prop.type == ProposalType.social_history:
        db.add(SocialHistory(profile_id=prop.profile_id, notes=payload.get("notes"), source_document_id=prop.document_id))
    elif prop.type == ProposalType.family_history:
        db.add(FamilyHistory(profile_id=prop.profile_id, relationship=payload.get("relationship", ""), condition=payload.get("condition", ""), source_document_id=prop.document_id))
    elif prop.type == ProposalType.medical_equipment:
        db.add(MedicalEquipment(profile_id=prop.profile_id, name=payload.get("name", ""), source_document_id=prop.document_id))
    prop.status = ProposalStatus.accepted
    db.commit()
    return {"ok": True, "status": "accepted"}

@app.post("/proposals/{proposal_id}/reject")
def reject_proposal(proposal_id: int, db: Session = Depends(get_db)):
    prop = db.query(Proposal).filter(Proposal.id == proposal_id).first()
    if not prop:
        raise HTTPException(404)
    prop.status = ProposalStatus.rejected
    db.commit()
    return {"ok": True, "status": "rejected"}

@app.post("/documents/{document_id}/create-lab")
def create_lab_from_document(document_id: int, body: dict, db: Session = Depends(get_db)):
    """Manual create lab report from document when extraction finds nothing."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(404)
    # body: {panel_name, collection_time, components: [...]}
    enc = Encounter(
        profile_id=doc.profile_id,
        type=EncounterType.lab,
        start=datetime.fromisoformat(body.get("collection_time")) if body.get("collection_time") else datetime.utcnow(),
        reason="Manual from document",
    )
    db.add(enc)
    db.flush()
    report = LabReport(
        profile_id=doc.profile_id,
        encounter_id=enc.id,
        collection_time=enc.start,
        panel_name=body.get("panel_name", "Manual Panel"),
        source_document_id=doc.id,
    )
    db.add(report)
    db.flush()
    analytes = db.query(CanonicalAnalyte).all()
    for seq, c in enumerate(body.get("components", [])):
        value_num = None
        if is_plain_number(c.get("value_text", "")):
            value_num = float(c["value_text"])
        matched = match_analyte(c.get("original_name", ""), analytes)
        norm_val, norm_unit = None, None
        if matched and value_num is not None:
            norm_val, norm_unit = compute_normalized(matched, value_num, c.get("unit_original"))
        flag = compute_abnormal_flag(value_num, c.get("ref_low"), c.get("ref_high"), c.get("printed_flag"))
        comp = LabComponent(
            lab_report_id=report.id,
            sequence=seq,
            original_name=c.get("original_name", ""),
            value_text=c.get("value_text", ""),
            value_numeric=value_num,
            unit_original=c.get("unit_original"),
            ref_low=c.get("ref_low"),
            ref_high=c.get("ref_high"),
            ref_text=c.get("ref_text"),
            abnormal_flag=flag,
            canonical_analyte_id=matched.id if matched else None,
            normalized_value=norm_val,
            normalized_unit=norm_unit,
        )
        db.add(comp)
    db.commit()
    db.refresh(report)
    return {"lab_report_id": report.id, "source_document_id": doc.id}

@app.get("/profiles/{profile_id}/export-ccd")
def export_ccd(profile_id: int, db: Session = Depends(get_db)):
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(404)
    problems = db.query(Problem).filter(Problem.profile_id == profile_id).all()
    allergies = db.query(Allergy).filter(Allergy.profile_id == profile_id).all()
    medications = db.query(Medication).filter(Medication.profile_id == profile_id).all()
    labs = (
        db.query(LabComponent)
        .join(LabReport)
        .filter(LabReport.profile_id == profile_id, LabComponent.canonical_analyte_id.isnot(None))
        .all()
    )
    xml = build_ccd(profile, problems, allergies, medications, labs)
    return Response(content=xml, media_type="application/xml", headers={"Content-Disposition": "attachment; filename=ccd.xml"})
def create_imaging_from_document(document_id: int, body: dict, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(404)
    enc = Encounter(
        profile_id=doc.profile_id,
        type=EncounterType.imaging,
        start=datetime.fromisoformat(body.get("performed_at")) if body.get("performed_at") else datetime.utcnow(),
        reason="Manual imaging from document",
    )
    db.add(enc)
    db.flush()
    img = ImagingReport(
        profile_id=doc.profile_id,
        encounter_id=enc.id,
        modality=body.get("modality", "OT"),
        body_site=body.get("body_site"),
        laterality=body.get("laterality"),
        performed_at=enc.start,
        findings=body.get("findings"),
        impression=body.get("impression"),
        facility=body.get("facility"),
        reporting_provider=body.get("reporting_provider"),
        source_document_id=doc.id,
    )
    db.add(img)
    db.commit()
    db.refresh(img)
    return {"imaging_report_id": img.id, "source_document_id": doc.id}

# DICOM Phase 7
def _require_session(request):
    # Minimal session check for viewer. Real auth is Phase 1.
    if not request.cookies.get("session"):
        raise HTTPException(401, "session required")

@app.post("/profiles/{profile_id}/dicom")
async def upload_dicom(profile_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(404)
    data = await file.read()
    skipped = []
    instances = []
    name = (file.filename or "").lower()
    if name.endswith(".zip"):
        with zipfile.ZipFile(BytesIO(data)) as z:
            for info in z.infolist():
                if info.is_dir():
                    continue
                raw = z.read(info.filename)
                if not raw.startswith(b"DICM") and b"DICM" not in raw[:132]:
                    skipped.append(info.filename)
                    continue
                instances.append(raw)
    else:
        instances.append(data)
    studies = {}
    for raw in instances:
        try:
            ds = pydicom.dcmread(BytesIO(raw), force=True)
        except Exception:
            skipped.append("unreadable")
            continue
        uid = str(getattr(ds, "StudyInstanceUID", "unknown"))
        series_uid = str(getattr(ds, "SeriesInstanceUID", "unknown"))
        modality = str(getattr(ds, "Modality", "OT"))
        desc = str(getattr(ds, "StudyDescription", "") or "")
        accession = str(getattr(ds, "AccessionNumber", "") or "")
        study_date = None
        if hasattr(ds, "StudyDate") and ds.StudyDate:
            try:
                study_date = datetime.strptime(ds.StudyDate, "%Y%m%d")
            except Exception:
                pass
        # Stream to Orthanc (no local pixel copy)
        orthanc_id = None
        try:
            resp = upload_instance(raw)
            orthanc_id = resp.get("ParentStudy") or resp.get("ID")
        except Exception:
            orthanc_id = "local-test"
        if uid not in studies:
            enc = Encounter(profile_id=profile_id, type=EncounterType.imaging, start=study_date or datetime.utcnow(), reason=desc or modality)
            db.add(enc)
            db.flush()
            study = DicomStudy(profile_id=profile_id, study_instance_uid=uid, accession=accession, modality=modality, description=desc, study_date=study_date, orthanc_id=orthanc_id, encounter_id=enc.id)
            db.add(study)
            db.flush()
            studies[uid] = study
        study = studies[uid]
        existing_series = db.query(DicomSeries).filter(DicomSeries.study_id == study.id, DicomSeries.series_instance_uid == series_uid).first()
        if not existing_series:
            ser = DicomSeries(study_id=study.id, series_instance_uid=series_uid, modality=modality, description=str(getattr(ds, "SeriesDescription", "") or ""), orthanc_id=orthanc_id)
            db.add(ser)
    db.commit()
    return {"studies": list(studies.keys()), "skipped": skipped}

@app.get("/profiles/{profile_id}/studies")
def list_studies(profile_id: int, db: Session = Depends(get_db)):
    studies = db.query(DicomStudy).filter(DicomStudy.profile_id == profile_id).all()
    out = []
    for s in studies:
        series = db.query(DicomSeries).filter(DicomSeries.study_id == s.id).all()
        links = db.query(StudyLink).filter(StudyLink.study_id == s.id).all()
        out.append({
            "id": s.id, "study_instance_uid": s.study_instance_uid, "modality": s.modality,
            "description": s.description, "study_date": s.study_date, "orthanc_id": s.orthanc_id,
            "series": [{"id": ser.id, "series_instance_uid": ser.series_instance_uid, "description": ser.description} for ser in series],
            "links": [{"id": l.id, "imaging_report_id": l.imaging_report_id, "document_id": l.document_id, "series_id": l.series_id} for l in links]
        })
    return out

@app.post("/studies/{study_id}/link")
def link_study(study_id: int, body: dict, db: Session = Depends(get_db)):
    study = db.query(DicomStudy).filter(DicomStudy.id == study_id).first()
    if not study:
        raise HTTPException(404)
    link = StudyLink(
        profile_id=study.profile_id,
        study_id=study.id,
        series_id=body.get("series_id"),
        imaging_report_id=body.get("imaging_report_id"),
        document_id=body.get("document_id"),
    )
    db.add(link)
    if body.get("imaging_report_id"):
        rep = db.query(ImagingReport).filter(ImagingReport.id == body["imaging_report_id"]).first()
        if rep:
            rep.dicom_study_id = study.study_instance_uid
            if body.get("series_id"):
                ser = db.query(DicomSeries).filter(DicomSeries.id == body["series_id"]).first()
                if ser:
                    rep.series_id = ser.series_instance_uid
    db.commit()
    return {"ok": True, "link_id": link.id}

@app.delete("/studies/{study_id}/links/{link_id}")
def unlink(study_id: int, link_id: int, db: Session = Depends(get_db)):
    link = db.query(StudyLink).filter(StudyLink.id == link_id, StudyLink.study_id == study_id).first()
    if not link:
        raise HTTPException(404)
    db.delete(link)
    db.commit()
    return {"ok": True}

@app.delete("/profiles/{profile_id}/studies/{study_id}")
def remove_study(profile_id: int, study_id: int, db: Session = Depends(get_db)):
    study = db.query(DicomStudy).filter(DicomStudy.id == study_id, DicomStudy.profile_id == profile_id).first()
    if not study:
        raise HTTPException(404)
    other = db.query(DicomStudy).filter(DicomStudy.study_instance_uid == study.study_instance_uid, DicomStudy.id != study.id).count()
    if other == 0 and study.orthanc_id and study.orthanc_id != "local-test":
        try:
            delete_study(study.orthanc_id)
        except Exception:
            pass
    db.query(StudyLink).filter(StudyLink.study_id == study.id).delete()
    db.query(DicomSeries).filter(DicomSeries.study_id == study.id).delete()
    db.delete(study)
    db.commit()
    return {"ok": True, "removed_from_profile": True}

@app.api_route("/orthanc/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_orthanc(path: str, request: Request):
    from .orthanc_client import ORTHANC_URL, ORTHANC_USER, ORTHANC_PASS
    url = f"{ORTHANC_URL}/{path}"
    if request.url.query:
        url += f"?{request.url.query}"
    body = await request.body()
    async with httpx.AsyncClient(timeout=60.0, auth=(ORTHANC_USER, ORTHANC_PASS), follow_redirects=True) as client:
        r = await client.request(
            request.method,
            url,
            content=body or None,
            headers={"Accept": request.headers.get("accept", "*/*")},
        )
    return Response(content=r.content, status_code=r.status_code, media_type=r.headers.get("content-type"))

@app.get("/viewer/{study_instance_uid}")
def viewer(study_instance_uid: str, request: Request, db: Session = Depends(get_db)):
    if not request.cookies.get("session"):
        raise HTTPException(401, "session required")
    study = db.query(DicomStudy).filter(DicomStudy.study_instance_uid == study_instance_uid).first()
    if not study:
        raise HTTPException(404)
    # Proxied OHIF URL. Browser never sees Orthanc address or password.
    return {"viewer_url": f"/api/orthanc/ohif/viewer?StudyInstanceUIDs={study_instance_uid}", "series_label": None}

# Phase 8 dashboard
@app.get("/profiles/{profile_id}/dashboard")
def dashboard(profile_id: int, db: Session = Depends(get_db)):
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(404)
    problems = db.query(Problem).filter(Problem.profile_id == profile_id, Problem.status == "active").limit(5).all()
    allergies = db.query(Allergy).filter(Allergy.profile_id == profile_id, Allergy.status == "active").limit(5).all()
    meds = db.query(Medication).filter(Medication.profile_id == profile_id, Medication.status == "active").limit(5).all()
    next_appt = db.query(Appointment).filter(Appointment.profile_id == profile_id, Appointment.when >= datetime.utcnow()).order_by(Appointment.when).first()
    encounters = db.query(Encounter).filter(Encounter.profile_id == profile_id).order_by(Encounter.start.desc()).limit(5).all()
    flagged = (
        db.query(LabComponent)
        .join(LabReport)
        .filter(LabReport.profile_id == profile_id, LabComponent.abnormal_flag.in_(["L", "H"]))
        .order_by(LabReport.collection_time.desc())
        .limit(5)
        .all()
    )
    imaging = db.query(ImagingReport).filter(ImagingReport.profile_id == profile_id).order_by(ImagingReport.performed_at.desc()).limit(10).all()
    by_mod = {}
    for r in imaging:
        by_mod.setdefault(r.modality, []).append({"id": r.id, "performed_at": r.performed_at, "impression": r.impression, "dicom_study_id": r.dicom_study_id})
    pending = db.query(Proposal).filter(Proposal.profile_id == profile_id, Proposal.status == ProposalStatus.pending).count()
    return {
        "demographics": {"legal_name": profile.legal_name, "preferred_name": profile.preferred_name, "date_of_birth": profile.date_of_birth, "sex": profile.sex},
        "problems": [{"id": p.id, "display_name": p.display_name} for p in problems],
        "allergies": [{"id": a.id, "substance": a.substance} for a in allergies],
        "medications": [{"id": m.id, "name": m.name} for m in meds],
        "next_appointment": {"when": next_appt.when, "provider": next_appt.provider, "reason": next_appt.reason} if next_appt else None,
        "recent_encounters": [{"id": e.id, "type": e.type.value, "start": e.start, "reason": e.reason} for e in encounters],
        "flagged_labs": [{"original_name": c.original_name, "value_text": c.value_text, "unit": c.unit_original, "ref_low": c.ref_low, "ref_high": c.ref_high, "flag": c.abnormal_flag.value, "analyte": c.canonical.name if c.canonical else None} for c in flagged],
        "imaging_by_modality": by_mod,
        "inbox_count": pending,
    }

@app.get("/profiles/{profile_id}/inbox-count")
def inbox_count(profile_id: int, db: Session = Depends(get_db)):
    n = db.query(Proposal).filter(Proposal.profile_id == profile_id, Proposal.status == ProposalStatus.pending).count()
    return {"count": n}

@app.post("/profiles/{profile_id}/appointments")
def create_appointment(profile_id: int, body: dict, db: Session = Depends(get_db)):
    appt = Appointment(profile_id=profile_id, when=datetime.fromisoformat(body["when"]), provider=body.get("provider"), place=body.get("place"), reason=body.get("reason"))
    db.add(appt)
    db.commit()
    db.refresh(appt)
    return {"id": appt.id, "when": appt.when}
