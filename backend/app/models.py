from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import (
    Column, Integer, String, DateTime, Date, Boolean, Float, Text, ForeignKey,
    Enum as SQLEnum, UniqueConstraint, Index
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func
import enum

Base = declarative_base()

class EncounterType(str, enum.Enum):
    office_visit = "office_visit"
    telehealth = "telehealth"
    ed = "ed"
    hospital_stay = "hospital_stay"
    lab = "lab"
    imaging = "imaging"
    procedure = "procedure"
    immunization_visit = "immunization_visit"
    patient_entered = "patient_entered"
    other = "other"

class OrderCategory(str, enum.Enum):
    lab = "lab"
    imaging = "imaging"
    procedure = "procedure"
    referral = "referral"

class OrderStatus(str, enum.Enum):
    ordered = "ordered"
    scheduled = "scheduled"
    completed = "completed"
    cancelled = "cancelled"

class AbnormalFlag(str, enum.Enum):
    L = "L"
    H = "H"
    N = "N"
    unknown = "unknown"

class Household(Base):
    __tablename__ = "household"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

class User(Base):
    __tablename__ = "user"
    id = Column(Integer, primary_key=True)
    household_id = Column(Integer, ForeignKey("household.id"), nullable=False)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    totp_secret = Column(String, nullable=True)
    totp_enabled = Column(Boolean, default=False)

class Profile(Base):
    __tablename__ = "profile"
    id = Column(Integer, primary_key=True)
    household_id = Column(Integer, ForeignKey("household.id"), nullable=False)
    legal_name = Column(String, nullable=False)
    preferred_name = Column(String, nullable=True)
    date_of_birth = Column(Date, nullable=True)
    sex = Column(String, nullable=True)
    blood_type = Column(String, nullable=True)
    relationship_label = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

class Encounter(Base):
    __tablename__ = "encounter"
    id = Column(Integer, primary_key=True)
    profile_id = Column(Integer, ForeignKey("profile.id"), nullable=False, index=True)
    type = Column(SQLEnum(EncounterType), nullable=False)
    start = Column(DateTime, nullable=False)
    end = Column(DateTime, nullable=True)
    facility_name = Column(String, nullable=True)
    reason = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    created_by = Column(Integer, ForeignKey("user.id"), nullable=True)

    profile = relationship("Profile")
    orders_placed = relationship("Order", foreign_keys="Order.ordering_encounter_id", back_populates="ordering_encounter")
    result_orders = relationship("OrderResultLink", back_populates="result_encounter")

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    profile_id = Column(Integer, ForeignKey("profile.id"), nullable=False, index=True)
    category = Column(SQLEnum(OrderCategory), nullable=False)
    name = Column(String, nullable=False)
    priority = Column(String, nullable=True)
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.ordered, nullable=False)
    ordered_at = Column(DateTime, nullable=False)
    ordering_encounter_id = Column(Integer, ForeignKey("encounter.id"), nullable=False)
    ordering_provider_id = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    created_by = Column(Integer, ForeignKey("user.id"), nullable=True)

    ordering_encounter = relationship("Encounter", foreign_keys=[ordering_encounter_id], back_populates="orders_placed")
    result_links = relationship("OrderResultLink", back_populates="order")

class OrderResultLink(Base):
    __tablename__ = "order_result_link"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    result_encounter_id = Column(Integer, ForeignKey("encounter.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    order = relationship("Order", back_populates="result_links")
    result_encounter = relationship("Encounter", back_populates="result_orders")

class CanonicalAnalyte(Base):
    __tablename__ = "canonical_analyte"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    loinc = Column(String, nullable=False, unique=True)
    ucum = Column(String, nullable=False)
    aliases = Column(Text, nullable=False)

class LabReport(Base):
    __tablename__ = "lab_report"
    id = Column(Integer, primary_key=True)
    profile_id = Column(Integer, ForeignKey("profile.id"), nullable=False, index=True)
    encounter_id = Column(Integer, ForeignKey("encounter.id"), nullable=False)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    collection_time = Column(DateTime, nullable=True)
    reported_time = Column(DateTime, nullable=True)
    performing_lab = Column(String, nullable=True)
    specimen = Column(String, nullable=True)
    panel_name = Column(String, nullable=False)
    source_document_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    created_by = Column(Integer, ForeignKey("user.id"), nullable=True)

    encounter = relationship("Encounter")
    components = relationship("LabComponent", back_populates="report", order_by="LabComponent.sequence")

class LabComponent(Base):
    __tablename__ = "lab_component"
    id = Column(Integer, primary_key=True)
    lab_report_id = Column(Integer, ForeignKey("lab_report.id"), nullable=False)
    sequence = Column(Integer, nullable=False, default=0)
    original_name = Column(String, nullable=False)
    value_text = Column(String, nullable=False)
    value_numeric = Column(Float, nullable=True)
    unit_original = Column(String, nullable=True)
    ref_low = Column(Float, nullable=True)
    ref_high = Column(Float, nullable=True)
    ref_text = Column(String, nullable=True)
    abnormal_flag = Column(SQLEnum(AbnormalFlag), default=AbnormalFlag.unknown, nullable=False)
    canonical_analyte_id = Column(Integer, ForeignKey("canonical_analyte.id"), nullable=True)
    normalized_value = Column(Float, nullable=True)
    normalized_unit = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    report = relationship("LabReport", back_populates="components")
    canonical = relationship("CanonicalAnalyte")

class ImagingReport(Base):
    __tablename__ = "imaging_report"
    id = Column(Integer, primary_key=True)
    profile_id = Column(Integer, ForeignKey("profile.id"), nullable=False, index=True)
    encounter_id = Column(Integer, ForeignKey("encounter.id"), nullable=False)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    modality = Column(String, nullable=False)
    body_site = Column(String, nullable=True)
    laterality = Column(String, nullable=True)
    performed_at = Column(DateTime, nullable=True)
    findings = Column(Text, nullable=True)
    impression = Column(Text, nullable=True)
    facility = Column(String, nullable=True)
    reporting_provider = Column(String, nullable=True)
    dicom_study_id = Column(String, nullable=True)
    series_id = Column(String, nullable=True)
    source_document_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    created_by = Column(Integer, ForeignKey("user.id"), nullable=True)

    encounter = relationship("Encounter")

class Document(Base):
    __tablename__ = "document"
    id = Column(Integer, primary_key=True)
    profile_id = Column(Integer, ForeignKey("profile.id"), nullable=False, index=True)
    filename = Column(String, nullable=False)
    mime_type = Column(String, nullable=False)
    sha256 = Column(String, nullable=False, index=True)
    size_bytes = Column(Integer, nullable=False)
    page_count = Column(Integer, nullable=True)
    extracted_text = Column(Text, nullable=True)
    ocr_used = Column(Boolean, default=False, nullable=False)
    storage_path = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    created_by = Column(Integer, ForeignKey("user.id"), nullable=True)

    profile = relationship("Profile")
    jobs = relationship("Job", back_populates="document")

class JobStatus(str, enum.Enum):
    queued = "queued"
    processing = "processing"
    needs_review = "needs_review"
    filed = "filed"
    failed = "failed"

class Job(Base):
    __tablename__ = "job"
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("document.id"), nullable=False, index=True)
    status = Column(SQLEnum(JobStatus), default=JobStatus.queued, nullable=False, index=True)
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0, nullable=False)
    use_model = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    document = relationship("Document", back_populates="jobs")

class ProposalStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"

class ProposalType(str, enum.Enum):
    lab_line = "lab_line"
    lab_report = "lab_report"
    imaging_report = "imaging_report"
    problem = "problem"
    allergy = "allergy"
    medication = "medication"
    immunization = "immunization"
    procedure = "procedure"
    encounter = "encounter"
    vital = "vital"
    social_history = "social_history"
    family_history = "family_history"
    medical_equipment = "medical_equipment"

class Proposal(Base):
    __tablename__ = "proposal"
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("document.id"), nullable=False, index=True)
    profile_id = Column(Integer, ForeignKey("profile.id"), nullable=False, index=True)
    type = Column(SQLEnum(ProposalType), nullable=False)
    status = Column(SQLEnum(ProposalStatus), default=ProposalStatus.pending, nullable=False)
    payload = Column(Text, nullable=False)
    quote = Column(Text, nullable=True)
    from_model = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    document = relationship("Document")

class Problem(Base):
    __tablename__ = "problem"
    id = Column(Integer, primary_key=True)
    profile_id = Column(Integer, ForeignKey("profile.id"), nullable=False, index=True)
    display_name = Column(String, nullable=False)
    icd10 = Column(String, nullable=True)
    status = Column(String, default="active")
    onset = Column(Date, nullable=True)
    resolved_date = Column(Date, nullable=True)
    notes = Column(Text, nullable=True)
    source_document_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    created_by = Column(Integer, ForeignKey("user.id"), nullable=True)

class Allergy(Base):
    __tablename__ = "allergy"
    id = Column(Integer, primary_key=True)
    profile_id = Column(Integer, ForeignKey("profile.id"), nullable=False, index=True)
    substance = Column(String, nullable=False)
    reaction = Column(String, nullable=True)
    severity = Column(String, default="unknown")
    status = Column(String, default="active")
    onset = Column(Date, nullable=True)
    notes = Column(Text, nullable=True)
    source_document_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    created_by = Column(Integer, ForeignKey("user.id"), nullable=True)

class Medication(Base):
    __tablename__ = "medication"
    id = Column(Integer, primary_key=True)
    profile_id = Column(Integer, ForeignKey("profile.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    rxnorm = Column(String, nullable=True)
    dose = Column(String, nullable=True)
    dose_unit = Column(String, nullable=True)
    route = Column(String, nullable=True)
    frequency = Column(String, nullable=True)
    status = Column(String, default="active")
    start = Column(Date, nullable=True)
    stop = Column(Date, nullable=True)
    prescriber = Column(String, nullable=True)
    indication = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    source_document_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    created_by = Column(Integer, ForeignKey("user.id"), nullable=True)

class Immunization(Base):
    __tablename__ = "immunization"
    id = Column(Integer, primary_key=True)
    profile_id = Column(Integer, ForeignKey("profile.id"), nullable=False, index=True)
    vaccine_name = Column(String, nullable=False)
    cvx = Column(String, nullable=True)
    date = Column(Date, nullable=True)
    lot = Column(String, nullable=True)
    site = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    source_document_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    created_by = Column(Integer, ForeignKey("user.id"), nullable=True)

class Procedure(Base):
    __tablename__ = "procedure"
    id = Column(Integer, primary_key=True)
    profile_id = Column(Integer, ForeignKey("profile.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    date = Column(Date, nullable=True)
    laterality = Column(String, nullable=True)
    provider = Column(String, nullable=True)
    facility = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    encounter_id = Column(Integer, ForeignKey("encounter.id"), nullable=True)
    source_document_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    created_by = Column(Integer, ForeignKey("user.id"), nullable=True)

class Vital(Base):
    __tablename__ = "vital"
    id = Column(Integer, primary_key=True)
    profile_id = Column(Integer, ForeignKey("profile.id"), nullable=False, index=True)
    type = Column(String, nullable=False)
    value = Column(String, nullable=False)
    unit = Column(String, nullable=True)
    measured_at = Column(DateTime, nullable=True)
    encounter_id = Column(Integer, ForeignKey("encounter.id"), nullable=True)
    source_document_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

class SocialHistory(Base):
    __tablename__ = "social_history"
    id = Column(Integer, primary_key=True)
    profile_id = Column(Integer, ForeignKey("profile.id"), nullable=False, index=True)
    as_of = Column(Date, nullable=True)
    smoking = Column(Text, nullable=True)
    alcohol = Column(Text, nullable=True)
    other_substances = Column(Text, nullable=True)
    occupation = Column(Text, nullable=True)
    living_situation = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    source_document_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

class FamilyHistory(Base):
    __tablename__ = "family_history"
    id = Column(Integer, primary_key=True)
    profile_id = Column(Integer, ForeignKey("profile.id"), nullable=False, index=True)
    relationship = Column(String, nullable=False)
    condition = Column(String, nullable=False)
    age_at_onset = Column(Integer, nullable=True)
    deceased = Column(Boolean, default=False)
    notes = Column(Text, nullable=True)
    source_document_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

class MedicalEquipment(Base):
    __tablename__ = "medical_equipment"
    id = Column(Integer, primary_key=True)
    profile_id = Column(Integer, ForeignKey("profile.id"), nullable=False, index=True)
    kind = Column(String, nullable=True)
    name = Column(String, nullable=False)
    model = Column(String, nullable=True)
    laterality = Column(String, nullable=True)
    implanted_date = Column(Date, nullable=True)
    facility = Column(String, nullable=True)
    mri_safety = Column(String, nullable=True)
    udi = Column(String, nullable=True)
    source_document_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

