"""Phase 13: tell lab documents from imaging narratives, and pull imaging fields.

Deterministic and keyword-based (no model). Imaging fields are copied from the
report text as printed; this does not interpret findings.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from .extraction import LAB_UNIT_RE, PANEL_NAMES

MAX_FIELD_CHARS = 20000
QUOTE_CHARS = 240

# Standing-spec modality codes. Short codes only count in the filename or on the
# exam line: "US" and "MR" in letterhead are a country and a medical record.
MODALITY_CODES = {
    "DX": "X-ray", "CT": "CT", "MR": "MRI", "US": "Ultrasound", "MG": "Mammography",
    "NM": "Nuclear medicine", "PT": "PET", "XA": "Fluoroscopy / angiography",
    "DXA": "Bone density (DXA)", "OT": "Other",
}
# Order matters: DXA before DX-ish words, PET before CT ("PET/CT" is PET).
_SHORT_MODALITY = [
    ("DXA", r"dxa|dexa"),
    ("PT", r"pet"),
    ("MG", r"mg|mammo"),
    ("DX", r"xr|cxr|cr|dx|xray|x-ray"),
    ("CT", r"ct|cat|cta"),
    ("MR", r"mri?|mra"),
    ("US", r"us|usg"),
    ("NM", r"nm"),
    ("XA", r"xa|fluoro"),
]
_LONG_MODALITY = [
    ("DXA", r"bone density|dexa\b|\bdxa\b"),
    ("PT", r"\bpet\b|positron emission"),
    ("MG", r"mammogra"),
    ("DX", r"radiograph|x-ray|\bxray\b"),
    ("CT", r"computed tomography|\bct scan"),
    ("MR", r"magnetic resonance|\bmri\b"),
    ("US", r"ultrasound|sonogra|doppler"),
    ("NM", r"nuclear medicine|scintigra"),
    ("XA", r"fluoroscop|angiogra"),
]
SHORT_MODALITY_RE = [(code, re.compile(r"(?<![a-z0-9])(?:" + pat + r")(?![a-z0-9])", re.I)) for code, pat in _SHORT_MODALITY]
LONG_MODALITY_RE = [(code, re.compile(pat, re.I)) for code, pat in _LONG_MODALITY]

HEADINGS = (
    "findings", "impression", "technique", "comparison", "history", "clinical history",
    "indication", "indications", "exam", "examination", "procedure", "conclusion",
    "reason for exam", "clinical information",
)
HEADING_RE = re.compile(
    r"^[ \t]*(" + "|".join(sorted((re.escape(h) for h in HEADINGS), key=len, reverse=True)) + r")[ \t]*(?::|$)",
    re.I | re.M,
)
END_RE = re.compile(
    r"^[ \t]*(?:end of report|electronically signed|signed by|dictated by|interpreted by|"
    r"reading radiologist|reported by|radiologist)\b",
    re.I | re.M,
)
EXAM_LINE_RE = re.compile(r"^[ \t]*(?:exam|examination|procedure|study)[ \t]*:[ \t]*(.+)$", re.I | re.M)

# Longest first so "abdomen and pelvis" beats "abdomen".
BODY_SITES = [
    ("abdomen and pelvis", r"abd(?:omen)?\s*(?:and|&|/)\s*pelvis"),
    ("cervical spine", r"c-?spine|cervical spine"),
    ("thoracic spine", r"t-?spine|thoracic spine"),
    ("lumbar spine", r"l-?spine|lumbar spine|lumbosacral"),
    ("chest", r"chest|thorax|\blungs?\b"),
    ("abdomen", r"abdomen|abdominal"),
    ("pelvis", r"pelvis|pelvic"),
    ("brain", r"brain"),
    ("head", r"\bhead\b|skull"),
    ("neck", r"\bneck\b|soft tissue neck"),
    ("sinuses", r"sinus"),
    ("shoulder", r"shoulder"),
    ("elbow", r"elbow"),
    ("wrist", r"wrist"),
    ("hand", r"\bhand\b"),
    ("hip", r"\bhips?\b"),
    ("knee", r"\bknees?\b"),
    ("ankle", r"ankle"),
    ("foot", r"\bfoot\b|\bfeet\b"),
    ("breast", r"breast"),
    ("thyroid", r"thyroid"),
    ("kidney", r"kidney|renal"),
    ("heart", r"cardiac|\bheart\b|echocardiogra"),
]
BODY_SITE_RE = [(site, re.compile(pat, re.I)) for site, pat in BODY_SITES]
LATERALITY_RE = [
    ("bilateral", re.compile(r"\bbilateral\b|\bbilat\b|\bboth\b", re.I)),
    ("left", re.compile(r"\bleft\b|\blt\b", re.I)),
    ("right", re.compile(r"\bright\b|\brt\b", re.I)),
]

_DATE_VALUE = r"(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})"
PERFORMED_DATE_RE = re.compile(
    r"(?:exam(?:ination)?\s*date|date\s*of\s*(?:exam(?:ination)?|study|service|procedure)|"
    r"study\s*date|performed(?:\s*(?:on|date))?|date\s*performed|exam\s*performed)\s*[:#]?\s*" + _DATE_VALUE,
    re.I,
)
FILENAME_DATE_RE = re.compile(r"(?<!\d)(\d{4}-\d{2}-\d{2})(?!\d)")
FACILITY_RE = re.compile(r"^[ \t]*(?:facility|location|performing (?:site|facility))[ \t]*:[ \t]*(.+)$", re.I | re.M)
PROVIDER_RE = re.compile(
    r"(?:electronically signed by|signed by|dictated by|interpreted by|reading radiologist|"
    r"reported by|radiologist)[ \t]*:?[ \t]*([^\n,;]{3,80})",
    re.I,
)

LAB_TITLE_RE = re.compile(r"lab(?:oratory)? results?|metabolic panel", re.I)


def _filename_words(filename: str) -> str:
    stem = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", filename or "")
    return re.sub(r"[_.\-+]+", " ", stem).replace("x ray", "xray")


def lab_unit_density(text: str) -> float:
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    if not lines:
        return 0.0
    hits = sum(1 for ln in lines if LAB_UNIT_RE.search(ln))
    return hits / len(lines)


def _heading_names(text: str) -> set:
    return {m.group(1).lower() for m in HEADING_RE.finditer(text or "")}


def filename_modality(filename: str) -> Optional[str]:
    words = _filename_words(filename)
    for code, rx in SHORT_MODALITY_RE:
        if rx.search(words):
            return code
    for code, rx in LONG_MODALITY_RE:
        if rx.search(words):
            return code
    return None


def text_modality(text: str) -> Optional[str]:
    for m in EXAM_LINE_RE.finditer(text or ""):
        line = m.group(1)
        for code, rx in SHORT_MODALITY_RE + LONG_MODALITY_RE:
            if rx.search(line):
                return code
    for code, rx in LONG_MODALITY_RE:
        if rx.search(text or ""):
            return code
    return None


def imaging_signal(filename: str, text: str, lab_lines: int = 0) -> bool:
    """True when the file reads as a radiology report.

    A file with parsed lab lines needs report headings too, so a lipid panel with an
    "Impression" comment or a lab packet named "CT follow-up labs" keeps only its labs.
    """
    heads = _heading_names(text)
    report_heads = bool(heads & {"findings", "impression", "conclusion"})
    if lab_lines:
        return report_heads and ("findings" in heads or "technique" in heads) and text_modality(text) is not None
    if filename_modality(filename):
        return True
    if report_heads and lab_unit_density(text) < 0.2:
        return len(heads) >= 2 or text_modality(text) is not None
    return False


def classify_document(filename: str, text: str, lab_lines: Optional[int] = None) -> str:
    """'lab' | 'imaging' | 'unknown'. Pass lab_lines (parsed row count) when known."""
    if lab_lines is None:
        titled = any(rx.search(text or "") for rx, _ in PANEL_NAMES) or LAB_TITLE_RE.search(text or "")
        lab_lines = 1 if titled and lab_unit_density(text) >= 0.2 else 0
    if imaging_signal(filename, text, lab_lines):
        return "imaging"
    if lab_lines:
        return "lab"
    return "unknown"


def _section(text: str, name: str) -> Optional[str]:
    """Body under NAME: until the next heading, an end-of-report line, or the end."""
    for m in HEADING_RE.finditer(text):
        if m.group(1).lower() != name:
            continue
        start = m.end()
        nxt = HEADING_RE.search(text, start)
        end_m = END_RE.search(text, start)
        stop = min(x.start() for x in (nxt, end_m) if x) if (nxt or end_m) else len(text)
        body = text[start:stop].strip()
        return body[:MAX_FIELD_CHARS] or None
    return None


def _date(s: str) -> Optional[datetime]:
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _performed_at(text: str, filename: str) -> Optional[datetime]:
    m = PERFORMED_DATE_RE.search(text or "")
    if m and _date(m.group(1)):
        return _date(m.group(1))
    # A leading ISO date in the filename is the owner's own label for the exam.
    m = FILENAME_DATE_RE.search(filename or "")
    return _date(m.group(1)) if m else None


def _site_and_side(sources: List[str]) -> tuple:
    for src in sources:
        for site, rx in BODY_SITE_RE:
            m = rx.search(src)
            if not m:
                continue
            window = src[max(0, m.start() - 30): m.end() + 30]
            side = next((name for name, lrx in LATERALITY_RE if lrx.search(window)), None)
            return site, side
    return None, None


def _split_reports(text: str) -> List[str]:
    """One chunk per IMPRESSION heading; a single report stays whole."""
    imps = [m for m in HEADING_RE.finditer(text) if m.group(1).lower() in ("impression", "conclusion")]
    if len(imps) <= 1:
        return [text]
    chunks, prev = [], 0
    for i, m in enumerate(imps):
        limit = imps[i + 1].start() if i + 1 < len(imps) else len(text)
        nxt = HEADING_RE.search(text, m.end(), limit)
        end = nxt.start() if nxt else limit
        chunks.append(text[prev:end])
        prev = end
    chunks[-1] += text[prev:]
    return chunks


def extract_imaging_reports(filename: str, text: str) -> List[Dict[str, Any]]:
    """Payloads for imaging_report proposals: modality code, site, side, date, findings, impression."""
    text = text or ""
    out = []
    for chunk in _split_reports(text):
        exam_lines = [m.group(1) for m in EXAM_LINE_RE.finditer(chunk)]
        modality = text_modality(chunk) if exam_lines else None
        modality = modality or filename_modality(filename) or text_modality(chunk) or "OT"
        site, side = _site_and_side([_filename_words(filename)] + exam_lines + [chunk])
        findings = _section(chunk, "findings")
        impression = _section(chunk, "impression") or _section(chunk, "conclusion")
        performed = _performed_at(chunk, filename) or _performed_at(text, filename)
        fac = FACILITY_RE.search(chunk) or FACILITY_RE.search(text)
        prov = PROVIDER_RE.search(chunk)
        quote_src = impression or findings or ""
        out.append({
            "modality": modality,
            "modality_label": MODALITY_CODES.get(modality, modality),
            "body_site": site,
            "laterality": side,
            "performed_at": performed.date().isoformat() if performed else None,
            "exam": exam_lines[0].strip()[:200] if exam_lines else None,
            "findings": findings,
            "impression": impression,
            "facility": fac.group(1).strip()[:200] if fac else None,
            "reporting_provider": prov.group(1).strip() if prov else None,
            "quote": re.sub(r"\s+", " ", quote_src)[:QUOTE_CHARS].strip() or None,
        })
    return out
