"""Manual chart CRUD for the active household."""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .auth import get_current_user
from .database import get_db
from .models import (
    Allergy,
    Appointment,
    EmergencyContact,
    Insurance,
    MedicalEquipment,
    Medication,
    Pharmacy,
    Problem,
    Profile,
    Provider,
    User,
)

router = APIRouter()


def _profile(db: Session, profile_id: int, user: Optional[User]) -> Profile:
    q = db.query(Profile).filter(Profile.id == profile_id)
    if user is not None:
        q = q.filter(Profile.household_id == user.household_id)
    profile = q.first()
    if not profile:
        raise HTTPException(404, "profile not found")
    return profile


class MedicationIn(BaseModel):
    name: str
    rxnorm: Optional[str] = None
    dose: Optional[str] = None
    dose_unit: Optional[str] = None
    route: Optional[str] = None
    frequency: Optional[str] = None
    status: Optional[str] = "active"
    start: Optional[date] = None
    stop: Optional[date] = None
    prescriber: Optional[str] = None
    indication: Optional[str] = None
    notes: Optional[str] = None


class ProblemIn(BaseModel):
    display_name: str
    icd10: Optional[str] = None
    status: Optional[str] = "active"
    onset: Optional[date] = None
    resolved_date: Optional[date] = None
    notes: Optional[str] = None


class AllergyIn(BaseModel):
    substance: str
    reaction: Optional[str] = None
    severity: Optional[str] = "unknown"
    status: Optional[str] = "active"
    onset: Optional[date] = None
    notes: Optional[str] = None


class VoidIn(BaseModel):
    status: str = "entered_in_error"


class ProfilePatch(BaseModel):
    legal_name: Optional[str] = None
    preferred_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    sex: Optional[str] = None
    blood_type: Optional[str] = None
    relationship_label: Optional[str] = None
    notes: Optional[str] = None


class ProviderIn(BaseModel):
    name: str
    credentials: Optional[str] = None
    specialty: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None
    is_primary: bool = False


@router.get("/profiles/{profile_id}")
def get_profile(profile_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = _profile(db, profile_id, user)
    return {
        "id": p.id,
        "legal_name": p.legal_name,
        "preferred_name": p.preferred_name,
        "date_of_birth": p.date_of_birth,
        "sex": p.sex,
        "blood_type": p.blood_type,
        "relationship_label": p.relationship_label,
        "notes": p.notes,
    }


@router.patch("/profiles/{profile_id}")
def patch_profile(
    profile_id: int,
    body: ProfilePatch,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    p = _profile(db, profile_id, user)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    db.commit()
    db.refresh(p)
    return {"id": p.id, "legal_name": p.legal_name, "date_of_birth": p.date_of_birth}


def _list(db, model, profile_id: int, include_voided: bool):
    q = db.query(model).filter(model.profile_id == profile_id)
    if hasattr(model, "status") and not include_voided:
        q = q.filter(model.status != "entered_in_error")
    return q.order_by(model.id.desc()).all()


@router.get("/profiles/{profile_id}/medications")
def list_meds(
    profile_id: int,
    include_voided: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _profile(db, profile_id, user)
    rows = _list(db, Medication, profile_id, include_voided)
    return [
        {
            "id": r.id,
            "name": r.name,
            "dose": r.dose,
            "dose_unit": r.dose_unit,
            "route": r.route,
            "frequency": r.frequency,
            "status": r.status,
            "start": r.start,
            "prescriber": r.prescriber,
        }
        for r in rows
    ]


@router.post("/profiles/{profile_id}/medications")
def create_med(
    profile_id: int,
    body: MedicationIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _profile(db, profile_id, user)
    obj = Medication(profile_id=profile_id, created_by=user.id, **body.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return {"id": obj.id, "name": obj.name, "status": obj.status}


@router.post("/medications/{med_id}/void")
def void_med(med_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    obj = db.query(Medication).filter(Medication.id == med_id).first()
    if not obj:
        raise HTTPException(404)
    _profile(db, obj.profile_id, user)
    obj.status = "entered_in_error"
    db.commit()
    return {"id": obj.id, "status": obj.status}


@router.get("/profiles/{profile_id}/problems")
def list_problems(
    profile_id: int,
    include_voided: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _profile(db, profile_id, user)
    rows = _list(db, Problem, profile_id, include_voided)
    return [{"id": r.id, "display_name": r.display_name, "status": r.status, "icd10": r.icd10} for r in rows]


@router.post("/profiles/{profile_id}/problems")
def create_problem(
    profile_id: int,
    body: ProblemIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _profile(db, profile_id, user)
    obj = Problem(profile_id=profile_id, created_by=user.id, **body.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return {"id": obj.id, "display_name": obj.display_name, "status": obj.status}


@router.post("/problems/{row_id}/void")
def void_problem(row_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    obj = db.query(Problem).filter(Problem.id == row_id).first()
    if not obj:
        raise HTTPException(404)
    _profile(db, obj.profile_id, user)
    obj.status = "entered_in_error"
    db.commit()
    return {"id": obj.id, "status": obj.status}


@router.get("/profiles/{profile_id}/allergies")
def list_allergies(
    profile_id: int,
    include_voided: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _profile(db, profile_id, user)
    rows = _list(db, Allergy, profile_id, include_voided)
    return [
        {"id": r.id, "substance": r.substance, "reaction": r.reaction, "severity": r.severity, "status": r.status}
        for r in rows
    ]


@router.post("/profiles/{profile_id}/allergies")
def create_allergy(
    profile_id: int,
    body: AllergyIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _profile(db, profile_id, user)
    obj = Allergy(profile_id=profile_id, created_by=user.id, **body.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return {"id": obj.id, "substance": obj.substance, "status": obj.status}


@router.get("/profiles/{profile_id}/emergency")
def emergency(profile_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = _profile(db, profile_id, user)
    allergies = _list(db, Allergy, profile_id, False)
    problems = _list(db, Problem, profile_id, False)
    meds = _list(db, Medication, profile_id, False)
    implants = db.query(MedicalEquipment).filter(MedicalEquipment.profile_id == profile_id).all()
    contacts = db.query(EmergencyContact).filter(EmergencyContact.profile_id == profile_id).all()
    pharmacies = db.query(Pharmacy).filter(Pharmacy.profile_id == profile_id).all()
    ins = db.query(Insurance).filter(Insurance.profile_id == profile_id).all()
    primary = (
        db.query(Provider)
        .filter(Provider.profile_id == profile_id, Provider.is_primary == True)  # noqa: E712
        .first()
    )
    return {
        "demographics": {
            "legal_name": p.legal_name,
            "preferred_name": p.preferred_name,
            "date_of_birth": p.date_of_birth,
            "sex": p.sex,
            "blood_type": p.blood_type,
        },
        "allergies": [{"substance": a.substance, "reaction": a.reaction, "severity": a.severity} for a in allergies if a.status == "active"],
        "problems": [{"display_name": x.display_name} for x in problems if x.status == "active"],
        "medications": [{"name": m.name, "dose": m.dose, "dose_unit": m.dose_unit, "frequency": m.frequency} for m in meds if m.status == "active"],
        "implants": [{"name": i.name, "kind": i.kind, "mri_safety": i.mri_safety} for i in implants],
        "emergency_contacts": [{"name": c.name, "relationship": c.relationship, "phone": c.phone} for c in contacts],
        "pharmacies": [{"name": ph.name, "phone": ph.phone} for ph in pharmacies],
        "insurance": [{"payer": i.payer, "plan": i.plan, "member_id": i.member_id} for i in ins],
        "primary_provider": {"name": primary.name, "phone": primary.phone} if primary else None,
    }


@router.get("/profiles/{profile_id}/providers")
def list_providers(profile_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _profile(db, profile_id, user)
    rows = db.query(Provider).filter(Provider.profile_id == profile_id).all()
    return [{"id": r.id, "name": r.name, "specialty": r.specialty, "phone": r.phone, "is_primary": r.is_primary} for r in rows]


@router.post("/profiles/{profile_id}/providers")
def create_provider(
    profile_id: int,
    body: ProviderIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _profile(db, profile_id, user)
    obj = Provider(profile_id=profile_id, **body.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return {"id": obj.id, "name": obj.name}


@router.get("/profiles/{profile_id}/appointments")
def list_appointments(profile_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _profile(db, profile_id, user)
    rows = db.query(Appointment).filter(Appointment.profile_id == profile_id).order_by(Appointment.when.desc()).all()
    return [{"id": r.id, "when": r.when, "provider": r.provider, "place": r.place, "reason": r.reason, "status": r.status} for r in rows]
