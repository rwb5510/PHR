# Phase 13 — Imaging-report proposals from documents

**Status:** 📋 Planned
**GitHub Issue:** [#5](https://github.com/rwb5510/PHR/issues/5)
**Prerequisites:** none (reuse Phase 9’s inbox source pane when it exists; otherwise filename + extracted text)
**Blocks:** none

---

## Goal *(planning-time)*

Documents currently always run the **lab** parser. A chest XR PDF (`2026-10-23 XR chest post port.pdf`) ends as `needs_review` with “No lab results found. A result is a test name, a number, and a lab unit…”. `ProposalType.imaging_report` already exists on `Proposal` (`models.py` ~252), and `ImagingReport` already has modality, body site, laterality, findings, impression, source_document_id. This phase classifies uploads as lab-like vs imaging-like vs unknown, and for imaging-like narrative PDFs creates **imaging_report proposals** in the review inbox (with the original file beside them) instead of a failed-lab message. Manual “create imaging report from this document” stays. DICOM is not required.

---

## Features *(planning-time)*

- Classifier uses filename **and** extracted text: XR, CXR, CR, DX, XRAY, CT, MR, MRI, US, ultrasound, MG, mammograph, NM, PET, PT, XA, DXA, fluoroscop, radiograph, plus phrases like “technique:”, “findings:”, “impression:”.
- Imaging-like documents with **no** lab-shaped lines create one or more `imaging_report` proposals (typically one per report) and **do not** set the job error to the lab-shaped-result paragraph.
- Proposal payload: `modality` (codes from the standing spec), `body_site`, `laterality`, `performed_at` (if a labeled date is found), `findings`, `impression`, `facility`, `reporting_provider` when easily parsed; plus `quote` from the impression or findings block.
- Inbox shows these candidates (not only `lab_line`). If Phase 9 shipped, the source pane loads the PDF/image beside the proposal; otherwise show filename + `GET /documents/{id}/text`.
- Accept creates an `ImagingReport` + imaging `Encounter`, pointer `source_document_id`, status accepted. Reject drops the proposal; the **file remains**.
- Documents page: keep upload as-is; add / restore a control **Create imaging report from this document** that posts a manual payload (the function `create_imaging_from_document` in `main.py` ~611 currently has **no route decorator** — register it).
- Unknown documents (no labs, no imaging signals) can stay `needs_review` with a **neutral** message: not “No lab results found” when the filename is clearly imaging; for truly unknown, say that no lab lines and no imaging report were detected.
- Do not require a DICOM study. Do not auto-file imaging narratives (impressions wait in review — standing spec).

---

## Design *(planning-time)*

### Classifier

Pure function in `extraction.py` (or `backend/app/document_class.py`):

```
classify_document(filename: str, text: str) -> "lab" | "imaging" | "unknown"
```

Signals (weight, do not use a model by default):

- **Lab-like:** `parse_lab_lines` would return ≥1 row, or filename/text has strong lab titles (`PANEL_NAMES`, “metabolic panel”, “lab results”) **and** lab units.
- **Imaging-like:** filename tokens `\b(xr|cxr|ct|mri?|us|usg|nm|pet|dxa|mammo)\b` or text headings Findings/Impression/Technique/Comparison with little or no lab-unit density.
- **Both:** keep lab parsing **and** add an imaging proposal if imaging signals are strong (e.g. a packet with a report plus a CBC). Do not drop labs.
- **Neither:** unknown.

Modality mapping (standing spec; store the **code**, display the label in UI):

| Code | Aliases in filename/text |
|---|---|
| DX | XR, CXR, CR, DX, XRAY, radiograph, x-ray |
| CT | CT, CAT |
| MR | MR, MRI |
| US | US, ultrasound, sonogram |
| MG | MG, mammograph, mammo |
| NM | NM, nuclear |
| PT | PET |
| XA | XA, fluoro, angiograph |
| DXA | DXA, dexa, bone density |
| OT | fallback |

Body site: simple patterns (`chest`, `abdomen`, `pelvis`, `head`, `brain`, `c-spine`, `knee`, `port` is not a site — try `chest` from “XR chest”). Laterality: `left`, `right`, `bilateral` near the site. Dates: reuse labeled date patterns; prefer “Exam date” / “Study date” / “Performed” over collection.

Findings / impression: slice text from a `FINDINGS:` heading until `IMPRESSION:` / `END OF REPORT`; impression from `IMPRESSION:` until the next heading or end. Cap stored text (e.g. 20k chars) so the payload stays JSON-friendly. `quote` = first ~240 chars of impression, else findings.

This is deterministic extraction, not a diagnosis engine. Empty findings are allowed; the owner edits by accepting then using existing imaging fields, or by rejecting and using the manual form.

### Processor

In `process_job`, after text extraction and C-CDA / optional-model short-circuits:

1. `lines = parse_lab_lines(...)` as today.
2. `kind = classify_document(doc.filename, text)`.
3. If lines: existing lab auto-file / lab_line proposals (Phase 11 grouping if present).
4. If `kind == "imaging"` or (imaging signals and (kind == "unknown" or both)): insert `Proposal(type=imaging_report, payload=json.dumps({...}), quote=...)`. **Never auto-file** this type (`llm_autofile` does not apply to narratives).
5. Job status:

   - Only labs, all auto-filed, no imaging proposal → `filed`.
   - Any proposal → `needs_review`, `error_message` null (or a short “Imaging report ready to review”).
   - Unknown, no lines → `needs_review` with a message that does **not** claim the file was a failed lab when `kind == "imaging"`.

Model path (Phase 6): if `use_model` and the model returns `type: imaging_report`, map to `ProposalType.imaging_report` instead of today’s fallback to `lab_report`. Do not require the model for this phase.

### Accept / reject

`POST /proposals/{id}/accept` currently has **no** `ProposalType.imaging_report` branch (`main.py` ~449–528). Add:

- Create `Encounter(type=imaging, start=performed_at or utcnow, reason="Accepted from review", profile_id=prop.profile_id)`.
- Create `ImagingReport` from payload fields; `source_document_id=prop.document_id`; `profile_id` from the proposal row.
- Do not trust a profile id in the JSON body.
- Leave DICOM ids null.

Reject: status `rejected` only. Do not delete `Document`.

### Manual create route

`create_imaging_from_document` exists at `main.py` ~611 **without** `@app.post`. Register:

```
POST /documents/{document_id}/create-imaging
body: { modality, body_site, laterality, performed_at, findings, impression, facility, reporting_provider }
```

Household-scope the document. Documents UI: for `needs_review` / `filed` jobs, a secondary button opens a small form (modality select with spec codes, textareas for findings/impression) and POSTs. This remains available even when proposals exist.

### Inbox UI

- Render `type === 'imaging_report'` with modality, body site, date, impression preview (first 200 chars), quote.
- Accept / Reject buttons unchanged.
- Source: Phase 9 pane if present; else `<a target="_blank" rel="noreferrer" href=/api/documents/${document_id}/file>` plus extracted text (Phase 10 inline if present).
- Do not assume only `lab_line` in the list.

### Imaging library

Existing `GET /profiles/{id}/imaging-reports` groups by modality. Accepted proposals appear there. Source link should inline-open after Phase 10.

### Data model

No new tables. Use `ProposalType.imaging_report`, `ImagingReport`, `Document`. `create_all` on boot; no pinned Alembic number.

### Access control

Session household owns the profile. Proposal `profile_id` is copied from `doc.profile_id` at insert. File GET scoped as in Phases 9–10.

### Mobile

Inbox cards wrap; impression text `pre-wrap`; 44px buttons. Source pane stacked (Phase 9).

### Tests

`backend/tests/test_phase13.py`:

- Upload a TXT/PDF named `XR chest post port.pdf` whose body is a short findings/impression **without** lab units → job `needs_review`, **no** “No lab results found” lab-unit paragraph, one pending `imaging_report` with modality `DX` and body_site containing chest, quote from impression.
- Accept → `ImagingReport` row, imaging encounter, `source_document_id` set; document still GET-able.
- BMP PDF from Phase 4 still auto-files labs and does **not** create an imaging proposal.
- Filename `labs.pdf` with Sodium lines stays lab-only.
- `POST /documents/{id}/create-imaging` creates a report when extraction found nothing.
- Two profiles: cannot accept a proposal by id that belongs to the other profile (404).

### Out of scope

- DICOM upload (Phase 7 already exists); do not require a study on the report.
- Auto-file of impressions.
- Radiology AI / measurements.
- FHIR ImagingStudy.
- Pixel highlight boxes on the radiograph (same limits as Phase 9).

---

## Decisions Needed From User / Open Design Questions *(planning-time)*

1. Imaging PDFs create inbox proposals (not only a manual form).
   **Answer:** Yes — `imaging_report` proposals with source beside them. (Interview.)

2. When a file looks like both a lab and an imaging report.
   **Answer:** *(pending — default: keep lab lines and also add an imaging proposal if imaging headings exist)*

3. One proposal vs split findings/impression.
   **Answer:** *(pending — default: one `imaging_report` proposal per document unless page text has multiple Impression headings)*

---

## Risks *(planning-time)*

- “US” as a country code or “MR” as medical record in letterhead. Require word boundaries and/or nearby imaging words (`chest`, `findings`, filename).
- Lab documents with an “Impression” comment on a lipid panel. Require low lab-unit density **or** imaging filename tokens before dropping the lab error path; never skip lab lines that already parsed.
- Unregistered `create_imaging_from_document` surprises the build session — this doc calls it out.
- Model path mapping everything unknown to `lab_report` (processor ~79) would mis-file imaging JSON; fix the enum mapping.

---

## Definition of Done

- [ ] An imaging-like narrative PDF (e.g. chest XR) creates an `imaging_report` proposal instead of a “No lab results found” lab-unit message.
- [ ] Inbox can accept/reject that proposal; Accept writes `ImagingReport` + imaging encounter with `source_document_id`.
- [ ] Original file is kept and viewable beside the proposal (Phase 9 pane if present, else filename + extracted text).
- [ ] Manual `POST /documents/{id}/create-imaging` is a real route and remains available.
- [ ] Lab PDFs still parse as labs; imaging does not auto-file; no DICOM required.
- [ ] Household/session scoping on accept and file GET; no client-sent household id.
- [ ] Tests cover XR fixture, BMP non-regression, and the manual create route.
- [ ] No FHIR, no invented lab ranges, no hard-delete of filed rows.
