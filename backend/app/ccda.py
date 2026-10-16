"""C-CDA import/export. Phase 5. No model, no DICOM."""
import json
from datetime import datetime, date
from typing import List, Dict, Any, Optional, Tuple
from lxml import etree

from .models import CanonicalAnalyte
from .lab_matching import match_analyte

# HL7 C-CDA R2.1 CCD template OIDs (from HL7 CDA R2.1 Implementation Guide)
CCD_TEMPLATE_OID = "2.16.840.1.113883.10.20.22.1.2"
PROBLEM_SECTION_OID = "2.16.840.1.113883.10.20.22.2.5.1"
ALLERGY_SECTION_OID = "2.16.840.1.113883.10.20.22.2.6.1"
MED_SECTION_OID = "2.16.840.1.113883.10.20.22.2.1.1"
RESULT_SECTION_OID = "2.16.840.1.113883.10.20.22.2.3.1"
IMMUN_SECTION_OID = "2.16.840.1.113883.10.20.22.2.2.1"
PROC_SECTION_OID = "2.16.840.1.113883.10.20.22.2.7.1"
VITAL_SECTION_OID = "2.16.840.1.113883.10.20.22.2.4.1"
SOCIAL_SECTION_OID = "2.16.840.1.113883.10.20.22.2.17"
FAMILY_SECTION_OID = "2.16.840.1.113883.10.20.22.2.15"
EQUIP_SECTION_OID = "2.16.840.1.113883.10.20.22.2.23"

NS = {"cda": "urn:hl7-org:v3"}

def is_clinical_document(xml_bytes: bytes) -> bool:
    try:
        root = etree.fromstring(xml_bytes)
        return root.tag == "{urn:hl7-org:v3}ClinicalDocument"
    except Exception:
        return False

def extract_dob(root) -> Optional[date]:
    el = root.find(".//cda:patient/cda:birthTime", NS)
    if el is not None and el.get("value"):
        v = el.get("value")
        try:
            return datetime.strptime(v[:8], "%Y%m%d").date()
        except Exception:
            pass
    return None

def parse_sections(xml_bytes: bytes, analytes: List[CanonicalAnalyte]) -> Tuple[List[Dict], Optional[date], str]:
    """Return (proposals, patient_dob, mismatch_note)."""
    root = etree.fromstring(xml_bytes)
    patient_dob = extract_dob(root)
    proposals = []

    # Problems
    for sec in root.findall(".//cda:section", NS):
        tid = sec.find("cda:templateId", NS)
        if tid is not None and tid.get("root") == PROBLEM_SECTION_OID:
            for obs in sec.findall(".//cda:observation", NS):
                val = obs.find(".//cda:value", NS)
                name = (val.get("displayName") if val is not None else "") or (obs.find(".//cda:code", NS).get("displayName") if obs.find(".//cda:code", NS) is not None else "")
                name = (name or "").strip()
                if name:
                    proposals.append({"type": "problem", "payload": {"display_name": name}, "quote": name})

    # Allergies
    for sec in root.findall(".//cda:section", NS):
        tid = sec.find("cda:templateId", NS)
        if tid is not None and tid.get("root") == ALLERGY_SECTION_OID:
            for obs in sec.findall(".//cda:observation", NS):
                code_el = obs.find(".//cda:participant/cda:participantRole/cda:playingEntity/cda:code", NS)
                subst = (code_el.get("displayName") if code_el is not None else "").strip()
                if subst:
                    proposals.append({"type": "allergy", "payload": {"substance": subst}, "quote": subst})

    # Medications
    for sec in root.findall(".//cda:section", NS):
        tid = sec.find("cda:templateId", NS)
        if tid is not None and tid.get("root") == MED_SECTION_OID:
            for sub in sec.findall(".//cda:substanceAdministration", NS):
                code_el = sub.find(".//cda:manufacturedMaterial/cda:code", NS)
                name = (code_el.get("displayName") if code_el is not None else "").strip()
                if name:
                    proposals.append({"type": "medication", "payload": {"name": name}, "quote": name})

    # Results
    for sec in root.findall(".//cda:section", NS):
        tid = sec.find("cda:templateId", NS)
        if tid is not None and tid.get("root") == RESULT_SECTION_OID:
            for obs in sec.findall(".//cda:observation", NS):
                code_el = obs.find("cda:code", NS)
                loinc = code_el.get("code") if code_el is not None else None
                display = code_el.get("displayName") if code_el is not None else ""
                value_el = obs.find("cda:value", NS)
                value_text = value_el.get("value") if value_el is not None else ""
                unit = value_el.get("unit") if value_el is not None else ""
                matched = None
                if loinc:
                    for a in analytes:
                        if a.loinc == loinc:
                            matched = a
                            break
                proposals.append({
                    "type": "lab_line",
                    "payload": {
                        "original_name": display or loinc or "result",
                        "value_text": value_text,
                        "unit_original": unit,
                        "loinc": loinc,
                        "canonical_analyte_id": matched.id if matched else None,
                    },
                    "quote": f"{display} {value_text} {unit}",
                })

    return proposals, patient_dob, ""

def build_ccd(profile, problems, allergies, medications, lab_components) -> bytes:
    """Minimal C-CDA R2.1 CCD. OIDs from HL7 CDA R2.1 IG."""
    root = etree.Element("{urn:hl7-org:v3}ClinicalDocument", nsmap={None: "urn:hl7-org:v3"})
    etree.SubElement(root, "templateId", root=CCD_TEMPLATE_OID)
    etree.SubElement(root, "id", root="2.16.840.1.113883.19.5", extension="synthetic")
    etree.SubElement(root, "code", code="34133-9", codeSystem="2.16.840.1.113883.6.1", displayName="Summarization of Episode Note")
    etree.SubElement(root, "title").text = "Self-generated personal health record CCD"
    etree.SubElement(root, "effectiveTime", value=datetime.utcnow().strftime("%Y%m%d%H%M%S"))

    recordTarget = etree.SubElement(root, "recordTarget")
    patientRole = etree.SubElement(recordTarget, "patientRole")
    patient = etree.SubElement(patientRole, "patient")
    name = etree.SubElement(patient, "name")
    etree.SubElement(name, "given").text = profile.preferred_name or profile.legal_name.split()[0]
    etree.SubElement(name, "family").text = profile.legal_name.split()[-1] if " " in profile.legal_name else profile.legal_name
    if profile.date_of_birth:
        etree.SubElement(patient, "birthTime", value=profile.date_of_birth.strftime("%Y%m%d"))

    author = etree.SubElement(root, "author")
    etree.SubElement(author, "time", value=datetime.utcnow().strftime("%Y%m%d"))
    assigned = etree.SubElement(author, "assignedAuthor")
    etree.SubElement(assigned, "id", root="2.16.840.1.113883.19.5")
    assignedPerson = etree.SubElement(assigned, "assignedPerson")
    etree.SubElement(assignedPerson, "name").text = "Self-generated personal record"

    # Problems section
    if problems:
        sec = etree.SubElement(root, "section")
        etree.SubElement(sec, "templateId", root=PROBLEM_SECTION_OID)
        etree.SubElement(sec, "code", code="11450-4", codeSystem="2.16.840.1.113883.6.1")
        etree.SubElement(sec, "title").text = "Problems"
        for p in problems:
            entry = etree.SubElement(sec, "entry")
            obs = etree.SubElement(entry, "observation")
            etree.SubElement(obs, "code", displayName=p.display_name or "")
            etree.SubElement(obs, "value", displayName=p.display_name or "")

    # Allergies
    if allergies:
        sec = etree.SubElement(root, "section")
        etree.SubElement(sec, "templateId", root=ALLERGY_SECTION_OID)
        etree.SubElement(sec, "code", code="48765-2", codeSystem="2.16.840.1.113883.6.1")
        etree.SubElement(sec, "title").text = "Allergies"
        for a in allergies:
            entry = etree.SubElement(sec, "entry")
            obs = etree.SubElement(entry, "observation")
            part = etree.SubElement(obs, "participant")
            role = etree.SubElement(part, "participantRole")
            playing = etree.SubElement(role, "playingEntity")
            etree.SubElement(playing, "code", displayName=a.substance or "")

    # Medications
    if medications:
        sec = etree.SubElement(root, "section")
        etree.SubElement(sec, "templateId", root=MED_SECTION_OID)
        etree.SubElement(sec, "code", code="10160-0", codeSystem="2.16.840.1.113883.6.1")
        etree.SubElement(sec, "title").text = "Medications"
        for m in medications:
            entry = etree.SubElement(sec, "entry")
            sub = etree.SubElement(entry, "substanceAdministration")
            cons = etree.SubElement(sub, "consumable")
            mat = etree.SubElement(cons, "manufacturedProduct")
            mm = etree.SubElement(mat, "manufacturedMaterial")
            etree.SubElement(mm, "code", displayName=m.name or "")

    # Results
    if lab_components:
        sec = etree.SubElement(root, "section")
        etree.SubElement(sec, "templateId", root=RESULT_SECTION_OID)
        etree.SubElement(sec, "code", code="30954-2", codeSystem="2.16.840.1.113883.6.1")
        etree.SubElement(sec, "title").text = "Results"
        org = etree.SubElement(sec, "organizer")
        for c in lab_components:
            entry = etree.SubElement(org, "component")
            obs = etree.SubElement(entry, "observation")
            if c.canonical and c.canonical.loinc:
                etree.SubElement(obs, "code", code=c.canonical.loinc, displayName=c.original_name, codeSystem="2.16.840.1.113883.6.1")
            else:
                etree.SubElement(obs, "code", displayName=c.original_name)
            etree.SubElement(obs, "value", value=c.value_text, unit=c.unit_original or "")

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8")
