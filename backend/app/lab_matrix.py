"""Assemble a profile-scoped lab results matrix (date columns, component rows)."""
from collections import defaultdict
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session, joinedload

from .lab_matching import normalize_test_name
from .models import CanonicalAnalyte, LabComponent, LabReport


def unmatched_key(original_name: Optional[str]) -> str:
    return normalize_test_name(original_name or "").lower()


def _flag(component: LabComponent) -> str:
    flag = component.abnormal_flag
    return flag.value if hasattr(flag, "value") else str(flag)


def _rank(component: LabComponent) -> tuple:
    report = component.report
    reported = report.reported_time or datetime.min
    return (reported, report.id)


def _cell(component: LabComponent) -> dict[str, Any]:
    report = component.report
    return {
        "component_id": component.id,
        "report_id": report.id,
        "panel_name": report.panel_name,
        "value_text": component.value_text,
        "value_numeric": component.value_numeric,
        "unit_original": component.unit_original,
        "normalized_value": component.normalized_value,
        "normalized_unit": component.normalized_unit,
        "abnormal_flag": _flag(component),
        "ref_text": component.ref_text,
        "source_document_id": report.source_document_id,
        "also": [],
    }


def _also(component: LabComponent) -> dict[str, Any]:
    report = component.report
    return {
        "report_id": report.id,
        "panel_name": report.panel_name,
        "value_text": component.value_text,
    }


def _point(component: LabComponent) -> dict[str, Any]:
    report = component.report
    return {
        "collected_at": report.collection_time.isoformat() if report.collection_time else None,
        "original_value": component.value_text,
        "original_unit": component.unit_original,
        "ref_low": component.ref_low,
        "ref_high": component.ref_high,
        "ref_text": component.ref_text,
        "normalized_value": component.normalized_value,
        "normalized_unit": component.normalized_unit,
        "panel_name": report.panel_name,
        "value_numeric": component.value_numeric,
        "source_document_id": report.source_document_id,
    }


def _pick_cells(by_date: dict[str, list[LabComponent]]) -> dict[str, dict[str, Any]]:
    cells: dict[str, dict[str, Any]] = {}
    for date_key, group in by_date.items():
        ordered = sorted(group, key=_rank)
        winner = ordered[-1]
        cell = _cell(winner)
        cell["also"] = [_also(item) for item in ordered[:-1]]
        cells[date_key] = cell
    return cells


def build_lab_matrix(db: Session, profile_id: int) -> dict[str, Any]:
    comps = (
        db.query(LabComponent)
        .join(LabReport)
        .filter(LabReport.profile_id == profile_id, LabReport.collection_time.isnot(None))
        .options(joinedload(LabComponent.report), joinedload(LabComponent.canonical))
        .all()
    )
    canonical_by_date: dict[int, dict[str, list[LabComponent]]] = defaultdict(lambda: defaultdict(list))
    unmatched_by_date: dict[str, dict[str, list[LabComponent]]] = defaultdict(lambda: defaultdict(list))
    unmatched_display: dict[str, tuple[tuple, str]] = {}
    dates: set[str] = set()

    for component in comps:
        date_key = component.report.collection_time.date().isoformat()
        dates.add(date_key)
        if component.canonical_analyte_id:
            canonical_by_date[component.canonical_analyte_id][date_key].append(component)
            continue
        key = unmatched_key(component.original_name)
        if not key:
            continue
        unmatched_by_date[key][date_key].append(component)
        rank = _rank(component)
        prev = unmatched_display.get(key)
        if prev is None or rank > prev[0]:
            unmatched_display[key] = (rank, component.original_name)

    rows: list[dict[str, Any]] = []
    analytes = db.query(CanonicalAnalyte).order_by(CanonicalAnalyte.id).all()
    for analyte in analytes:
        if analyte.id not in canonical_by_date:
            continue
        rows.append(
            {
                "key": f"analyte:{analyte.id}",
                "kind": "canonical",
                "canonical_analyte_id": analyte.id,
                "display_name": analyte.name,
                "canonical_unit": analyte.ucum,
                "cells": _pick_cells(canonical_by_date[analyte.id]),
            }
        )
    for key in sorted(unmatched_by_date):
        rows.append(
            {
                "key": f"original:{key}",
                "kind": "unmatched",
                "canonical_analyte_id": None,
                "display_name": unmatched_display[key][1],
                "canonical_unit": None,
                "cells": _pick_cells(unmatched_by_date[key]),
            }
        )
    return {"dates": sorted(dates, reverse=True), "rows": rows}


def original_name_trend(db: Session, profile_id: int, name: str) -> dict[str, Any]:
    target = unmatched_key(name)
    comps = (
        db.query(LabComponent)
        .join(LabReport)
        .filter(LabReport.profile_id == profile_id, LabComponent.canonical_analyte_id.is_(None))
        .options(joinedload(LabComponent.report))
        .order_by(LabReport.collection_time)
        .all()
    )
    points = []
    display = name
    for component in comps:
        if unmatched_key(component.original_name) != target:
            continue
        points.append(_point(component))
        display = component.original_name
    return {
        "analyte": display,
        "canonical_unit": None,
        "kind": "unmatched",
        "points": points,
    }
