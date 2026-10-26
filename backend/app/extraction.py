"""Text extraction and deterministic lab line parsing. No model, no network.

A lab result is a test name, a numeric value, and a known lab unit sitting
together on a visual row (or a table row). Letterhead, phones, comments,
and footers never match that shape and are dropped.
"""
import re
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from io import BytesIO

from pypdf import PdfReader
from PIL import Image
import pytesseract
from pdf2image import convert_from_bytes

from .lab_matching import match_analyte, is_plain_number, normalize_test_name

MAX_UPLOAD_BYTES = 50 * 1024 * 1024

# Longest units first so mg/dL is not eaten as g/dL.
LAB_UNITS = [
    "mL/min/1.73m2", "mL/min/1.73 m2", "mL/min/1.73", "10*3/uL", "10^3/uL",
    "10x3/uL", "x10^3/uL", "x10e3/uL", "10e3/uL", "10*6/uL", "10^6/uL",
    "x10^6/uL", "x10e6/uL", "10e6/uL", "cells/uL", "thou/uL", "thous/uL",
    "thous/cmm", "mmol/L", "mmol/l", "mEq/L", "meq/L", "meq/l",
    "umol/L", "umol/l", "µmol/L", "mg/dL", "mg/dl", "g/dL", "g/dl",
    "mg/L", "ug/dL", "µg/dL", "mcg/dL", "ug/mL", "ug/L", "ng/mL", "ng/dL",
    "ng/L", "pg/mL", "pg/dL", "m[IU]/L", "mIU/L", "mIU/mL", "uIU/mL",
    "µIU/mL", "IU/L", "IU/mL", "U/L", "K/uL", "K/µL", "K/cmm", "M/uL",
    "/uL", "/µL", "mm/Hr", "mm/hr", "mL/min", "Thousand/uL", "Million/uL",
    "mg/g creat", "mg/g", "fL", "pg", "sec", "%", "{INR}", "INR",
]
_UNIT_ALTS = "|".join(
    re.escape(u) for u in sorted((u for u in LAB_UNITS if u != "%"), key=len, reverse=True)
)
LAB_UNIT_RE = re.compile(
    r"(?:(?<![A-Za-z0-9])(?:" + _UNIT_ALTS + r")(?![A-Za-z])|(?<=\d)\s*%)",
    re.I,
)
VALUE_RE = re.compile(r"(?<![A-Za-z])([<>≤≥]=?)?-?\d{1,6}(?:,\d{3})*(?:\.\d+)?")
RANGE_RE = re.compile(
    r"[\[(]?\s*(\d+(?:\.\d+)?)\s*[-–—to]+\s*(\d+(?:\.\d+)?)\s*[\])]?",
    re.I,
)
INEQ_RANGE_RE = re.compile(
    r"(?:>\s*or\s*=|<\s*or\s*=|>=|<=|[<>≤≥]=?)\s*\d+(?:\.\d+)?\s*$",
    re.I,
)
LOINC_LINE_RE = re.compile(r"^\(?\d{2,5}-\d{1,2}\)?$")
REF_LABEL_RE = re.compile(r"^reference range:?$", re.I)
STATUS_LINE_RE = re.compile(r"^(FINAL|PEND|PRE|RE|Lab:.*|Analyte|Value)$", re.I)
SITE_CODE_RE = re.compile(r"^[A-Z]{2,3}\d?[A-Z]?$|^[A-Z0-9]{2,4}$")
FLAG_RE = re.compile(r"^(H|L|HH|LL|A|\*|HIGH|LOW|ABN|ABNORMAL|CRIT|CRITICAL)$", re.I)
# % matches too much page copy. Keep it only for tests that are actually percents.
PERCENT_NAME_RE = re.compile(
    r"\b(hct|hematocrit|a1c|hba1c|hemoglobin a1c|rdw|neutrophils?|lymph(ocyte)?s?|"
    r"monos?|eos|basos?|saturation|o2\s*sat|retic|bands|segs|polys|mpv|"
    r"eosinophils?|basophils?|monocytes?)\b",
    re.I,
)

SKIP_NAME_EXACT = {
    "page", "phone", "fax", "tel", "telephone", "age", "dob", "date", "account",
    "patient", "doctor", "provider", "specimen", "requisition", "reported",
    "collected", "printed", "clia", "director", "address", "suite", "street",
    "city", "state", "zip", "www", "http", "https", "note", "comment", "see",
    "final", "copy", "client", "location", "department", "accession", "mrn",
    "sex", "gender", "order", "status", "report", "panel", "test", "result",
    "results", "units", "unit", "flag", "reference", "range", "ref", "lab",
    "laboratory", "npi", "license", "physician", "ordering", "performing",
    "continue", "continued", "end", "of", "id", "name", "sample", "time",
    "drawn", "received", "verified", "technician", "technologist", "method",
    "methodology", "interpretation", "comment", "comments", "footnote",
    "confidential", "hipaa", "accredited", "college", "american", "pathologists",
    "director", "md", "do", "rn", "ph", "ext", "floor", "room", "building",
    "po", "box", "county", "country", "email", "web", "site", "portal",
    "invoice", "bill", "cpt", "icd", "loinc", "code", "regional", "reference",
    "drive", "anytown", "years", "year", "hours", "hour", "minutes",
}
# Any of these in a candidate name means the text is a sentence, not a test.
NAME_STOPWORDS = {
    "between", "without", "someone", "consistent", "confirmed", "follow",
    "additional", "please", "refer", "performing", "copyright", "increased",
    "decreased", "optimal", "desirable", "according", "guidelines", "deficiency",
    "while", "levels", "copied", "originally", "reported", "client", "split",
    "suite", "wellness", "trademarks", "registered", "currently", "consensus",
    "regarding", "children", "assay", "patients", "ages", "option", "treatment",
    "target", "known", "indicative", "suggest", "endogenous", "measurement",
    "diabetes", "value", "and", "with", "from", "this", "that", "for", "the",
    "a", "an", "is", "are", "was", "were", "to", "or", "by", "on", "in",
    "should", "be",
}
SKIP_LINE = re.compile(
    r"(clia\s*#|npi\s*#|www\.|https?://|@|"
    r"laboratory director|performing lab|end of report|"
    r"page\s+\d+(\s+of\s+\d+)?|"
    r"confidential|hipaa|not a medical device|"
    r"please (see|refer)|see comment|see note|"
    r"this test was (perform|develop)|"
    r"college of american|accredited by|"
    r"final report|preliminary report|"
    r"specimen (id|type)|requisition|accession|"
    r"date of birth|\bdob\b|"
    r"phone:|fax:|tel:)",
    re.I,
)
RESULT_HEADER = re.compile(
    r"(test\s*name|analyte|result|reference\s*range|ref\s*range|"
    r"complete metabolic|comprehensive metabolic|basic metabolic|"
    r"lipid panel|lipid profile|cbc|hemoglobin a1c|lab results|"
    r"current results|component\s+results)",
    re.I,
)
RESULT_END = re.compile(
    r"^(comments?|interpretation|method(ology)?|performing lab|"
    r"end of report|footnotes?|notes?:)\b",
    re.I,
)
PANEL_NAMES = [
    (re.compile(r"comprehensive metabolic|cmp\b", re.I), "CMP"),
    (re.compile(r"complete metabolic", re.I), "CMP"),
    (re.compile(r"basic metabolic|bmp\b", re.I), "BMP"),
    (re.compile(r"lipid (panel|profile)", re.I), "Lipid Panel"),
    (re.compile(r"\bcbc\b|complete blood count", re.I), "CBC"),
    (re.compile(r"hemoglobin a1c|hba1c", re.I), "Hemoglobin A1c"),
    (re.compile(r"thyroid|tsh", re.I), "Thyroid"),
    (re.compile(r"hepatic|liver (panel|function)", re.I), "Hepatic Function"),
]


def extract_text_from_pdf(data: bytes) -> Tuple[str, int, bool]:
    """Return (text, page_count, ocr_used). Visual rows first; OCR pages that need it."""
    plumber_text, page_count = _pdfplumber_extract(data)
    pypdf_text, pypdf_pages = _pypdf_extract(data)
    if pypdf_pages:
        page_count = pypdf_pages
    text = _best_text(plumber_text, pypdf_text)
    ocr_used = False
    if _page_needs_ocr(text):
        ocr_text = _ocr_pdf(data)
        if ocr_text.strip():
            ocr_used = True
            if _score_text(ocr_text) > _score_text(text):
                text = ocr_text
            elif text.strip():
                text = text + "\n" + ocr_text
    return text, page_count or 1, ocr_used


def _score_text(text: str) -> Tuple[int, int]:
    t = text or ""
    return (len(LAB_UNIT_RE.findall(t)), len(t.strip()))


def _best_text(a: str, b: str) -> str:
    if _score_text(a) >= _score_text(b):
        return a or b
    return b or a


def _pdfplumber_extract(data: bytes) -> Tuple[str, int]:
    try:
        import pdfplumber
    except Exception:
        return "", 0
    try:
        pages_out: List[str] = []
        with pdfplumber.open(BytesIO(data)) as pdf:
            for page in pdf.pages:
                visual = _visual_rows(page)
                table_lines: List[str] = []
                try:
                    for tbl in page.extract_tables() or []:
                        table_lines.extend(_table_as_lines(tbl))
                except Exception:
                    pass
                block = visual
                if table_lines:
                    existing = visual.lower()
                    extra = [ln for ln in table_lines if ln.lower() not in existing]
                    if extra:
                        block = (visual + "\n" if visual else "") + "\n".join(extra)
                pages_out.append(block)
            return "\n\n".join(pages_out), len(pdf.pages)
    except Exception:
        return "", 0


def _visual_rows(page) -> str:
    try:
        words = page.extract_words(x_tolerance=3, y_tolerance=4, keep_blank_chars=False) or []
    except Exception:
        words = []
    if not words:
        try:
            return page.extract_text(layout=True) or page.extract_text() or ""
        except Exception:
            return ""
    words = sorted(words, key=lambda w: (float(w["top"]), float(w["x0"])))
    rows = []
    current = [words[0]]
    for w in words[1:]:
        if abs(float(w["top"]) - float(current[0]["top"])) <= 4:
            current.append(w)
        else:
            rows.append(_join_words(current))
            current = [w]
    rows.append(_join_words(current))
    return "\n".join(rows)


def _join_words(words: list) -> str:
    words = sorted(words, key=lambda w: float(w["x0"]))
    parts = [words[0]["text"]]
    for prev, w in zip(words, words[1:]):
        gap = float(w["x0"]) - float(prev["x1"])
        parts.append("  " if gap > 6 else " ")
        parts.append(w["text"])
    return "".join(parts)


def _table_as_lines(table: list) -> List[str]:
    if not table:
        return []
    header_map = _table_header_map(table[0])
    start = 1 if header_map else 0
    lines = []
    for raw in table[start:]:
        cells = [" ".join(((c or "").replace("\n", " ")).split()) for c in raw]
        if header_map:
            name = _idx(cells, header_map.get("name"))
            value = _idx(cells, header_map.get("value"))
            flag = _idx(cells, header_map.get("flag"))
            unit = _idx(cells, header_map.get("unit"))
            ref = _idx(cells, header_map.get("range"))
            if name and value:
                lines.append("  ".join(p for p in (name, value, flag, unit, ref) if p))
                continue
        joined = "  ".join(c for c in cells if c)
        if joined:
            lines.append(joined)
    return lines


def _idx(cells: List[str], i: Optional[int]) -> str:
    if i is None or i < 0 or i >= len(cells):
        return ""
    return cells[i]


def _table_header_map(header_row) -> Dict[str, int]:
    if not header_row:
        return {}
    found: Dict[str, int] = {}
    for i, raw in enumerate(header_row):
        h = " ".join(((raw or "").replace("\n", " ")).split()).lower()
        if not h:
            continue
        if re.search(r"test|analyte|component|description|name", h) and "name" not in found:
            found["name"] = i
        elif re.search(r"^(result|value|in range)$|result|value", h) and "value" not in found:
            if "range" in h or "ref" in h:
                found.setdefault("range", i)
            else:
                found["value"] = i
        elif re.search(r"unit", h) and "unit" not in found:
            found["unit"] = i
        elif re.search(r"range|interval|reference|ref\b", h) and "range" not in found:
            found["range"] = i
        elif re.search(r"flag|abn", h) and "flag" not in found:
            found["flag"] = i
    if "name" in found and "value" in found:
        return found
    return {}


def _pypdf_extract(data: bytes) -> Tuple[str, int]:
    try:
        reader = PdfReader(BytesIO(data))
    except Exception:
        return "", 0
    texts = []
    for page in reader.pages:
        texts.append(_page_text(page))
    return "\n\n".join(texts), len(reader.pages)


def _ocr_pdf(data: bytes) -> str:
    texts = []
    try:
        images = convert_from_bytes(data, dpi=200)
    except Exception:
        return ""
    for img in images:
        try:
            texts.append(pytesseract.image_to_string(img, config="--psm 6"))
        except Exception:
            continue
    return "\n\n".join(texts)


def _page_text(page) -> str:
    raw = ""
    layout = ""
    try:
        layout = page.extract_text(extraction_mode="layout") or ""
    except TypeError:
        layout = ""
    try:
        raw = page.extract_text() or ""
    except Exception:
        raw = ""
    if layout.count("\n") >= raw.count("\n") and len(layout.strip()) >= max(20, int(len(raw.strip()) * 0.4)):
        return layout
    return raw or layout


def _page_needs_ocr(text: str) -> bool:
    stripped = (text or "").strip()
    if len(stripped) < 80:
        return True
    if LAB_UNIT_RE.search(stripped):
        return False
    if VALUE_RE.search(stripped) and re.search(r"[A-Za-z]{3,}", stripped):
        return False
    return True


def extract_text_from_image(data: bytes, mime: str) -> Tuple[str, int, bool]:
    img = Image.open(BytesIO(data))
    text = pytesseract.image_to_string(img, config="--psm 6")
    return text, 1, True


def extract_text_from_plain(data: bytes) -> Tuple[str, int, bool]:
    text = data.decode("utf-8", errors="replace")
    return text, 1, False


def extract_document_text(data: bytes, mime: str, filename: str) -> Tuple[str, int, bool]:
    mime = (mime or "").lower()
    if mime == "application/pdf" or filename.lower().endswith(".pdf"):
        return extract_text_from_pdf(data)
    if mime.startswith("image/") or filename.lower().endswith((".tif", ".tiff", ".jpg", ".jpeg", ".png")):
        return extract_text_from_image(data, mime)
    if mime in ("text/plain", "text/markdown") or filename.lower().endswith((".txt", ".md", ".markdown")):
        return extract_text_from_plain(data)
    if mime in ("text/xml", "application/xml") or filename.lower().endswith(".xml"):
        return extract_text_from_plain(data)
    return "", 0, False


DATE_PATTERNS = [
    re.compile(
        r"(?:date\s*)?(?:collected|collection|drawn|specimen(?:\s+date)?|"
        r"coll(?:ected)?(?:\s*date)?|date/time\s*collected)\s*[:#]?\s*"
        r"(\d{4}-\d{2}-\d{2}(?:[ T]\d{1,2}:\d{2})?|\d{1,2}/\d{1,2}/\d{2,4}(?:\s+\d{1,2}:\d{2})?)",
        re.I,
    ),
]


def find_collection_date(text: str) -> Optional[datetime]:
    """Only labeled collection/drawn dates. Unlabeled dates are not confident enough to auto-file."""
    for pat in DATE_PATTERNS:
        m = pat.search(text or "")
        if not m:
            continue
        s = m.group(1).strip()
        s = re.sub(r"[ T](\d{1,2}:\d{2}).*$", "", s)
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
    return None


def detect_panel_name(text: str) -> str:
    for pat, name in PANEL_NAMES:
        if pat.search(text or ""):
            return name
    return "Imported Panel"


def _collapse(line: str) -> str:
    return re.sub(r"[ \t]+", " ", (line or "").strip())


def _is_boilerplate(line: str) -> bool:
    s = line.strip()
    if not s:
        return True
    if SKIP_LINE.search(s):
        return True
    if len(s) > 160:
        return True
    if re.fullmatch(r"[-_=.*]{3,}", s):
        return True
    return False


def _looks_like_test_name(name: str) -> bool:
    n = normalize_test_name(name)
    if not n or len(n) < 2 or len(n) > 55:
        return False
    if not re.match(r"[A-Za-z]", n):
        return False
    words = [w.lower().strip(".,:;#") for w in n.split() if w.strip(".,:;#")]
    if not words:
        return False
    if words[0] in SKIP_NAME_EXACT:
        return False
    if any(w in NAME_STOPWORDS for w in words):
        return False
    if re.search(r"\d{5,}", n):
        return False
    letters = sum(ch.isalpha() for ch in n)
    if letters < 2:
        return False
    return True


def _canon_unit(unit: str) -> str:
    raw = (unit or "").strip()
    key = raw.replace("µ", "u").replace("μ", "u").replace(" ", "")
    mapping = {
        "mmol/l": "mmol/L",
        "meq/l": "mEq/L",
        "mg/dl": "mg/dL",
        "g/dl": "g/dL",
        "u/l": "U/L",
        "iu/l": "IU/L",
        "{inr}": "{INR}",
        "inr": "{INR}",
        "k/ul": "K/uL",
        "10*3/ul": "10*3/uL",
        "10^3/ul": "10*3/uL",
        "x10^3/ul": "10*3/uL",
        "x10e3/ul": "10*3/uL",
        "10e3/ul": "10*3/uL",
        "miu/l": "mIU/L",
        "m[iu]/l": "mIU/L",
        "thousand/ul": "10*3/uL",
        "million/ul": "10*6/uL",
        "mg/gcreat": "mg/g",
    }
    return mapping.get(key.lower(), raw)


def _split_tokens(line: str) -> List[str]:
    s = line.replace("–", "-").replace("—", "-")
    s = re.sub(r"(\d)\s*-\s*(\d)", r"\1-\2", s)
    return s.split()


def _parse_after_unit(after: str) -> Tuple[Optional[str], Optional[float], Optional[float], Optional[str], str]:
    flag = None
    ref_low = ref_high = None
    ref_text = None
    tokens = _split_tokens(after)
    if tokens and FLAG_RE.match(tokens[0]):
        flag = tokens.pop(0)
    after = " ".join(tokens)
    rm = RANGE_RE.search(after)
    if rm:
        ref_low = float(rm.group(1))
        ref_high = float(rm.group(2))
        ref_text = f"{rm.group(1)}-{rm.group(2)}"
        after = (after[: rm.start()] + after[rm.end():]).strip()
    elif after.strip() and after.strip().lower() not in ("see note", "see comment", "tnp", "n/a"):
        leftover = after.strip(" :|")
        if leftover and not FLAG_RE.match(leftover) and len(leftover) <= 40 and not LAB_UNIT_RE.search(leftover):
            code = leftover.split()[0] if leftover.split() else leftover
            if not SITE_CODE_RE.match(code):
                ref_text = leftover
    return flag, ref_low, ref_high, ref_text, after


def _name_from_left(left: str) -> Optional[str]:
    left = left.replace("|", " ").replace(";", " ")
    left = left.split("\n")[-1].strip()
    parts = [p.strip() for p in re.split(r"\s{2,}", left) if p.strip()]
    left = parts[-1] if parts else ""
    words = _split_tokens(left)
    cleaned = []
    for w in words:
        if re.fullmatch(r"\d{1,4}[/-]\d{1,2}[/-]\d{2,4}", w):
            cleaned = []
            continue
        if re.fullmatch(r"\d{1,2}:\d{2}", w):
            continue
        if w.lower().strip(".:") in SKIP_NAME_EXACT:
            cleaned = []
            continue
        cleaned.append(w)
    name = " ".join(cleaned[-6:]).strip(" :|-")
    name = re.sub(r"\(\d{2,5}-\d{1,2}\)", "", name).strip(" :|-")
    if _looks_like_test_name(name):
        return name
    return None


def _peel_trailing_range(left: str) -> Tuple[str, Optional[float], Optional[float], Optional[str]]:
    """If the reference range sat to the left of the unit, do not treat 145 as the result."""
    s = left.rstrip()
    last = None
    for m in RANGE_RE.finditer(s):
        if s[m.end():].strip() == "":
            last = m
    if last:
        return (
            s[: last.start()],
            float(last.group(1)),
            float(last.group(2)),
            f"{last.group(1)}-{last.group(2)}",
        )
    ineq = INEQ_RANGE_RE.search(s)
    if ineq and list(VALUE_RE.finditer(s[: ineq.start()])):
        return s[: ineq.start()], None, None, ineq.group(0).strip()
    return left, None, None, None


def _row_from_unit_match(text: str, unit_m: re.Match) -> Optional[Dict[str, Any]]:
    unit = _canon_unit(unit_m.group(0))
    window_start = max(0, unit_m.start() - 90)
    left = text[window_start: unit_m.start()]
    if re.search(r"(phone|fax|tel|clia|npi|page|www)\s*[:#]?\s*$", left, re.I):
        return None
    peeled_low = peeled_high = None
    peeled_text = None
    left, peeled_low, peeled_high, peeled_text = _peel_trailing_range(left)
    values = list(VALUE_RE.finditer(left))
    if not values:
        return None
    value_m = values[-1]
    between = left[value_m.end():]
    if not re.fullmatch(
        r"[\s,|/]*(H|L|HH|LL|HIGH|LOW)?[\s,|/]*(reference\s*range:?)?[\s,|/]*",
        between,
        re.I,
    ):
        return None
    flag = None
    fm = re.search(r"\b(H|L|HH|LL|HIGH|LOW)\b", between, re.I)
    if fm:
        flag = fm.group(1)
    name_src = left[: value_m.start()]
    name = _name_from_left(name_src)
    if not name:
        prior = name_src.rstrip().rsplit("\n", 1)
        if len(prior) == 2:
            name = _name_from_left(prior[0])
    if not name:
        return None
    if unit == "%" and not PERCENT_NAME_RE.search(name):
        return None
    value = value_m.group(0).replace(",", "")
    if re.fullmatch(r"19\d{2}|20\d{2}", value) and unit.lower() not in ("u/l", "iu/l"):
        return None
    after = text[unit_m.end(): unit_m.end() + 40]
    nxt = LAB_UNIT_RE.search(after)
    if nxt:
        after = after[: nxt.start()]
    a_flag, ref_low, ref_high, ref_text, _ = _parse_after_unit(after)
    quote_start = max(window_start, value_m.start() - 40)
    quote = _collapse(text[quote_start: unit_m.end() + 24])
    return {
        "original_name": name,
        "value_text": value,
        "unit_original": unit,
        "ref_low": ref_low if ref_low is not None else peeled_low,
        "ref_high": ref_high if ref_high is not None else peeled_high,
        "ref_text": ref_text or peeled_text,
        "printed_flag": flag or a_flag,
        "quote": quote[:120],
    }


def parse_result_line(line: str) -> Optional[Dict[str, Any]]:
    """Parse one line into a lab result. None if it is not result-shaped."""
    line = _collapse(line)
    if _is_boilerplate(line):
        return None
    unit_m = LAB_UNIT_RE.search(line)
    if not unit_m:
        return None
    return _row_from_unit_match(line, unit_m)


def _result_zone(lines: List[str]) -> List[str]:
    start = 0
    saw_header = False
    for i, line in enumerate(lines):
        if not RESULT_HEADER.search(line):
            continue
        looks_like_header_row = (
            not LAB_UNIT_RE.search(line)
            or re.search(r"\b(units?|reference|test name|ref range)\b", line, re.I)
        )
        if looks_like_header_row:
            start = i + 1
            saw_header = True
            break
    out = []
    for line in lines[start:]:
        if saw_header and RESULT_END.match(line.strip()):
            break
        out.append(line)
    return out if out else lines


def _should_join_name_line(prev: str, line: str) -> bool:
    prev = prev.strip()
    if not prev or not _looks_like_test_name(prev):
        return False
    if LAB_UNIT_RE.search(prev) or VALUE_RE.search(prev):
        return False
    if _is_boilerplate(prev):
        return False
    if not LAB_UNIT_RE.search(line):
        return False
    return True


def _annotate(row: Dict[str, Any], analytes: list) -> Dict[str, Any]:
    matched = match_analyte(row["original_name"], analytes)
    row["matched"] = matched is not None
    row["analyte_id"] = matched.id if matched else None
    row["plain_number"] = is_plain_number(row["value_text"])
    return row


def _dedupe(parsed: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    unique = []
    for row in parsed:
        key = (
            normalize_test_name(row["original_name"]).lower(),
            row["value_text"],
            (row["unit_original"] or "").lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


VALUE_LINE_RE = re.compile(
    r"^([<>≤≥]=?)?-?\d{1,6}(?:,\d{3})*(?:\.\d+)?(?:\s+(H|L|HH|LL|HIGH|LOW))?$",
    re.I,
)


def _unit_from_line(line: str) -> Optional[str]:
    s = re.sub(r"\(calc\)", "", line, flags=re.I).strip()
    if s == "%":
        return "%"
    m = LAB_UNIT_RE.search(s)
    if not m:
        return None
    rest = (s[: m.start()] + s[m.end() :]).strip()
    if rest:
        return None
    return _canon_unit(m.group(0))


def _range_from_line(line: str) -> Tuple[Optional[float], Optional[float], Optional[str]]:
    s = (line or "").strip()
    if not s or s.lower() in ("see note:", "see note", "see comment", "tnp", "n/a"):
        return None, None, s or None
    rm = RANGE_RE.fullmatch(s) or RANGE_RE.search(s)
    if rm and s[rm.end() :].strip() == "" and s[: rm.start()].strip() == "":
        return float(rm.group(1)), float(rm.group(2)), f"{rm.group(1)}-{rm.group(2)}"
    ineq = INEQ_RANGE_RE.search(s)
    if ineq and s[: ineq.start()].strip() == "":
        return None, None, ineq.group(0).strip()
    return None, None, None


def _coalesce_quest_lines(text: str) -> List[str]:
    """Join Quest text boxes so '(', '2345-7', ')' becomes one LOINC line."""
    raw = [_collapse(l) for l in (text or "").split("\n")]
    raw = [l for l in raw if l]
    out: List[str] = []
    i = 0
    while i < len(raw):
        if (
            raw[i] == "("
            and i + 2 < len(raw)
            and re.fullmatch(r"\d{2,5}-\d{1,2}", raw[i + 1])
            and raw[i + 2] == ")"
        ):
            out.append(f"({raw[i + 1]})")
            i += 3
            continue
        out.append(raw[i])
        i += 1
    return out


def _parse_stacked_blocks(text: str) -> List[Dict[str, Any]]:
    """Quest-style reports print name, value, 'Reference Range', then unit on separate lines."""
    lines = _coalesce_quest_lines(text)
    out: List[Dict[str, Any]] = []
    i = 0
    while i < len(lines):
        name = re.sub(r"\(\d{2,5}-\d{1,2}\)", "", lines[i]).strip(" :|-")
        j = i + 1
        if j < len(lines) and LOINC_LINE_RE.match(lines[j]):
            j += 1
        if j >= len(lines):
            i += 1
            continue
        vm = VALUE_LINE_RE.match(lines[j])
        if not vm or not _looks_like_test_name(name):
            i += 1
            continue
        value = vm.group(0)
        flag = None
        fm = re.search(r"\s(H|L|HH|LL|HIGH|LOW)$", value, re.I)
        if fm:
            flag = fm.group(1)
            value = value[: fm.start()].strip()
        k = j + 1
        ref_low = ref_high = None
        ref_text = None
        if k < len(lines) and REF_LABEL_RE.match(lines[k]):
            k += 1
            if k < len(lines):
                ref_low, ref_high, maybe = _range_from_line(lines[k])
                if maybe is not None or ref_low is not None:
                    ref_text = maybe
                    k += 1
        unit = None
        if k < len(lines):
            unit = _unit_from_line(lines[k])
            if unit:
                k += 1
        if not unit and re.fullmatch(r"INR", name, re.I):
            unit = "{INR}"
        if not unit:
            i += 1
            continue
        if unit == "%" and not PERCENT_NAME_RE.search(name):
            i += 1
            continue
        quote = _collapse(" ".join(lines[i:k]))[:120]
        out.append({
            "original_name": name,
            "value_text": value.replace(",", ""),
            "unit_original": unit,
            "ref_low": ref_low,
            "ref_high": ref_high,
            "ref_text": ref_text,
            "printed_flag": flag,
            "quote": quote,
        })
        while k < len(lines) and STATUS_LINE_RE.match(lines[k]):
            k += 1
        i = max(k, i + 1)
    return out


INR_LINE_RE = re.compile(
    r"^INR(?:\s*\(\d{2,5}-\d{1,2}\))?\s+([<>]?\d+(?:\.\d+)?)(?:\s+(H|L))?(?:\s+FINAL)?$",
    re.I,
)


def _parse_inr_lines(text: str) -> List[Dict[str, Any]]:
    out = []
    for line in _coalesce_quest_lines(text):
        m = INR_LINE_RE.match(line)
        if not m:
            continue
        out.append({
            "original_name": "INR",
            "value_text": m.group(1),
            "unit_original": "{INR}",
            "ref_low": None,
            "ref_high": None,
            "ref_text": None,
            "printed_flag": m.group(2),
            "quote": line[:120],
        })
    return out


def parse_lab_lines(text: str, analytes: list) -> List[Dict[str, Any]]:
    """Return lab-result-shaped rows only. Letterhead, phones, comments are dropped."""
    text = (text or "").replace("\r", "")
    lines = text.split("\n")
    zone = _result_zone(lines)
    parsed: List[Dict[str, Any]] = []

    for row in _parse_stacked_blocks("\n".join(zone)):
        parsed.append(_annotate(row, analytes))
    for row in _parse_inr_lines("\n".join(zone)):
        parsed.append(_annotate(row, analytes))

    def consume(fragment: str) -> None:
        if not fragment.strip():
            return
        for unit_m in LAB_UNIT_RE.finditer(fragment):
            line_start = fragment.rfind("\n", 0, unit_m.start()) + 1
            line_end = fragment.find("\n", unit_m.end())
            if line_end < 0:
                line_end = len(fragment)
            line = fragment[line_start:line_end]
            if _is_boilerplate(line) and not VALUE_RE.search(line):
                continue
            row = _row_from_unit_match(fragment, unit_m)
            if row:
                parsed.append(_annotate(row, analytes))

    for i, line in enumerate(zone):
        if not line.strip():
            continue
        fragment = line
        prev = zone[i - 1] if i else ""
        if _should_join_name_line(prev, line):
            fragment = prev.strip() + "  " + line
        if _is_boilerplate(line) and not (VALUE_RE.search(line) and LAB_UNIT_RE.search(line)):
            continue
        consume(fragment)

    # One-blob PDFs only. Walking a whole Quest page treats comment sentences as results.
    if not parsed and zone and sum(1 for l in zone if l.strip()) <= 3:
        consume("\n".join(zone))

    return _dedupe(parsed)
