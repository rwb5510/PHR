"""Text extraction and deterministic lab line parsing. No model, no network."""
import os
import re
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from io import BytesIO

from pypdf import PdfReader
from PIL import Image
import pytesseract
from pdf2image import convert_from_bytes

from .lab_matching import match_analyte, is_plain_number, normalize_unit

# Size limit
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB

def extract_text_from_pdf(data: bytes) -> Tuple[str, int, bool]:
    """Return (text, page_count, ocr_used)."""
    reader = PdfReader(BytesIO(data))
    page_count = len(reader.pages)
    texts = []
    ocr_used = False
    for i, page in enumerate(reader.pages):
        t = page.extract_text() or ""
        if len(t.strip()) < 20:  # almost no text
            # OCR this page
            try:
                images = convert_from_bytes(data, first_page=i+1, last_page=i+1, dpi=150)
                if images:
                    ocr_text = pytesseract.image_to_string(images[0])
                    texts.append(ocr_text)
                    ocr_used = True
                else:
                    texts.append(t)
            except Exception:
                texts.append(t)
        else:
            texts.append(t)
    return "\n\n".join(texts), page_count, ocr_used

def extract_text_from_image(data: bytes, mime: str) -> Tuple[str, int, bool]:
    img = Image.open(BytesIO(data))
    text = pytesseract.image_to_string(img)
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
    # XML stored, text shown (no clinical parse)
    if mime in ("text/xml", "application/xml") or filename.lower().endswith(".xml"):
        return extract_text_from_plain(data)
    return "", 0, False

# Date patterns
DATE_PATTERNS = [
    re.compile(r"(?:collected|collection\s+date|drawn|specimen\s+date)[:\s]+(\d{4}-\d{2}-\d{2})", re.I),
    re.compile(r"(?:collected|collection\s+date|drawn|specimen\s+date)[:\s]+(\d{1,2}/\d{1,2}/\d{2,4})", re.I),
    re.compile(r"(\d{4}-\d{2}-\d{2})"),
]

def find_collection_date(text: str) -> Optional[datetime]:
    for pat in DATE_PATTERNS:
        m = pat.search(text)
        if m:
            s = m.group(1)
            for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
                try:
                    return datetime.strptime(s, fmt)
                except ValueError:
                    continue
    return None

# Lab line: Name Value Unit (low-high) or Name Value Unit
LAB_LINE_RE = re.compile(
    r"^([A-Za-z][A-Za-z0-9 ,\-/]+?)\s+([0-9.<>]+)\s+([a-zA-Z%/\[\]*0-9.]+)\s*(?:\(([0-9.]+)\s*[-–]\s*([0-9.]+)\))?",
    re.M
)

def parse_lab_lines(text: str, analytes: list) -> List[Dict[str, Any]]:
    """Return list of candidate lab lines with match info."""
    results = []
    for m in LAB_LINE_RE.finditer(text):
        name = m.group(1).strip()
        value = m.group(2)
        unit = m.group(3)
        low = m.group(4)
        high = m.group(5)
        matched = match_analyte(name, analytes)
        plain = is_plain_number(value)
        results.append({
            "original_name": name,
            "value_text": value,
            "unit_original": unit,
            "ref_low": float(low) if low else None,
            "ref_high": float(high) if high else None,
            "ref_text": f"{low}-{high}" if low and high else None,
            "matched": matched is not None,
            "analyte_id": matched.id if matched else None,
            "plain_number": plain,
            "quote": m.group(0).strip(),
        })
    return results
