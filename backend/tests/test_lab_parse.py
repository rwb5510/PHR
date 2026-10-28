"""Lab PDF parsing: results vs letterhead/noise."""
from types import SimpleNamespace
from app.extraction import (
    parse_lab_lines, find_collection_date, parse_result_line, detect_panel_name, detect_panel_headers,
)
from app.lab_matching import match_analyte


def analytes():
    rows = [
        (1, "Sodium", "sodium,na"),
        (2, "Potassium", "potassium,k"),
        (3, "Chloride", "chloride,cl"),
        (4, "Bicarbonate", "bicarbonate,co2,carbon dioxide,hco3"),
        (5, "Glucose", "glucose"),
        (6, "Urea nitrogen", "bun,urea nitrogen,blood urea nitrogen"),
        (7, "Creatinine", "creatinine,creat"),
        (8, "Calcium", "calcium,ca"),
        (9, "ALT", "alt,sgpt,alanine aminotransferase"),
        (10, "Cholesterol, total", "cholesterol,total cholesterol"),
    ]
    return [SimpleNamespace(id=i, name=n, aliases=a, ucum="x") for i, n, a in rows]


MESSY = """
REGIONAL REFERENCE LABORATORY
123 Laboratory Drive
Anytown, ST 00000
Phone: 800 555 0100  Fax: 800 555 0101
CLIA # 11D1234567
Patient: Pat Sample   DOB: 01/01/1980   Sex: F   Age: 45 years
Account: 998877   Physician: A Provider MD
Specimen ID: 24-555-0001
Date Collected: 05/01/2024 08:15
Date Reported: 05/02/2024 11:00
FINAL REPORT

COMPREHENSIVE METABOLIC PANEL
Test Name            Result  Flag  Units     Reference Range
Sodium               140           mmol/L    135-145
Potassium            4.2           mmol/L    3.5-5.1
Chloride             102           mmol/L    98-107
CO2                  24            mmol/L    22-29
Glucose              95            mg/dL     70-99
BUN                  15            mg/dL     7-20
Creatinine           0.9           mg/dL     0.6-1.2
Calcium              9.4           mg/dL     8.6-10.2
ALT (SGPT)           22            U/L       7-52
Sodium, Serum        141           mmol/L    135-145
LDL Cholesterol      110           mg/dL     <100

Please see comments below.
This test was performed at the reference laboratory.
Laboratory Director: Jane Director, MD
Page 1 of 2
"""


def names(rows):
    return [r["original_name"] for r in rows]


def test_messy_report_keeps_results_drops_letterhead():
    rows = parse_lab_lines(MESSY, analytes())
    n = names(rows)
    assert "Sodium" in n
    assert "Potassium" in n
    assert "CO2" in n
    assert "BUN" in n
    assert "ALT (SGPT)" in n
    assert "LDL Cholesterol" in n
    joined = " ".join(n).lower()
    for junk in ("phone", "clia", "patient", "account", "page", "director", "anytown", "sample"):
        assert junk not in joined
    quotes = " ".join(r["quote"] for r in rows).lower()
    assert "800 555" not in quotes
    assert "page 1" not in quotes
    assert "laboratory director" not in quotes


def test_known_analytes_match_unknown_wait():
    rows = parse_lab_lines(MESSY, analytes())
    by_name = {r["original_name"]: r for r in rows}
    assert by_name["Sodium"]["matched"] is True
    assert by_name["CO2"]["matched"] is True
    assert by_name["BUN"]["matched"] is True
    assert by_name["ALT (SGPT)"]["matched"] is True
    assert by_name["Sodium, Serum"]["matched"] is True
    assert by_name["LDL Cholesterol"]["matched"] is False
    assert by_name["LDL Cholesterol"]["unit_original"] == "mg/dL"


def test_ldl_does_not_attach_to_cholesterol():
    a = analytes()
    assert match_analyte("LDL Cholesterol", a) is None
    assert match_analyte("LDL", a) is None
    assert match_analyte("Cholesterol", a) is not None


def test_collection_date_uses_label_not_dob_or_reported():
    dt = find_collection_date(MESSY)
    assert dt is not None
    assert dt.year == 2024
    assert dt.month == 5
    assert dt.day == 1


def test_panel_name_cmp():
    assert detect_panel_name(MESSY) == "CMP"


def test_plain_bmp_line_still_parses():
    row = parse_result_line("Sodium 140 mmol/L (135-145)")
    assert row is not None
    assert row["original_name"] == "Sodium"
    assert row["value_text"] == "140"
    assert row["unit_original"] == "mmol/L"
    assert row["ref_low"] == 135
    assert row["ref_high"] == 145


def test_unknown_analyte_shaped_like_result():
    rows = parse_lab_lines("Collected: 2024-05-01\nFooBar 1.2 mg/dL\n", analytes())
    assert any(r["original_name"] == "FooBar" for r in rows)
    assert all(r["matched"] is False for r in rows if r["original_name"] == "FooBar")


def test_noise_lines_are_not_results():
    text = """
    Phone 800 555 1212
    Page 1 of 3
    Age 45 years
    Suite 100 Floor 2
    Reported 05/02/2024
    """
    assert parse_lab_lines(text, analytes()) == []


def test_range_before_unit_uses_the_result_not_the_high():
    row = parse_result_line("Sodium 140 135-145 mmol/L")
    assert row is not None
    assert row["original_name"] == "Sodium"
    assert row["value_text"] == "140"
    assert row["unit_original"] == "mmol/L"
    assert row["ref_low"] == 135
    assert row["ref_high"] == 145


def test_two_line_name_joins():
    rows = parse_lab_lines(
        "Collected: 2024-05-01\nAlanine Aminotransferase\n22 U/L 7-52\n",
        analytes(),
    )
    assert any(r["original_name"] == "Alanine Aminotransferase" and r["value_text"] == "22" for r in rows)


def test_percent_marketing_is_not_a_result():
    text = "We are 100% committed to HIPAA.\nHematocrit 42.1%\n"
    rows = parse_lab_lines(text, analytes())
    names = [r["original_name"] for r in rows]
    assert "Hematocrit" in names
    assert all("committed" not in n.lower() and "we are" not in n.lower() for n in names)


QUEST_STACKED = """
COMPREHENSIVE METABOLIC PANEL
Analyte
Value
GLUCOSE
(
2345-7
)
110 H
Reference Range:
65-99
mg/dL
FINAL
For someone without known diabetes, a glucose value between 100 and 125 mg/dL is consistent with prediabetes.
SODIUM
(2951-2)
139
Reference Range:
135-146
mmol/L
FINAL
WHITE BLOOD CELL COUNT
(6690-2)
8.5
Reference Range:
3.8-10.8
Thousand/uL
FINAL
NEUTROPHILS
(770-8)
49.8
%
FINAL
Laboratory Director: Weston H Rothrock MD
Quest Diagnostics-Tampa
"""


def test_quest_stacked_keeps_results_drops_comments():
    rows = parse_lab_lines(QUEST_STACKED, analytes())
    n = names(rows)
    assert "GLUCOSE" in n
    assert "SODIUM" in n
    assert "WHITE BLOOD CELL COUNT" in n
    assert "NEUTROPHILS" in n
    glu = next(r for r in rows if r["original_name"] == "GLUCOSE")
    assert glu["value_text"] == "110"
    assert glu["printed_flag"] == "H"
    assert glu["ref_low"] == 65
    assert glu["unit_original"] == "mg/dL"
    joined = " ".join(n).lower()
    assert "between" not in joined
    assert "prediabetes" not in joined
    assert "director" not in joined
    assert "quest" not in joined


def test_quest_one_line_with_loinc_and_reference_range_label():
    line = "GLUCOSE (2345-7)  110 H  Reference Range: 65-99 mg/dL  FINAL"
    row = parse_result_line(line)
    assert row is not None
    assert row["original_name"] == "GLUCOSE"
    assert row["value_text"] == "110"
    assert row["unit_original"] == "mg/dL"
    assert row["ref_low"] == 65
    assert row["printed_flag"] == "H"


def test_inr_without_printed_unit():
    rows = parse_lab_lines("Collected: 2024-05-01\nINR (6301-6)  1.0  FINAL\n", analytes())
    assert any(r["original_name"] == "INR" and r["value_text"] == "1.0" for r in rows)


def test_quest_compact_or_equal_range():
    text = (
        "Collected: 05/29/2026\n"
        "HDL CHOLESTEROL 42 > OR = 40 mg/dL TP\n"
        "CHOLESTEROL, TOTAL 143 <200 mg/dL TP\n"
        "For someone without known diabetes, a glucose value between 100 and 125 mg/dL is consistent.\n"
        "GLUCOSE 104 H 65-99 mg/dL\n"
    )
    rows = parse_lab_lines(text, analytes())
    by = {r["original_name"]: r for r in rows}
    assert by["HDL CHOLESTEROL"]["value_text"] == "42"
    assert by["CHOLESTEROL, TOTAL"]["value_text"] == "143"
    assert by["GLUCOSE"]["value_text"] == "104"
    assert all("between" not in r["original_name"].lower() for r in rows)


def test_protein_total_matches_total_protein():
    a = analytes()
    a.append(type("A", (), {"id": 11, "name": "Total protein", "aliases": "total protein,protein", "ucum": "g/dL"})())
    rows = parse_lab_lines("PROTEIN, TOTAL 6.9 g/dL\n", a)
    assert rows
    assert rows[0]["matched"] is True


def test_column_blob_still_finds_each_row():
    text = (
        "Date Collected: 05/01/2024\n"
        "Sodium               140           mmol/L    135-145\n"
        "Potassium            4.2           mmol/L    3.5-5.1\n"
        "Laboratory Director: Jane Director, MD\n"
    )
    rows = parse_lab_lines(text, analytes())
    n = names(rows)
    assert "Sodium" in n
    assert "Potassium" in n
    assert all("Director" not in x and "Jane" not in x for x in n)


# Phase 11: one document, several panels.

TWO_PANELS = """Collected: 2026-09-21
COMPREHENSIVE METABOLIC PANEL
Sodium 140 mmol/L (135-145)
Potassium 4.2 mmol/L (3.5-5.1)
Glucose 95 mg/dL (70-99)
COMPLETE BLOOD COUNT
WBC 6.2 10*3/uL (3.8-10.8)
Hemoglobin 13.5 g/dL (11.7-15.5)
"""


def panel_of(rows):
    return {r["original_name"]: r["panel_name"] for r in rows}


def test_two_panels_each_line_under_its_header():
    p = panel_of(parse_lab_lines(TWO_PANELS, analytes()))
    assert p["Sodium"] == "CMP"
    assert p["Glucose"] == "CMP"
    assert p["WBC"] == "CBC"
    assert p["Hemoglobin"] == "CBC"
    assert [h["name"] for h in detect_panel_headers(TWO_PANELS)] == ["CMP", "CBC"]


def test_messy_cmp_rows_carry_cmp():
    rows = parse_lab_lines(MESSY, analytes())
    assert {r["panel_name"] for r in rows} == {"CMP"}


def test_no_header_is_imported_panel_not_first_test():
    text = "Collected: 2024-05-01\nSodium 140 mmol/L\nPotassium 4.2 mmol/L\n"
    assert detect_panel_name(text) == "Imported Panel"
    assert {r["panel_name"] for r in parse_lab_lines(text, analytes())} == {"Imported Panel"}


def test_tsh_component_does_not_split_bmp():
    text = (
        "BASIC METABOLIC PANEL\n"
        "Sodium 140 mmol/L (135-145)\n"
        "TSH 1.8 m[IU]/L (0.4-4.5)\n"
        "Potassium 4.2 mmol/L (3.5-5.1)\n"
    )
    assert [h["name"] for h in detect_panel_headers(text)] == ["BMP"]
    assert set(panel_of(parse_lab_lines(text, analytes())).values()) == {"BMP"}


def test_tsh_title_line_is_a_header():
    text = "CMP\nSodium 140 mmol/L\nTHYROID PANEL\nTSH 1.8 m[IU]/L\n"
    assert [h["name"] for h in detect_panel_headers(text)] == ["CMP", "Thyroid"]


def test_stacked_component_name_is_not_a_header():
    text = "HEMOGLOBIN A1C\n5.4\n%\nFINAL\n"
    assert detect_panel_headers(text) == []


def test_orphan_lines_above_first_header_use_default():
    text = (
        "Sodium 140 mmol/L\n"
        "COMPLETE BLOOD COUNT\n"
        "Hemoglobin 13.5 g/dL\n"
    )
    p = panel_of(parse_lab_lines(text, analytes()))
    assert p["Sodium"] == "Imported Panel"
    assert p["Hemoglobin"] == "CBC"


def test_comment_after_first_panel_does_not_drop_second():
    text = (
        "COMPREHENSIVE METABOLIC PANEL\n"
        "Sodium 140 mmol/L (135-145)\n"
        "Comments: fasting specimen\n"
        "Random note text\n"
        "COMPLETE BLOOD COUNT\n"
        "Hemoglobin 13.5 g/dL (11.7-15.5)\n"
    )
    p = panel_of(parse_lab_lines(text, analytes()))
    assert p == {"Sodium": "CMP", "Hemoglobin": "CBC"}


def test_sentence_mentioning_lipid_panel_is_not_a_header():
    text = "CMP\nSodium 140 mmol/L\nA lipid panel is recommended annually.\nPotassium 4.2 mmol/L\n"
    assert [h["name"] for h in detect_panel_headers(text)] == ["CMP"]
