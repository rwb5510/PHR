from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
import hashlib
import os
import json
import uuid
from .database import get_db, engine
from .models import (
    Base, Profile, Encounter, Order, OrderResultLink, LabReport, LabComponent,
    CanonicalAnalyte, ImagingReport, OrderStatus, Document, Job, JobStatus,
    Proposal, ProposalStatus, ProposalType, EncounterType,
    Problem, Allergy, Medication, Immunization, Procedure, Vital,
    SocialHistory, FamilyHistory, MedicalEquipment
)
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
from .processor import process_job
from .ccda import build_ccd
from fastapi.responses import Response

app = FastAPI(title="Household PHR Phase 4")

STORAGE_ROOT = os.getenv("STORAGE_ROOT", "/data/documents")
os.makedirs(STORAGE_ROOT, exist_ok=True)

@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    load_analytes()
    os.makedirs(STORAGE_ROOT, exist_ok=True)

@app.get("/health")
def health():
    return {"status": "ok"}

# Profiles
@app.post("/profiles", response_model=ProfileOut)
def create_profile(p: ProfileCreate, db: Session = Depends(get_db)):
    obj = Profile(household_id=1, **p.dict())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj

@app.get("/profiles", response_model=List[ProfileOut])
def list_profiles(db: Session = Depends(get_db)):
    return db.query(Profile).all()

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
@app.post("/profiles/{profile_id}/documents")
async def upload_document(
    profile_id: int,
    file: UploadFile = File(...),
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
            "warning": "Duplicate file already stored for this profile. Not filing a second copy.",
            "document_id": existing.id
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
    job = Job(document_id=doc.id, status=JobStatus.queued)
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

@app.get("/documents/{document_id}/file")
def get_document_file(document_id: int, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(404)
    path = os.path.join(STORAGE_ROOT, doc.storage_path)
    if not os.path.exists(path):
        raise HTTPException(404, "file missing")
    return FileResponse(path, filename=doc.filename, media_type=doc.mime_type)

@app.get("/documents/{document_id}/text")
def get_document_text(document_id: int, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(404)
    return {"extracted_text": doc.extracted_text, "ocr_used": doc.ocr_used, "page_count": doc.page_count}

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
    if job.status not in (JobStatus.failed, JobStatus.processing):
        raise HTTPException(400, "only failed or stuck processing jobs can be retried")
    job.status = JobStatus.queued
    job.retry_count += 1
    job.error_message = None
    db.commit()
    return {"status": "queued"}

@app.get("/profiles/{profile_id}/proposals")
def list_proposals(profile_id: int, db: Session = Depends(get_db)):
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
        coll_dt = datetime.fromisoformat(coll) if coll else datetime.utcnow()
        enc = Encounter(
            profile_id=prop.profile_id,
            type=EncounterType.lab,
            start=coll_dt,
            reason="Accepted from review",
        )
        db.add(enc)
        db.flush()
        report = LabReport(
            profile_id=prop.profile_id,
            encounter_id=enc.id,
            collection_time=coll_dt,
            panel_name="Reviewed Panel",
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
        flag = compute_abnormal_flag(value_num, payload.get("ref_low"), payload.get("ref_high"), None)
        comp = LabComponent(
            lab_report_id=report.id,
            sequence=0,
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
