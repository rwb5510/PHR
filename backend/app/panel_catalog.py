"""Household panel catalog: seed, templates, import, and parse-time aliases."""
from __future__ import annotations

import csv
import io
import json
import re
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from .auth import household_id_for
from .database import get_db
from .documents import session_household_id
from .lab_matching import match_analyte
from .models import CanonicalAnalyte, Household, PanelComponentDefinition, PanelDefinition

router = APIRouter()

CSV_FIELDS = [
    "panel_name",
    "panel_aliases",
    "sequence",
    "component_alias",
    "canonical_name",
]

STARTER_PANELS = [
    {
        "name": "CMP",
        "aliases": ["comprehensive metabolic", "complete metabolic", "cmp"],
        "components": [
            "Sodium", "Potassium", "Chloride", "Bicarbonate", "Urea nitrogen",
            "Creatinine", "Glucose", "Calcium", "Albumin", "Total protein",
            "Alkaline phosphatase", "ALT", "AST", "Bilirubin, total",
        ],
    },
    {
        "name": "BMP",
        "aliases": ["basic metabolic", "bmp"],
        "components": [
            "Sodium", "Potassium", "Chloride", "Bicarbonate", "Urea nitrogen",
            "Creatinine", "Glucose", "Calcium",
        ],
    },
    {
        "name": "CBC",
        "aliases": ["complete blood count", "cbc"],
        "components": [
            "Leukocytes", "Erythrocytes", "Hemoglobin", "Hematocrit", "Platelets",
            "MCV", "MCH", "MCHC", "RDW",
        ],
    },
    {
        "name": "Lipid Panel",
        "aliases": ["lipid panel", "lipid profile", "lipids"],
        "components": ["Cholesterol, total", "HDL cholesterol", "Triglycerides"],
    },
    {
        "name": "Hemoglobin A1c",
        "aliases": ["hemoglobin a1c", "hba1c", "a1c panel"],
        "components": ["Hemoglobin A1c"],
    },
    {
        "name": "TSH",
        "aliases": ["thyroid", "thyroid panel", "tsh panel"],
        "components": ["TSH"],
    },
]


def split_aliases(text: Optional[str]) -> List[str]:
    return [p.strip() for p in (text or "").split(",") if p.strip()]


def ensure_household(db: Session, household_id: int) -> int:
    row = db.query(Household).filter(Household.id == household_id).first()
    if row:
        return row.id
    row = Household(id=household_id, name="Household")
    db.add(row)
    db.flush()
    return row.id


def resolve_household_id(request: Request, db: Session) -> int:
    hid = session_household_id(request, db)
    if hid is None:
        hid = household_id_for(request, db)
    return ensure_household(db, hid)


def find_panel(db: Session, household_id: int, name: str) -> Optional[PanelDefinition]:
    rows = db.query(PanelDefinition).filter(PanelDefinition.household_id == household_id).all()
    key = name.strip().lower()
    return next((p for p in rows if p.name.lower() == key), None)


def _analytes_by_name(analytes: list) -> Dict[str, CanonicalAnalyte]:
    return {a.name.lower(): a for a in analytes}


def expand_component_tokens(analyte: Optional[CanonicalAnalyte], fallback: str) -> List[str]:
    tokens: List[str] = []
    seen = set()

    def add(tok: str) -> None:
        t = (tok or "").strip()
        if not t:
            return
        k = t.lower()
        if k in seen:
            return
        seen.add(k)
        tokens.append(t)

    if analyte:
        add(analyte.name)
        for part in split_aliases(analyte.aliases):
            add(part)
    else:
        add(fallback)
    return tokens


def starter_component_specs(analytes: list) -> List[Dict[str, Any]]:
    by_name = _analytes_by_name(analytes)
    out = []
    for spec in STARTER_PANELS:
        components = []
        seq = 1
        for cname in spec["components"]:
            analyte = by_name.get(cname.lower())
            for tok in expand_component_tokens(analyte, cname):
                components.append({
                    "sequence": seq,
                    "alias": tok,
                    "canonical_name": analyte.name if analyte else cname,
                })
                seq += 1
        out.append({
            "name": spec["name"],
            "aliases": list(spec["aliases"]),
            "components": components,
        })
    return out


def upsert_panel(
    db: Session,
    household_id: int,
    name: str,
    aliases: List[str],
    components: List[Dict[str, Any]],
    analytes: list,
) -> Tuple[bool, List[Dict[str, Any]]]:
    existing = find_panel(db, household_id, name)
    created = existing is None
    alias_text = ",".join(aliases)
    if existing:
        existing.name = name
        existing.aliases = alias_text
        for child in list(existing.components):
            db.delete(child)
        db.flush()
        panel = existing
    else:
        panel = PanelDefinition(household_id=household_id, name=name, aliases=alias_text)
        db.add(panel)
        db.flush()
    unmatched: List[Dict[str, Any]] = []
    for spec in components:
        alias = (spec.get("alias") or spec.get("original_alias") or "").strip()
        if not alias:
            continue
        try:
            seq = int(spec.get("sequence") or 0)
        except (TypeError, ValueError):
            seq = 0
        if seq <= 0:
            seq = len(panel.components) + 1
        canon_name = (spec.get("canonical_name") or "").strip() or None
        analyte = None
        if canon_name:
            analyte = next((a for a in analytes if a.name.lower() == canon_name.lower()), None)
            if analyte is None:
                unmatched.append({"panel": name, "alias": alias, "canonical_name": canon_name})
        else:
            analyte = match_analyte(alias, analytes)
            if analyte is None:
                unmatched.append({"panel": name, "alias": alias, "canonical_name": None})
        db.add(PanelComponentDefinition(
            panel_definition_id=panel.id,
            sequence=seq,
            original_alias=alias,
            canonical_analyte_id=analyte.id if analyte else None,
        ))
    db.flush()
    return created, unmatched


def seed_starter_if_empty(db: Session, household_id: int) -> None:
    household_id = ensure_household(db, household_id)
    existing = db.query(PanelDefinition).filter(PanelDefinition.household_id == household_id).count()
    if existing:
        return
    analytes = db.query(CanonicalAnalyte).all()
    for spec in starter_component_specs(analytes):
        upsert_panel(db, household_id, spec["name"], spec["aliases"], spec["components"], analytes)
    db.commit()


def seed_all_empty_households(db: Session) -> None:
    for h in db.query(Household).all():
        seed_starter_if_empty(db, h.id)


def serialize_panel(panel: PanelDefinition) -> Dict[str, Any]:
    comps = sorted(panel.components, key=lambda c: c.sequence)
    return {
        "id": panel.id,
        "name": panel.name,
        "aliases": split_aliases(panel.aliases),
        "components": [
            {
                "sequence": c.sequence,
                "original_alias": c.original_alias,
                "canonical_analyte_id": c.canonical_analyte_id,
                "canonical_name": c.canonical.name if c.canonical else None,
            }
            for c in comps
        ],
    }


def extra_patterns_for_household(db: Session, household_id: Optional[int]):
    if not household_id:
        return []
    panels = db.query(PanelDefinition).filter(PanelDefinition.household_id == household_id).all()
    if not panels:
        return []
    analytes = db.query(CanonicalAnalyte).all()
    analyte_aliases = set()
    for a in analytes:
        analyte_aliases.add(a.name.strip().lower())
        for part in split_aliases(a.aliases):
            analyte_aliases.add(part.lower())
    patterns = []
    seen = set()
    for panel in panels:
        tokens = [panel.name] + split_aliases(panel.aliases)
        n_canon = len({c.canonical_analyte_id for c in panel.components if c.canonical_analyte_id})
        single_test = n_canon <= 1
        for token in tokens:
            t = token.strip()
            if len(t) <= 2:
                continue
            key = (t.lower(), panel.name)
            if key in seen:
                continue
            if t.lower() in analyte_aliases and not single_test and t.lower() != panel.name.lower():
                continue
            seen.add(key)
            patterns.append((re.compile(r"(?<!\w)" + re.escape(t) + r"(?!\w)", re.I), panel.name))
    return patterns


def _csv_to_payload(text: str) -> Dict[str, Any]:
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(400, "csv missing header")
    fields = {f.strip() for f in reader.fieldnames if f}
    needed = set(CSV_FIELDS)
    if not needed.issubset(fields):
        raise HTTPException(400, "csv missing required headers")
    grouped: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for row in reader:
        name = (row.get("panel_name") or "").strip()
        if not name:
            continue
        key = name.lower()
        if key not in grouped:
            grouped[key] = {
                "name": name,
                "aliases": split_aliases(row.get("panel_aliases") or ""),
                "components": [],
            }
            order.append(key)
        alias = (row.get("component_alias") or "").strip()
        if not alias:
            continue
        seq_raw = (row.get("sequence") or "").strip()
        try:
            seq = int(seq_raw) if seq_raw else len(grouped[key]["components"]) + 1
        except ValueError:
            seq = len(grouped[key]["components"]) + 1
        canon = (row.get("canonical_name") or "").strip() or None
        grouped[key]["components"].append({
            "sequence": seq,
            "alias": alias,
            "canonical_name": canon,
        })
    return {"version": 1, "panels": [grouped[k] for k in order]}


async def _read_import_payload(request: Request) -> Dict[str, Any]:
    ctype = (request.headers.get("content-type") or "").lower()
    if "multipart/form-data" in ctype:
        form = await request.form()
        upload = form.get("file")
        if upload is None:
            raise HTTPException(400, "file required")
        raw = await upload.read()
        filename = (getattr(upload, "filename", "") or "").lower()
        content_type = (getattr(upload, "content_type", "") or "").lower()
        if filename.endswith(".json") or "json" in content_type:
            try:
                return json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as exc:
                raise HTTPException(400, "invalid json") from exc
        try:
            return _csv_to_payload(raw.decode("utf-8-sig"))
        except HTTPException:
            raise
        except UnicodeDecodeError as exc:
            raise HTTPException(400, "invalid csv") from exc
    try:
        return await request.json()
    except Exception as exc:
        raise HTTPException(400, "expected JSON or CSV file") from exc


def _template_rows(db: Session) -> List[Dict[str, Any]]:
    analytes = db.query(CanonicalAnalyte).all()
    rows = []
    for spec in starter_component_specs(analytes):
        alias_str = ",".join(spec["aliases"])
        for comp in spec["components"]:
            rows.append({
                "panel_name": spec["name"],
                "panel_aliases": alias_str,
                "sequence": comp["sequence"],
                "component_alias": comp["alias"],
                "canonical_name": comp.get("canonical_name") or "",
            })
    return rows


@router.get("/panel-catalog")
def get_panel_catalog(request: Request, db: Session = Depends(get_db)):
    hid = resolve_household_id(request, db)
    seed_starter_if_empty(db, hid)
    panels = (
        db.query(PanelDefinition)
        .filter(PanelDefinition.household_id == hid)
        .order_by(PanelDefinition.name)
        .all()
    )
    return {"panels": [serialize_panel(p) for p in panels]}


@router.get("/panel-catalog/template.csv")
def download_template_csv(request: Request, db: Session = Depends(get_db)):
    resolve_household_id(request, db)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in _template_rows(db):
        writer.writerow(row)
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=panel-catalog-template.csv"},
    )


@router.get("/panel-catalog/template.json")
def download_template_json(request: Request, db: Session = Depends(get_db)):
    resolve_household_id(request, db)
    analytes = db.query(CanonicalAnalyte).all()
    payload = {"version": 1, "panels": starter_component_specs(analytes)}
    return Response(
        content=json.dumps(payload, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=panel-catalog-template.json"},
    )


@router.post("/panel-catalog/import")
async def import_panel_catalog(
    request: Request,
    mode: str = "merge",
    db: Session = Depends(get_db),
):
    mode = (mode or "merge").lower()
    if mode not in ("merge", "replace"):
        raise HTTPException(400, "mode must be merge or replace")
    hid = resolve_household_id(request, db)
    if mode == "merge":
        seed_starter_if_empty(db, hid)
    payload = await _read_import_payload(request)
    panels = payload.get("panels") if isinstance(payload, dict) else None
    if not isinstance(panels, list):
        raise HTTPException(400, "payload must include panels[]")
    if mode == "replace":
        existing = db.query(PanelDefinition).filter(PanelDefinition.household_id == hid).all()
        for panel in existing:
            db.delete(panel)
        db.flush()
    analytes = db.query(CanonicalAnalyte).all()
    imported = 0
    updated = 0
    skipped = 0
    unmatched: List[Dict[str, Any]] = []
    for spec in panels:
        if not isinstance(spec, dict):
            skipped += 1
            continue
        name = (spec.get("name") or "").strip()
        if not name:
            skipped += 1
            continue
        aliases = spec.get("aliases") or []
        if isinstance(aliases, str):
            aliases = split_aliases(aliases)
        comps = spec.get("components") or []
        created, um = upsert_panel(db, hid, name, list(aliases), comps, analytes)
        if created:
            imported += 1
        else:
            updated += 1
        unmatched.extend(um)
    db.commit()
    return {
        "imported": imported,
        "updated": updated,
        "skipped": skipped,
        "unmatched_components": unmatched,
    }


@router.delete("/panel-catalog/{panel_id}")
def delete_panel(panel_id: int, request: Request, db: Session = Depends(get_db)):
    hid = resolve_household_id(request, db)
    panel = (
        db.query(PanelDefinition)
        .filter(PanelDefinition.id == panel_id, PanelDefinition.household_id == hid)
        .first()
    )
    if not panel:
        raise HTTPException(404, "panel not found")
    db.delete(panel)
    db.commit()
    return {"ok": True}
