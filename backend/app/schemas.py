from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, date
from enum import Enum

class EncounterType(str, Enum):
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

class OrderCategory(str, Enum):
    lab = "lab"
    imaging = "imaging"
    procedure = "procedure"
    referral = "referral"

class OrderStatus(str, Enum):
    ordered = "ordered"
    scheduled = "scheduled"
    completed = "completed"
    cancelled = "cancelled"

class ProfileCreate(BaseModel):
    legal_name: str
    preferred_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    sex: Optional[str] = None
    blood_type: Optional[str] = None
    relationship_label: Optional[str] = None
    notes: Optional[str] = None

class ProfileOut(ProfileCreate):
    id: int
    class Config:
        from_attributes = True

class EncounterCreate(BaseModel):
    profile_id: int
    type: EncounterType
    start: datetime
    end: Optional[datetime] = None
    facility_name: Optional[str] = None
    reason: Optional[str] = None
    notes: Optional[str] = None

class EncounterOut(EncounterCreate):
    id: int
    class Config:
        from_attributes = True

class OrderCreate(BaseModel):
    profile_id: int
    category: OrderCategory
    name: str
    priority: Optional[str] = None
    ordered_at: datetime
    ordering_encounter_id: int
    notes: Optional[str] = None

class OrderOut(BaseModel):
    id: int
    profile_id: int
    category: OrderCategory
    name: str
    status: OrderStatus
    ordered_at: datetime
    ordering_encounter_id: int
    class Config:
        from_attributes = True

class LinkResult(BaseModel):
    result_encounter_id: int

class LabComponentIn(BaseModel):
    original_name: str
    value_text: str
    unit_original: Optional[str] = None
    ref_low: Optional[float] = None
    ref_high: Optional[float] = None
    ref_text: Optional[str] = None
    printed_flag: Optional[str] = None

class LabReportCreate(BaseModel):
    profile_id: int
    encounter_id: int
    order_id: Optional[int] = None
    collection_time: Optional[datetime] = None
    reported_time: Optional[datetime] = None
    performing_lab: Optional[str] = None
    specimen: Optional[str] = None
    panel_name: str
    components: List[LabComponentIn]

class LabComponentOut(BaseModel):
    id: int
    sequence: int
    original_name: str
    value_text: str
    value_numeric: Optional[float]
    unit_original: Optional[str]
    ref_low: Optional[float]
    ref_high: Optional[float]
    ref_text: Optional[str]
    abnormal_flag: str
    canonical_analyte_id: Optional[int]
    normalized_value: Optional[float]
    normalized_unit: Optional[str]
    class Config:
        from_attributes = True

class LabReportOut(BaseModel):
    id: int
    panel_name: str
    collection_time: Optional[datetime]
    source_document_id: Optional[int] = None
    components: List[LabComponentOut]
    class Config:
        from_attributes = True

class ImagingReportCreate(BaseModel):
    profile_id: int
    encounter_id: int
    order_id: Optional[int] = None
    modality: str
    body_site: Optional[str] = None
    laterality: Optional[str] = None
    performed_at: Optional[datetime] = None
    findings: Optional[str] = None
    impression: Optional[str] = None
    facility: Optional[str] = None
    reporting_provider: Optional[str] = None

class ImagingReportOut(ImagingReportCreate):
    id: int
    source_document_id: Optional[int] = None
    class Config:
        from_attributes = True

class TrendPoint(BaseModel):
    collected_at: Optional[datetime]
    original_value: str
    original_unit: Optional[str]
    ref_low: Optional[float]
    ref_high: Optional[float]
    ref_text: Optional[str]
    normalized_value: Optional[float]
    normalized_unit: Optional[str]
    panel_name: str
