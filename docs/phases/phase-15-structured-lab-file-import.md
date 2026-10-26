# Phase 15 — Structured CSV / XLS / XLSX / JSON lab import

**Status:** 📋 Planned
**GitHub Issue:** [#7](https://github.com/rwb5510/PHR/issues/7)
**Prerequisites:** none (Phase 12 catalog improves panel-name matching; Phase 11 grouping helps; both optional)
**Blocks:** none

---

## Goal *(planning-time)*

Documents currently advertise “Max 50 MB per file. PDF, TIFF, JPG, PNG, TXT, XML, MD” (`Documents()` ~479) and the lab parser looks for “a test name, a number, and a lab unit” on a visual row. Spreadsheets and JSON are rejected or treated as opaque binaries, then fail as fake lab PDFs. This phase accepts **csv, xls, xlsx, json** on the same Documents upload (50 MB), publishes a **template** that can hold **several panels and several dates in one file**, and when the file matches that template, files lab reports/components (unknown names → inbox). If the file does **not** match the template, store the original bytes and attempt text extraction rather than erroring as a failed lab PDF.

---

## Features *(planning-time)*

- Documents file input accepts `.csv`, `.xls`, `.xlsx`, `.json` in addition to today’s types. Help text lists them. Cap remains 50 MB (`MAX_UPLOAD_BYTES`).
- Downloadable template (CSV + JSON; XLSX generated from the same columns) from Documents and/or Data management.
- One file may contain multiple `panel_name`s and multiple `collection_date`s. Each (date, panel) becomes its own `LabReport`. Same date + same performing lab (if provided) share one lab encounter (standing spec).
- Template columns: collection date, panel name, original name, value, unit, ref range (low/high/text), optional flag, optional performing lab, optional specimen.
- Rows whose name matches exactly one seed analyte, with a plain number, unit, and collection date, auto-file. Others become `lab_line` proposals with quotes pointing at the cell/row.
- Non-template CSV/JSON/XLSX: store file, extract text (CSV/JSON as UTF-8 text; xlsx via cell dump), then existing parsers / classifier. Do **not** use the “No lab results found… Sodium 140 mmol/L” message as if it were a PDF when the file is a spreadsheet — if no rows parse, say the file did not match the lab template and no result rows were detected.
- Use a real XLSX library at **build** time (`openpyxl` added to `backend/requirements.txt`). Do not hand-roll ZIP/XML.

---

## Design *(planning-time)*

### Template layout (proposed — long format)

**Dates as columns (wide)** fights “several panels AND several dates AND variable components” in one sheet (sparse headers, repeated panel names). **One result per row (long)** is the published template.

CSV / XLSX sheet `results` header row (exact names, case-insensitive):

```
collection_date,panel_name,original_name,value,unit,ref_low,ref_high,ref_text,flag,performing_lab,specimen
```

- `collection_date` — ISO `YYYY-MM-DD` preferred; also `MM/DD/YYYY`. Required for auto-file.
- `panel_name` — printed/catalog name (`CMP`, `CBC`). Required. Mapped through Phase 12 aliases when that table exists.
- `original_name` — required.
- `value` — stored as `value_text` (keep `<0.1`). `value_numeric` only if `is_plain_number`.
- `unit` — original unit; do not invent.
- `ref_low` / `ref_high` — optional floats.
- `ref_text` — optional; if empty and both lows/highs exist, UI may display `low–high`.
- `flag` — optional `L`/`H`/`N`.
- `performing_lab`, `specimen` — optional, copied onto `LabReport`.

JSON:

```
{
  "version": 1,
  "format": "phr-lab-results",
  "results": [
    {
      "collection_date": "2026-09-21",
      "panel_name": "CMP",
      "original_name": "Sodium",
      "value": "140",
      "unit": "mmol/L",
      "ref_low": 135,
      "ref_high": 145,
      "ref_text": "135-145",
      "flag": null,
      "performing_lab": "Quest",
      "specimen": "serum"
    },
    {
      "collection_date": "2026-09-21",
      "panel_name": "CBC",
      "original_name": "WBC",
      "value": "6.2",
      "unit": "10*3/uL"
    }
  ]
}
```

Recognition as “matches template”:

- JSON: `format == "phr-lab-results"` **or** (`version` present **and** `results` is a list of objects with `original_name` + `value`).
- CSV/XLSX: header contains at least `collection_date`, `panel_name`, `original_name`, `value` (unit strongly recommended; missing unit blocks auto-file per standing spec, still proposes).

XLS: read via `openpyxl` if xlsx; for legacy `.xls` either add `xlrd` (old) or document that `.xls` is converted by the owner. **Build should support .xls if feasible** (`xlrd==1.2.x` is frozen for xls, or convert with a small dependency). If `.xls` support is too brittle, accept the file, store it, and return needs_review “Excel 97-2003 .xls is stored; save as .xlsx for structured import.” Do not crash.

Wide sheets (dates as columns) are **not** auto-detected in v1. If headers look like dates, job message should say: use the long template (link/path). Remaining questions go under Decisions Needed.

### Upload / MIME

`POST /profiles/{profile_id}/documents` already accepts any bytes under 50 MB. Extend allowed-type messaging only (there may be no server allowlist today — confirm at build; if an allowlist exists, add csv/xls/xlsx/json mimes and suffixes).

Store `mime_type` from suffix when the client sends `octet-stream`.

### Processor

Before `parse_lab_lines` on raw text:

```
if looks_like_structured_lab(filename, mime, data):
    rows = parse_structured_lab(data, filename)
    # then same auto-file / proposal loop as PDF lines, grouped by (collection_date, panel_name)
else:
    text = extract as today  # for csv/json, decode utf-8; for xlsx, concatenate cell values as TSV text
    existing lab / imaging / ccda paths
```

Grouping:

- Key: `(collection_date, panel_name, performing_lab or "")`.
- One `Encounter` per `(collection_date, performing_lab)` with `type=lab`.
- One `LabReport` per `(encounter, panel_name)` with components in file order (`sequence`).
- `source_document_id` = this document.
- `quote` for proposals: `"{panel} {original_name} {value} {unit} on {date}"` or the CSV line.

Duplicate SHA on the same profile still warns and does not create a second document (`main.py` ~336). Reprocess remains the path to parse again.

Auto-file rules unchanged: chosen profile, DOB ok (structured files usually have no patient DOB — treat as “no DOB on document” → allowed), exact one canonical analyte, plain numeric value, unit, collection date. Never invent ranges. Never add LOINC.

### Template download

```
GET /lab-import/template.csv
GET /lab-import/template.json
GET /lab-import/template.xlsx
```

Authenticated. Attachments. Include 2–3 example rows (synthetic; no real names). Documents page links these next to the file input.

### Frontend

- Update the help sentence on Documents to include CSV, XLS, XLSX, JSON and a one-line “Use the lab results template for several panels and dates in one file.”
- `input` `accept` attribute: add `.csv,.xls,.xlsx,.json`.
- Links: Download CSV template, JSON, XLSX.
- Phase 10: xlsx may still Save-As when opening the stored original; JSON/CSV can inline as text.

### Dependencies

Add to `backend/requirements.txt` (pin a current stable at build time, e.g. `openpyxl`):

- `openpyxl` for xlsx read/write.
- Optional `xlrd` only if .xls is implemented.

Do not add these as frontend packages.

### Access control

Upload already profile-scoped. Processor uses `doc.profile_id`. Template GETs need a session. Household from session.

### Mobile

File input and template links stack; 44px. No spreadsheet grid editor in-app.

### Tests

`backend/tests/test_phase15.py` plus a fixture file under `backend/tests/fixtures/`:

- JSON template with CMP Sodium 140 on 2026-09-21 **and** CBC WBC on the **same** date **and** a BMP Sodium on 2026-05-01 → two encounters (two dates), three reports, Sodium trends across dates, WBC only on Sep 21.
- CSV equivalent.
- XLSX via openpyxl in-test.
- Unknown name `Ferritin` with number+unit+date → proposal, not auto-file.
- JSON that is `{ "foo": 1 }` stored, job does not claim “lab unit on the same row” PDF copy; extracted_text nonempty or a structured-miss message.
- 50 MB cap still 413.
- No new `canonical_analyte` rows.
- Profile isolation: uploaded to profile 1, not listed on profile 2.

Keep Phase 4 PDF tests green.

### Out of scope

- FHIR, HL7 v2, public signup.
- Wide (dates-as-columns) template v1.
- Editing cells in the browser.
- Hard-delete of filed rows (reprocess reset only, existing).
- Invented ranges / extra LOINC.

---

## Decisions Needed From User / Open Design Questions *(planning-time)*

1. Long format (one result per row) vs dates as columns.
   **Answer:** Publish long format so one file can hold several panels and several dates. (Proposed; interview left this open.)

2. Legacy `.xls` (Excel 97–2003).
   **Answer:** *(pending — default: store the file; structured parse guaranteed for xlsx/csv/json; xls best-effort or a “save as xlsx” job message)*

3. Extra sheets in a workbook.
   **Answer:** *(pending — default: read the sheet named `results` if present, else the first sheet)*

4. Alternate header names (`Test`, `Result`, `Ref Range`).
   **Answer:** *(pending — default: only the published headers in v1; unmatched files fall through to text dump)*

---

## Risks *(planning-time)*

- Treating a random CSV export from a portal as the template and filing garbage. Mitigate with strict header recognition; otherwise store + text extract + inbox.
- Formula cells / merged cells in xlsx. Read `data_only=True` if Excel cached values exist; otherwise skip formula-only cells and message.
- Date serials in Excel (days since 1899). Convert with openpyxl’s date types; do not file `44900` as a collection date string without conversion.
- Memory: 50 MB xlsx parse on the worker (1g). Stream rows; do not build giant DOM beyond openpyxl’s model.
- Duplicate panels on reprocess — existing `reset_document_outputs` must clear prior labs from this document.

---

## Definition of Done

- [ ] Documents accepts csv, xls/xlsx, and json up to 50 MB and lists them in the help text.
- [ ] Published CSV/JSON/(XLSX) template supports several panels and several dates in one file (long format).
- [ ] A matching template file files one lab report per (date, panel), sharing a lab encounter per date (+ performing lab when present).
- [ ] Unknown test names go to the review inbox; known analytes with number, unit, and date auto-file per standing spec.
- [ ] A non-template spreadsheet/JSON is stored and does not fail with the PDF “Sodium 140 mmol/L” empty-lab copy.
- [ ] `openpyxl` (or equivalent) is a real backend dependency used for xlsx — no hand-rolled xlsx parser.
- [ ] No new LOINC codes, no invented ranges, no client-sent household ids.
- [ ] Tests cover multi-panel + multi-date JSON/CSV/XLSX, unmatched names, and non-template JSON; Phase 4 PDF tests still pass.
