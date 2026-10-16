"""Job processor for document intake. Called by worker loop or tests."""
import json
import os
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import text

from .models import (
    Document, Job, JobStatus, Proposal, ProposalStatus, ProposalType,
    LabReport, LabComponent, Encounter, EncounterType, CanonicalAnalyte
)
from .extraction import extract_document_text, parse_lab_lines, find_collection_date
from .ccda import is_clinical_document, parse_sections
from .lab_matching import match_analyte, is_plain_number, compute_normalized, compute_abnormal_flag

STORAGE_ROOT = os.getenv("STORAGE_ROOT", "/data/documents")

def process_job(db: Session, job_id: int) -> None:
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job or job.status not in (JobStatus.queued, JobStatus.failed):
        return
    job.status = JobStatus.processing
    job.error_message = None
    db.commit()

    try:
        doc = job.document
        with open(os.path.join(STORAGE_ROOT, doc.storage_path), "rb") as f:
            data = f.read()
        text, pages, ocr = extract_document_text(data, doc.mime_type, doc.filename)
        doc.extracted_text = text
        doc.page_count = pages
        doc.ocr_used = ocr
        db.commit()

        # Phase 5: C-CDA detection
        if doc.filename.lower().endswith(".xml") or (doc.mime_type or "").endswith("xml"):
            if is_clinical_document(data):
                analytes = db.query(CanonicalAnalyte).all()
                proposals, patient_dob, _ = parse_sections(data, analytes)
                profile = doc.profile
                dob_mismatch = False
                if patient_dob and profile.date_of_birth and patient_dob != profile.date_of_birth:
                    dob_mismatch = True
                for p in proposals:
                    payload = p["payload"]
                    if dob_mismatch:
                        payload["dob_mismatch"] = f"Document DOB {patient_dob} != profile {profile.date_of_birth}"
                    ptype = ProposalType.lab_line if p["type"] == "lab_line" else getattr(ProposalType, p["type"], ProposalType.lab_report)
                    prop = Proposal(
                        document_id=doc.id,
                        profile_id=doc.profile_id,
                        type=ptype,
                        status=ProposalStatus.pending,
                        payload=json.dumps(payload),
                        quote=p.get("quote"),
                    )
                    db.add(prop)
                job.status = JobStatus.needs_review
                db.commit()
                return

        analytes = db.query(CanonicalAnalyte).all()
        lines = parse_lab_lines(text, analytes)
        coll_date = find_collection_date(text)

        auto_filed_any = False
        proposals_created = False
        # Group auto-fileable lines
        auto_lines = []
        for line in lines:
            can_auto = (
                line["matched"]
                and line["plain_number"]
                and line["unit_original"]
                and coll_date is not None
            )
            if can_auto:
                auto_lines.append(line)
            else:
                # proposal
                payload = {
                    "original_name": line["original_name"],
                    "value_text": line["value_text"],
                    "unit_original": line["unit_original"],
                    "ref_low": line["ref_low"],
                    "ref_high": line["ref_high"],
                    "ref_text": line["ref_text"],
                    "collection_date": coll_date.isoformat() if coll_date else None,
                }
                prop = Proposal(
                    document_id=doc.id,
                    profile_id=doc.profile_id,
                    type=ProposalType.lab_line,
                    status=ProposalStatus.pending,
                    payload=json.dumps(payload),
                    quote=line["quote"],
                )
                db.add(prop)
                proposals_created = True

        if auto_lines and coll_date:
            # Create one lab report for the auto lines
            enc = Encounter(
                profile_id=doc.profile_id,
                type=EncounterType.lab,
                start=coll_date,
                reason="Imported lab",
                facility_name=None,
            )
            db.add(enc)
            db.flush()
            report = LabReport(
                profile_id=doc.profile_id,
                encounter_id=enc.id,
                collection_time=coll_date,
                panel_name="Imported Panel",
                source_document_id=doc.id,
            )
            db.add(report)
            db.flush()
            for seq, line in enumerate(auto_lines):
                value_num = float(line["value_text"]) if line["plain_number"] else None
                matched = next((a for a in analytes if a.id == line["analyte_id"]), None)
                norm_val, norm_unit = None, None
                if matched and value_num is not None:
                    norm_val, norm_unit = compute_normalized(matched, value_num, line["unit_original"])
                flag = compute_abnormal_flag(value_num, line["ref_low"], line["ref_high"], None)
                comp = LabComponent(
                    lab_report_id=report.id,
                    sequence=seq,
                    original_name=line["original_name"],
                    value_text=line["value_text"],
                    value_numeric=value_num,
                    unit_original=line["unit_original"],
                    ref_low=line["ref_low"],
                    ref_high=line["ref_high"],
                    ref_text=line["ref_text"],
                    abnormal_flag=flag,
                    canonical_analyte_id=matched.id if matched else None,
                    normalized_value=norm_val,
                    normalized_unit=norm_unit,
                )
                db.add(comp)
            auto_filed_any = True

        if auto_filed_any and not proposals_created:
            job.status = JobStatus.filed
        elif proposals_created:
            job.status = JobStatus.needs_review
        else:
            # nothing found
            job.status = JobStatus.needs_review
        db.commit()
    except Exception as e:
        job.status = JobStatus.failed
        job.error_message = str(e)[:500]
        db.commit()
        raise

def claim_next_job(db: Session) -> int | None:
    """Postgres SKIP LOCKED claim. For SQLite tests, simple select."""
    if db.bind.dialect.name == "postgresql":
        row = db.execute(
            text("""
                SELECT id FROM job
                WHERE status IN ('queued', 'failed')
                ORDER BY id
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            """)
        ).fetchone()
        if row:
            job_id = row[0]
            db.execute(text("UPDATE job SET status = 'processing' WHERE id = :id"), {"id": job_id})
            db.commit()
            return job_id
        return None
    else:
        job = db.query(Job).filter(Job.status.in_([JobStatus.queued, JobStatus.failed])).order_by(Job.id).first()
        if job:
            job.status = JobStatus.processing
            db.commit()
            return job.id
        return None
