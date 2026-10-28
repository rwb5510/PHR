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
from .extraction import extract_document_text, parse_lab_lines, find_collection_date, DEFAULT_PANEL_NAME
from .document_class import classify_document, extract_imaging_reports, filename_modality
from .panel_catalog import extra_patterns_for_household
from .ccda import is_clinical_document, parse_sections
from .lab_matching import match_analyte, is_plain_number, compute_normalized, compute_abnormal_flag
from .model_client import call_model, llm_autofile_enabled, get_model_mode

STORAGE_ROOT = os.getenv("STORAGE_ROOT", "/data/documents")

def process_job(db: Session, job_id: int) -> None:
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job or job.status not in (JobStatus.queued, JobStatus.failed, JobStatus.processing):
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

        # Phase 6: optional model (never required; off leaves Phase 4/5 unchanged)
        if getattr(job, "use_model", False) and get_model_mode() != "off":
            try:
                alias_list = []
                for a in db.query(CanonicalAnalyte).all():
                    alias_list.append(a.name)
                    alias_list.extend([x.strip() for x in (a.aliases or "").split(",") if x.strip()])
                result = call_model(doc.id, text, alias_list, True)
                if result:
                    for p in result.get("proposals", []):
                        # Never auto-file impressions; only lab_line may auto-file if setting on
                        ptype = getattr(ProposalType, p.get("type") or "", None) or ProposalType.lab_report
                        prop = Proposal(
                            document_id=doc.id,
                            profile_id=doc.profile_id,
                            type=ptype,
                            status=ProposalStatus.pending,
                            payload=json.dumps(p),
                            quote=p.get("quote"),
                            from_model=True,
                        )
                        db.add(prop)
                    job.status = JobStatus.needs_review
                    db.commit()
                    return
            except Exception as e:
                job.status = JobStatus.failed
                job.error_message = f"model_extraction_failed: {type(e).__name__}"
                db.commit()
                return

        analytes = db.query(CanonicalAnalyte).all()
        hid = doc.profile.household_id if doc.profile else None
        extra = extra_patterns_for_household(db, hid)
        lines = parse_lab_lines(text, analytes, extra)
        coll_date = find_collection_date(text)

        auto_filed_any = False
        proposals_created = False
        # One report per printed panel, in first-seen order (dicts keep insertion order).
        auto_by_panel: dict = {}
        for line in lines:
            panel_name = line.get("panel_name") or DEFAULT_PANEL_NAME
            can_auto = (
                line["matched"]
                and line["plain_number"]
                and line["unit_original"]
                and coll_date is not None
            )
            if can_auto:
                auto_by_panel.setdefault(panel_name, []).append(line)
            else:
                payload = {
                    "original_name": line["original_name"],
                    "value_text": line["value_text"],
                    "unit_original": line["unit_original"],
                    "ref_low": line["ref_low"],
                    "ref_high": line["ref_high"],
                    "ref_text": line["ref_text"],
                    "printed_flag": line.get("printed_flag"),
                    "collection_date": coll_date.isoformat() if coll_date else None,
                    "panel_name": panel_name,
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

        if auto_by_panel:
            # Auto-file needs a collection date. One date per file (the only one we
            # parse), so one lab encounter holds every panel drawn with it.
            enc = Encounter(
                profile_id=doc.profile_id,
                type=EncounterType.lab,
                start=coll_date,
                reason="Imported lab",
                facility_name=None,
            )
            db.add(enc)
            db.flush()
        for panel_name, auto_lines in auto_by_panel.items():
            report = LabReport(
                profile_id=doc.profile_id,
                encounter_id=enc.id,
                collection_time=coll_date,
                panel_name=panel_name,
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

        # Phase 13: radiology narratives become imaging_report proposals. Never auto-filed.
        kind = classify_document(doc.filename, text, lab_lines=len(lines))
        if kind == "imaging" and text.strip():
            for payload in extract_imaging_reports(doc.filename, text):
                db.add(Proposal(
                    document_id=doc.id,
                    profile_id=doc.profile_id,
                    type=ProposalType.imaging_report,
                    status=ProposalStatus.pending,
                    payload=json.dumps(payload),
                    quote=payload.get("quote"),
                ))
                proposals_created = True

        if auto_filed_any and not proposals_created:
            job.status = JobStatus.filed
            job.error_message = None
        elif proposals_created:
            job.status = JobStatus.needs_review
            job.error_message = None
        elif filename_modality(doc.filename):
            # Named like an imaging study but no report text came out (blank scan, image only).
            job.status = JobStatus.needs_review
            job.error_message = (
                "No imaging report text was found. Use Create imaging report to enter it by hand."
            )
        else:
            job.status = JobStatus.needs_review
            job.error_message = (
                "No lab lines and no imaging report were detected. A lab result is a test name, "
                "a number, and a lab unit (for example Sodium 140 mmol/L); an imaging report has "
                "Findings or Impression headings. Letterhead, phones, and comments are ignored."
            )
        db.commit()
    except Exception as e:
        job.status = JobStatus.failed
        job.error_message = str(e)[:500]
        db.commit()
        raise

def reset_document_outputs(db: Session, document_id: int) -> None:
    """Drop proposals and auto-filed labs from a prior parse so the job can run again."""
    db.query(Proposal).filter(Proposal.document_id == document_id).delete(synchronize_session=False)
    reports = db.query(LabReport).filter(LabReport.source_document_id == document_id).all()
    enc_ids = []
    for report in reports:
        db.query(LabComponent).filter(LabComponent.lab_report_id == report.id).delete(synchronize_session=False)
        enc_ids.append(report.encounter_id)
        db.delete(report)
    db.flush()
    for eid in enc_ids:
        leftover = db.query(LabReport).filter(LabReport.encounter_id == eid).count()
        if leftover:
            continue
        enc = db.query(Encounter).filter(Encounter.id == eid).first()
        if enc and enc.reason in ("Imported lab", "Accepted from review"):
            db.delete(enc)


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
