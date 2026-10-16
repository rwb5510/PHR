"""Lab analyte matching and unit normalization. Exact case-insensitive alias match only.
Ambiguous names stay unmatched. Only seeded factors applied."""
from typing import Optional, Tuple
import re

# Factors: only those listed in AGENTS.md
# Sodium, K, Cl, HCO3: mEq/L == mmol/L
# Glucose: mmol/L = mg/dL / 18.0182  => mg/dL = mmol/L * 18.0182
# Creatinine: umol/L = mg/dL * 88.4  => mg/dL = umol/L / 88.4
# Urea nitrogen: mmol/L urea = mg/dL BUN / 2.8  => mg/dL = mmol/L * 2.8

UNIT_FACTORS = {
    # analyte name lower -> {from_unit_lower: (to_unit, multiplier_to_canonical)}
    "sodium": {"meq/l": ("mmol/L", 1.0)},
    "potassium": {"meq/l": ("mmol/L", 1.0)},
    "chloride": {"meq/l": ("mmol/L", 1.0)},
    "bicarbonate": {"meq/l": ("mmol/L", 1.0)},
    "glucose": {"mmol/l": ("mg/dL", 18.0182)},
    "creatinine": {"umol/l": ("mg/dL", 1.0 / 88.4)},
    "urea nitrogen": {"mmol/l": ("mg/dL", 2.8)},
}

def normalize_unit(unit: Optional[str]) -> Optional[str]:
    if not unit:
        return None
    return unit.strip().lower().replace(" ", "")

def is_plain_number(text: str) -> bool:
    if not text or not text.strip():
        return False
    t = text.strip()
    # Reject inequality or other non-plain
    if any(c in t for c in "<>≤≥~≈"):
        return False
    try:
        float(t)
        return True
    except ValueError:
        return False

def match_analyte(original_name: str, analytes: list) -> Optional[object]:
    """Case-insensitive exact alias match to exactly one analyte. Returns analyte or None if ambiguous/none."""
    if not original_name:
        return None
    name_l = original_name.strip().lower()
    matches = []
    for a in analytes:
        aliases = [x.strip().lower() for x in a.aliases.split(",") if x.strip()]
        if name_l in aliases or name_l == a.name.lower():
            matches.append(a)
    if len(matches) == 1:
        return matches[0]
    return None  # none or ambiguous

def compute_normalized(analyte, value_numeric: Optional[float], unit_original: Optional[str]) -> Tuple[Optional[float], Optional[str]]:
    if value_numeric is None or not analyte or not unit_original:
        return None, None
    unit_n = normalize_unit(unit_original)
    factors = UNIT_FACTORS.get(analyte.name.lower())
    if not factors or unit_n not in factors:
        # if unit already matches canonical, treat as normalized with factor 1
        if unit_n == normalize_unit(analyte.ucum):
            return value_numeric, analyte.ucum
        return None, None
    to_unit, mult = factors[unit_n]
    return value_numeric * mult, to_unit

def compute_abnormal_flag(value_numeric: Optional[float], ref_low: Optional[float], ref_high: Optional[float], printed_flag: Optional[str]) -> str:
    if printed_flag and printed_flag.strip().upper() in ("L", "H", "N", "LOW", "HIGH", "NORMAL"):
        f = printed_flag.strip().upper()
        if f in ("LOW",): return "L"
        if f in ("HIGH",): return "H"
        if f in ("NORMAL",): return "N"
        return f if f in ("L", "H", "N") else "unknown"
    if value_numeric is not None and ref_low is not None and ref_high is not None:
        if value_numeric < ref_low:
            return "L"
        if value_numeric > ref_high:
            return "H"
        return "N"
    return "unknown"
