# Household PHR — phased agent prompts

Personal health record for one household, hosted as Docker Compose on an 8 GB VPS.
Not a clinic system, not a medical device, not an EMR.

How to use this file:

1. Create an empty git repo.
2. Paste **Standing spec** into `AGENTS.md` at the repo root. It stays binding for every phase.
3. Start a fresh agent session and paste **only Phase 1**.
4. Do not paste Phase N+1 until Phase N meets every acceptance check.
5. Each phase prompt is written to be self-contained. Do not summarize it.

Assumptions locked from the interview (change the standing spec before Phase 1 if any of these are wrong):

- One household. Multiple profiles from day one. Only one login exists at first. Family logins come later without a schema change.
- Any future household user may open and edit any profile. There are no per-profile permissions in this build.
- Python (FastAPI) + React (Vite, TypeScript) + Postgres. No Redis.
- Files and OCR stay on the VPS. A language model is optional, off by default, per document.
- The model may be a cloud OpenAI-compatible API or a local Ollama. Ollama is a Compose profile, not part of the default 8 GB stack.
- Deterministic imports may auto-file easy fields. Model output does **not** auto-file unless a settings switch is turned on. That switch defaults off.
- No audit-log screen. Still store `created_at`, `updated_at`, and `created_by`.
- Orthanc plus its OHIF plugin in v1. Orthanc is not published on the public internet.

---

## Standing spec

Copy everything in this section into `AGENTS.md`.

### Product

A household personal health record. The owner uploads records, reviews what the system extracted, and gets one chart per person: history, encounters, orders, labs that trend across different panels, imaging reports by modality, and DICOM studies with a viewer. The app can import and export a C-CDA Continuity of Care Document.

People who will use the software are not clinicians sitting in an EHR. The UI must make the original report easy to open next to any structured value.

On-screen disclaimer, always reachable from the footer:

> This is a personal household record. It is not a medical device, not an emergency service, and not a substitute for your clinicians or the original report. Ranges shown are the ranges that came with the result.

### Non-goals

Do not build any of these in Phases 1–8:

- Multi-household SaaS, clinic patients, scheduling for a practice, billing, e-prescribing, or a connection to eClinicalWorks or any other EHR
- A public registration page
- FHIR server or FHIR export
- HL7 v2 listener
- Medication-interaction or clinical-advice engine
- Invented reference ranges
- An audit-log screen
- Native iOS or Android apps
- A local language model in the default Compose file
- Hard delete of a profile or of filed clinical rows

### Stack

- Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic
- Postgres 16
- Job queue is a Postgres table using `FOR UPDATE SKIP LOCKED`. One worker process. No Redis, no Celery.
- React 18, Vite, TypeScript, React Router. Charts with one small library (uPlot is a good default).
- OCR: extract embedded text first; Tesseract (or OCRmyPDF) only when the page has almost no text
- DICOM: `orthancteam/orthanc` with the DICOMweb and OHIF plugins. Pin an exact image tag in Compose and record it in the README. Do not use a floating tag.
- Tests: pytest. Clinical rules live in pure functions, not in route handlers.

Repo layout:

```
AGENTS.md
docker-compose.yml
README.md
api/            FastAPI app, routes, db models
domain/         pure logic: matching, units, C-CDA, auto-file
worker/         job loop
alembic/
web/            Vite React app
seed/analytes.csv
tests/fixtures/ synthetic documents only
scripts/backup.sh
scripts/restore.sh
```

### Runtime shape

Default Compose services: `web`, `api`, `worker`, `postgres`, `orthanc`.

Optional profiles, both off by default:

- `proxy`: Caddy, only if the VPS does not already have a reverse proxy
- `local-llm`: Ollama. The README must say this does not fit beside Orthanc on an 8 GB box and should point at another machine, or be used with Orthanc stopped.

Memory limits in Compose: Postgres 1g, Orthanc 2g, worker 1g, api 512m, web 128m. No GPU.

Nothing except the web port is published on the host. Postgres, Orthanc (8042 and 4242), and Ollama stay on the Docker network. The browser talks only to the web app. The API proxies DICOMweb and the OHIF viewer for logged-in sessions. Orthanc has authentication enabled. Credentials come from env vars.

TLS is the outer proxy’s job. The app must work behind an existing Caddy, Traefik, or nginx. Document the required headers and the upload body size.

Secrets are env vars: database URL, bootstrap username and password, Orthanc credentials, optional `LLM_API_KEY`. Never commit them. Never store the LLM key in Postgres.

First boot creates the household and one user from `BOOTSTRAP_USERNAME` and `BOOTSTRAP_PASSWORD` if no user exists. There is no signup form.

### Identity and access

Tables: `household`, `user`, `profile`.

A profile is one person: legal name, preferred name, date of birth, sex for clinical documents, blood type (optional), relationship label, notes.

Every clinical row has `profile_id`. Queries always filter on it. Tests must prove profile A cannot read profile B through the API.

Sessions are httpOnly cookies, `Secure` when the request is HTTPS, `SameSite=Lax`, server-side session store in Postgres. Passwords hashed with Argon2id. TOTP columns and an enrollment screen exist in Phase 1. Login does not require TOTP until that user turns it on.

`created_by` is the user id. Do not build an audit viewer.

### Encounters are the hub

An encounter is one episode of data, not a calendar day.

Types: `office_visit`, `telehealth`, `ed`, `hospital_stay`, `lab`, `imaging`, `procedure`, `immunization_visit`, `patient_entered`, `other`.

A hospital stay is one encounter with a start and an end, not one row per day.

A lab or imaging study on the same day as an office visit is its **own** encounter. It is tied back to the visit through an order, not by merging the rows.

Encounter fields: type, start, end, facility name, reason, notes, profile.

Providers attach to encounters with a role: attending, ordering, consulting, primary.

### Orders

An order is created at the encounter where it was placed.

Fields: category (`lab`, `imaging`, `procedure`, `referral`), name, priority, status (`ordered`, `scheduled`, `completed`, `cancelled`), ordered_at, ordering_encounter_id, ordering_provider_id, notes.

A result does not overwrite the order. Completing an order sets `status=completed` and links one or more result encounters. Preliminary and final reports can both hang off the same order.

### Clinical objects (manual entry must exist for all of these)

Problems: display name, optional ICD-10, status (`active`, `resolved`, `entered_in_error`), onset, resolved date, notes.

Allergies: substance, reaction, severity (`mild`, `moderate`, `severe`, `unknown`), status, onset, notes.

Medications: name, optional RxNorm, dose, dose unit, route, frequency, status (`active`, `stopped`, `held`, `entered_in_error`), start, stop, prescriber, indication, notes.

Immunizations: vaccine name, optional CVX, date, lot, site, notes.

Procedures and surgeries: name, date, laterality, provider, facility, notes, encounter.

Family history: relationship, condition, age at onset, deceased flag, notes.

Social history: as-of date, smoking, alcohol, other substances, occupation, living situation, notes. Keep the words on the page. Do not score them.

Vitals: type, value, unit, measured_at, optional encounter. Types include blood pressure (systolic and diastolic together), heart rate, weight, height, temperature, oxygen saturation.

Implants and devices: kind, name, model, laterality, implanted date, facility, MRI-safety note, UDI if known.

Insurance: payer, plan, member id, group number, phone.

Pharmacy: name, phone, fax, address.

Emergency contacts: name, relationship, phone.

Appointments: when, provider, place, reason, status. Not an encounter until the visit happens.

Providers: name, credentials, specialty, address, phone, fax, email, website, patient-portal URL, notes.

Voiding: set status to `entered_in_error`. Do not hard-delete filed clinical rows.

### Labs

This is the part agents usually get wrong. Follow it literally.

A **lab report** is one panel instance: profile, encounter, optional order, collection time, reported time, performing lab, specimen, panel name as printed (`CMP`, `BASIC METABOLIC PANEL`), source document.

A **component** is one line on that report:

- `original_name`, `value_text` (always the original characters)
- `value_numeric` only when the value is a plain number
- `unit_original`, `ref_low`, `ref_high`, `ref_text`
- `abnormal_flag`: use the flag printed on the report when it exists. If it does not, set L/H/N only when the value and both limits are numeric. Otherwise `unknown`. Never invent a range.
- `canonical_analyte_id` nullable
- `normalized_value`, `normalized_unit` nullable

A **canonical analyte** is what trends join on. Sodium from a BMP and sodium from a CMP are the same analyte. The panel name is not the join key.

Seed `seed/analytes.csv` with exactly these LOINC codes and no others. Aliases are case-insensitive. You may add aliases that clearly mean the same row. You may not add LOINC codes, and you may not merge two rows.

| Canonical | LOINC | UCUM | Aliases |
|---|---|---|---|
| Sodium | 2951-2 | mmol/L | sodium, na |
| Potassium | 2823-3 | mmol/L | potassium, k |
| Chloride | 2075-0 | mmol/L | chloride, cl |
| Bicarbonate | 1963-8 | mmol/L | bicarbonate, co2, carbon dioxide, hco3 |
| Urea nitrogen | 3094-0 | mg/dL | bun, urea nitrogen, blood urea nitrogen |
| Creatinine | 2160-0 | mg/dL | creatinine, creat |
| Glucose | 2345-7 | mg/dL | glucose |
| Calcium | 17861-6 | mg/dL | calcium, ca |
| Albumin | 1751-7 | g/dL | albumin |
| Total protein | 2885-2 | g/dL | total protein, protein |
| Alkaline phosphatase | 6768-6 | U/L | alkaline phosphatase, alp |
| ALT | 1742-6 | U/L | alt, sgpt, alanine aminotransferase |
| AST | 1920-8 | U/L | ast, sgot, aspartate aminotransferase |
| Bilirubin, total | 1975-2 | mg/dL | bilirubin, total bilirubin, tbil |
| Leukocytes | 6690-2 | 10*3/uL | wbc, leukocytes, white blood cells |
| Erythrocytes | 789-8 | 10*6/uL | rbc, erythrocytes, red blood cells |
| Hemoglobin | 718-7 | g/dL | hemoglobin, hgb, hb |
| Hematocrit | 4544-3 | % | hematocrit, hct |
| Platelets | 777-3 | 10*3/uL | platelets, plt |
| MCV | 787-2 | fL | mcv |
| MCH | 785-6 | pg | mch |
| MCHC | 786-4 | g/dL | mchc |
| RDW | 788-0 | % | rdw |
| Cholesterol, total | 2093-3 | mg/dL | cholesterol, total cholesterol |
| HDL cholesterol | 2085-9 | mg/dL | hdl, hdl cholesterol |
| Triglycerides | 2571-8 | mg/dL | triglycerides, tg |
| Hemoglobin A1c | 4548-4 | % | a1c, hba1c, hemoglobin a1c |
| TSH | 3016-3 | m[IU]/L | tsh, thyroid stimulating hormone |
| INR | 6301-6 | {INR} | inr |

Do not fold these into a single analyte. They look similar and are not:

- LDL calculated vs LDL direct
- eGFR results that use different equations
- Any name that matches more than one canonical row

Those wait in the review queue with the candidates shown.

Unit conversion is allowed only when a factor is stored on the analyte. Seed these factors and no general-purpose converter:

- Sodium, potassium, chloride, bicarbonate: `mEq/L` equals `mmol/L`
- Glucose: `mmol/L` = `mg/dL` / 18.0182
- Creatinine: `umol/L` = `mg/dL` * 88.4
- Urea nitrogen: `mmol/L` urea = `mg/dL` BUN / 2.8, and label the canonical unit `mg/dL`

The original value and unit are never overwritten. The trend chart plots `normalized_value` when it exists. If it does not, split the series by `unit_original`. Never plot mixed units on one axis. Do not draw a single normal band across results that came from different labs. The tooltip for every point shows original value, original unit, and that result’s own range.

Values like `<0.1` or `>100` stay in `value_text`. `value_numeric` is null. They are listed, not connected as ordinary points.

Same collection time and same performing lab share one **lab encounter**. Each panel is still its own lab report. A CMP and a CBC drawn together are two reports on one encounter.

### Imaging reports

Modalities, stored as codes, displayed as the label:

`DX` X-ray (aliases CR, DX, XR, XRAY), `CT`, `MR`, `US`, `MG` Mammography, `NM`, `PT` PET, `XA` Angiography or fluoroscopy, `DXA` Bone density, `OT` Other.

Fields: modality, body site, laterality, performed_at, findings text, impression text, facility, reporting provider, encounter, optional order, optional DICOM study id, optional series id, source document.

The library screen groups by modality, then date.

### Documents and auto-file

Accepted uploads: PDF, TIF, TIFF, JPG, JPEG, PNG, TXT, MD, XML, and a `.zip` of DICOM files (DICOM zip is Phase 7).

Store the original bytes, SHA-256, filename, mime type, and page count. Exact duplicate hash on the same profile shows a warning and does not create a second chart entry.

Processing order:

1. XML that is a CDA `ClinicalDocument` goes to the C-CDA parser.
2. Otherwise extract embedded text.
3. If a page has almost no text, OCR it.
4. Rules and, only when asked, a model propose chart entries.
5. Proposals are rows. A person accepts or rejects them. Accepted rows become real chart rows and keep a pointer to the source document and the quote or XML path they came from.

Auto-file, with no model involved, only when all of these are true:

- The document was imported into a chosen profile, and
- Either the document has no patient date of birth, or that date of birth equals the profile, and
- The item is a C-CDA structured entry with a code and a date for a problem, allergy, medication, immunization, procedure, vital, or lab result that has a value and a unit, **or** a lab line whose name matches exactly one canonical analyte, with a plain numeric value, a unit, and a collection date.

A conflicting date of birth never auto-files. The file stays in review with the difference shown.

Everything else waits: impressions, history narratives, social history, unmatched analytes, missing units, low-quality OCR, and every model proposal while `llm_autofile` is false.

`llm_autofile` exists and defaults to false. When it is true, a model proposal may auto-file only if it would have passed the lab rule above (single analyte, number, unit, date, DOB ok). Narratives still wait.

### Optional model

Settings: mode `off`, `remote`, or `local`. Default `off`.

Remote and local both use an OpenAI-compatible `base_url` and model name. The key is `LLM_API_KEY`. Local Ollama uses a dummy key and a URL on the Docker network.

Each upload has “Use model”, default off. The control is disabled while mode is `off`.

Send only the extracted text of that one document, plus the analyte alias list. Ask for JSON matching a schema the app owns. Proposals land in the review queue. Log the document id and the time, never the body, the key, or the model’s full output at info level.

If the call fails, the document still exists with its text. Failure is not data loss.

### C-CDA

Import and export C-CDA R2.1 Continuity of Care Document (document code `34133-9`).

Parse with `lxml`. Identify sections by their LOINC section codes, not by display name:

- `11450-4` problems
- `48765-2` allergies
- `10160-0` medications
- `11369-6` immunizations
- `47519-4` procedures
- `30954-2` results
- `46240-8` encounters
- `29762-2` social history
- `10157-6` family history
- `8716-3` vitals
- `46264-8` medical equipment

Copy template OIDs from the HL7 C-CDA R2.1 specification or from a synthetic sample checked into `tests/fixtures`. Do not invent OIDs. Do not depend on an abandoned generator library. A small explicit builder with fixture tests is better than an unmaintained framework.

Export includes a human-readable narrative and structured entries for the sections above, plus payers when insurance exists. Author is the app, described as a self-generated personal record. Unknown import sections are kept with the original XML file, not dropped.

Do not auto-file an import whose date of birth conflicts with the selected profile.

### DICOM

Orthanc stores bytes. Postgres stores study and series metadata: Study Instance UID, Series Instance UID, accession, modality, description, date, Orthanc ids, counts.

Upload goes through the API, which streams to Orthanc. Do not keep a second copy of the pixels in the document volume.

A study links to one imaging encounter. A document or imaging report links to a study and, optionally, a series.

The chart opens the viewer at that study through the authenticated proxy. OHIF is the Orthanc OHIF plugin, not a second build of OHIF from source.

### UI

Responsive. A phone-width browser must be able to use the emergency snapshot, allergies, medications, and a lab trend without horizontal scrolling. Desktop can be denser.

Shell: profile switcher always visible, plus navigation for dashboard, chart sections, labs, imaging, documents, review inbox, providers, and emergency snapshot.

Empty states tell the user what to enter or upload next. Do not fill the UI with sample patients. Tests use synthetic fixtures only. No real names, dates of birth, or MRNs in the repo.

### Backup

`scripts/backup.sh` writes a timestamped dump of Postgres, the document volume, and the Orthanc volume. `scripts/restore.sh` restores all three into an empty Compose project. No cloud backup destination is required.

### Definition of done, every phase

- `docker compose up` works from a clean checkout with a `.env.example`
- Alembic migrations apply on an empty database
- New tests for that phase pass
- README says what was added and how to try it
- No extra services, no new framework, no scope from later phases

---

## Phase 1 — Platform, login, profiles

```
You are building Phase 1 of a household personal health record. Read AGENTS.md and obey it. If AGENTS.md is missing, stop and ask for it.

Build only the platform.

Include:
- docker-compose.yml with web, api, worker, postgres, and orthanc
- Orthanc image pinned, DICOMweb and OHIF plugins enabled, authentication enabled, ports NOT published to the host, memory limit 2g
- The other memory limits from AGENTS.md
- Compose profiles `proxy` and `local-llm` present but not started by default. Do not pull a model.
- Alembic, SQLAlchemy models for household, user, profile, and session
- Bootstrap of one household and one user from env on first boot
- Login and logout. Argon2id passwords. httpOnly session cookie
- TOTP secret, enrollment screen, and disable screen. Login must succeed when TOTP is not enabled, and must ask for a code when it is
- Profile create, edit, and list. Profile switcher stored in the session
- A logged-in shell with the disclaimer in the footer and empty navigation placeholders
- Health check
- README: required env vars, how to log in, how to put this behind an existing reverse proxy, the 8 GB budget, and why Ollama is not in the default stack

Do not build clinical tables, uploads, or a DICOM UI yet. Orthanc only has to start and answer an authenticated status request from the API.

Acceptance:
- A clean `docker compose up` reaches the login page
- The bootstrap user can log in without TOTP
- After TOTP is enabled, login without a valid code fails, and login with a valid code works
- Creating two profiles and switching them persists across refresh
- An automated test fails if any profile route returns another profile’s row
- Postgres and Orthanc ports are not mapped to the host
- Worker process is running and idle

Stop when acceptance passes. Do not start Phase 2.
```

---

## Phase 2 — Manual chart

```
You are building Phase 2 of a household personal health record. Read AGENTS.md and obey it. Phase 1 is already done. Do not rebuild auth. Do not add file upload, OCR, C-CDA, lab trending, or DICOM.

Build manual chart entry for the active profile.

Tables and CRUD screens:
- providers
- encounters, with provider roles
- problems, allergies, medications, immunizations, procedures
- family history, social history, vitals
- implants, insurance, pharmacy, emergency contacts
- appointments

Encounters use the type list in AGENTS.md. A hospital stay has a start and an end.

Every query is scoped by the active profile. Add a test that seeds two profiles and proves each list is isolated.

Voiding sets status to entered_in_error and hides the row from default lists, with a toggle to show voided rows. No hard delete.

Emergency snapshot page, printable, for the active profile only:
- name, date of birth, sex, blood type
- active allergies with reaction and severity
- active problems
- active medications
- implants
- emergency contacts
- pharmacy and insurance
- primary provider if one is marked

The snapshot is a view over the chart, not a separate copy of the data.

Phone-width layout must be usable for the snapshot, allergies, and medications.

Acceptance:
- You can create a provider, an office-visit encounter, and attach the provider
- You can enter one row of every clinical type above and see it on refresh
- Voiding a medication removes it from the active list and from the snapshot, and the row still exists
- Switching profiles shows a different chart
- Emergency snapshot prints without the app navigation
- Tests cover profile isolation and voiding

Stop. Do not start Phase 3.
```

---

## Phase 3 — Orders, labs, imaging reports, trends

```
You are building Phase 3 of a household personal health record. Read AGENTS.md and obey it, especially the Labs section. Do not add file upload, OCR, C-CDA, a language model, or a DICOM viewer.

Build:

Orders
- Create an order on an encounter
- Categories and statuses from AGENTS.md
- A result encounter can be linked later. Linking marks the order completed
- The office-visit screen lists orders placed there
- The result encounter shows the order it fulfills
- Same calendar day does not merge encounters. Add a test: a visit and a lab on the same date are two encounters connected only by the order

Labs
- Implement the lab report, component, and canonical analyte model exactly as AGENTS.md specifies
- Load seed/analytes.csv in a migration or seed command. Do not add LOINC codes that are not in that file
- Manual entry of a report with components
- Matching: case-insensitive exact alias match to one analyte fills canonical_analyte_id and, when a seeded factor exists, normalized_value. Ambiguous names stay unmatched
- Implement only the unit factors listed in AGENTS.md
- Preserve value_text. Do not coerce “<0.1” into 0.1
- Abnormal flag rules from AGENTS.md
- A report view in the order the components were entered, showing value, unit, and range on every line
- An analyte trend view. BMP sodium and CMP sodium appear on one Sodium trend. Unmatched or mixed-unit series are not forced onto that axis
- Tooltips show the original value, unit, and that point’s own reference range
- Two panels drawn at the same time can share one lab encounter and remain two reports

Imaging reports
- Manual imaging report with modality, the grouping library, and the fields in AGENTS.md
- No viewer and no Orthanc calls in this phase

Acceptance, all automated where it is logic:
- A CMP and a BMP that both contain “Na” and “Sodium” produce one sodium series of two points, and the CMP-only analytes are not dropped
- “LDL” does not silently attach to a canonical analyte
- mEq/L sodium normalizes to mmol/L. The stored original unit remains mEq/L
- “<0.1” is stored and is not a numeric point
- A result with no range has flag unknown and still displays
- An order on a visit links to a separate lab encounter on the same day
- Profile isolation still holds for reports and trends

Stop. Do not start Phase 4.
```

---

## Phase 4 — Documents, OCR, review queue

```
You are building Phase 4 of a household personal health record. Read AGENTS.md and obey it. Do not add C-CDA mapping, a language model, or DICOM upload yet. XML files are stored and their text is shown; clinical XML parsing is Phase 5.

Build document intake.

- Upload PDF, TIFF, JPG, PNG, TXT, and Markdown into the active profile
- Store bytes, hash, filename, mime, page count, extracted text
- Same-profile duplicate hash warns and does not file a second copy
- Embedded text first. OCR only pages that need it. Record that OCR was used
- Jobs run on the Postgres queue. The UI shows queued, processing, needs review, filed, and failed
- A failed job can be retried. The file is never deleted by a failure
- Review inbox lists proposals. Accept creates the real chart row and stores the source document id. Reject keeps the proposal
- From a lab row or imaging report, the user can open the source file
- Manual “create lab report from this document” and “create imaging report from this document” when extraction finds nothing
- Size limit documented, default 50 MB per file

Auto-file in this phase is limited to lab lines in extracted text that pass the lab rule in AGENTS.md: exactly one analyte alias, plain number, unit, and a collection date on the page or in the form the user confirms. If the collection date is not confidently found, do not auto-file. Put the proposal in the inbox.

No model client in this phase. No network calls except the app itself.

Acceptance:
- A text PDF of a BMP produces sodium, potassium, and the other matched lines as chart components with units and ranges, and opens back to the PDF
- A scanned image with no text layer gets OCR text stored
- An unknown analyte name waits in the inbox and is not charted
- Duplicate upload is rejected with a visible warning
- Worker crash mid-job leaves the file stored and the job retryable
- Tests use synthetic files only

Stop. Do not start Phase 5.
```

---

## Phase 5 — C-CDA import and export

```
You are building Phase 5 of a household personal health record. Read AGENTS.md, especially C-CDA and the auto-file rules. Do not add a language model or DICOM upload.

Import
- Detect a CDA ClinicalDocument. Other XML stays a plain document as in Phase 4
- Parse sections by LOINC section code, using lxml
- Map problems, allergies, medications, immunizations, procedures, encounters, results, vitals, social history, family history, and medical equipment into proposals
- Lab results that include a LOINC code in the seed file attach to that canonical analyte even if the display name differs
- Lab results with a different LOINC stay as original-name components and wait for review
- Keep the original XML
- Auto-file only when the AGENTS.md auto-file rule passes, including the date-of-birth check
- A conflicting date of birth blocks auto-file and explains the mismatch
- Sections you do not understand remain inside the stored document

Export
- One action on the active profile: download a C-CDA R2.1 CCD
- Template OIDs come from a cited HL7 source or from the checked-in synthetic fixture, in a comment. No invented OIDs
- Narrative plus structured entries
- Author text makes clear this is a self-generated personal record
- Include the sections listed in AGENTS.md when the chart has data for them

Fixture
- Check in a synthetic CCD you can regenerate, with two profiles’ worth of nothing real: fictional names, a sodium result using LOINC 2951-2, one problem, one allergy, one medication
- Test: import that fixture into a profile with the same date of birth, export, import the export into a second empty profile, and assert equal counts for problems, allergies, medications, and sodium results

Acceptance is that round trip plus the DOB-mismatch test. Do not claim ONC certification.

Stop. Do not start Phase 6.
```

---

## Phase 6 — Optional model extraction

```
You are building Phase 6 of a household personal health record. Read AGENTS.md, especially Optional model and auto-file. C-CDA and rule-based lab parsing already exist. Do not replace them with the model. Do not add DICOM.

Build:
- Settings screen: mode off, remote, or local. Base URL and model name. No API key field. The key is the LLM_API_KEY env var only
- Per-upload “Use model”, default off, disabled when mode is off
- A client for an OpenAI-compatible chat endpoint. Local Ollama and a remote vendor must both work by changing URL and model
- Input is the extracted text of that single document plus the analyte alias list
- Output must validate against a JSON schema the app owns before any proposal is saved. Invalid JSON is a failed extraction, not a partial silent write
- Proposals go through the existing review inbox and show that they came from the model
- llm_autofile setting exists, defaults false, and is explained in the UI as unsafe
- When llm_autofile is false, no model proposal becomes a chart row by itself
- When a human accepts a lab proposal, the same matching and unit rules from Phase 3 apply
- Logs may contain document id, duration, and success or failure. They must not contain document text, the key, or the raw model response
- The Compose profile `local-llm` starts Ollama and nothing else. README says not to run it on the 8 GB box together with Orthanc

The model is never required for import. With mode off, Phase 4 and Phase 5 behavior is unchanged.

Acceptance:
- With mode off, an upload never opens an outbound model connection
- A fake local HTTP server returning schema-valid JSON creates inbox proposals and zero chart rows while llm_autofile is false
- A response that is not valid JSON leaves the document stored and marks extraction failed
- Turning llm_autofile on still does not auto-file an impression paragraph
- Tests do not call a real vendor

Stop. Do not start Phase 7.
```

---

## Phase 7 — DICOM studies and viewer

```
You are building Phase 7 of a household personal health record. Read AGENTS.md, especially DICOM. Orthanc is already running from Phase 1 with authentication and no published ports.

Build:
- Upload a DICOM file or a zip of DICOM files for the active profile. Stream the bytes to Orthanc through the API. Do not store a second pixel copy
- Non-DICOM files inside the zip are skipped and listed
- Postgres rows for study and series: UIDs, accession, modality, description, date, Orthanc ids
- Create or attach an imaging encounter for the study date and modality
- On the imaging library, show studies as well as reports
- Let the user link an existing document or imaging report to a study, and optionally to a series. Let them unlink
- Open viewer route that loads the Orthanc OHIF plugin for that Study Instance UID, proxied through the logged-in app. The browser never receives Orthanc’s address or password
- If the link is series-specific, select that series when the viewer supports it, and always show the series label in the chart even if the viewer opens the whole study
- Deleting a study from the chart UI is “remove from this profile”: delete the Postgres link and delete the Orthanc study only when no other profile references those UIDs. Do not delete the imaging report

Acceptance:
- A small synthetic DICOM study (generate one in the test, do not commit a huge file) appears under the right profile and modality
- The same bytes are not present on the document volume
- From the imaging report screen, linking that report to the study survives refresh
- Requesting the viewer URL without a session returns 401
- Orthanc’s ports are still unpublished
- A second profile cannot see the study

Stop. Do not start Phase 8.
```

---

## Phase 8 — Dashboard, backup, and the last gaps

```
You are building Phase 8, the last phase, of a household personal health record. Read AGENTS.md. Do not add a new subsystem. Fill in the shell that earlier phases left as placeholders.

Dashboard for the active profile:
- Demographics line
- Active problems, allergies, and medications, each with a link to the full list
- Next appointment if one exists
- Recent encounters in reverse chronological order
- Recent lab results that are flagged L or H, showing value, unit, and range, linking to the trend
- Recent imaging reports grouped by modality, linking to the report and, if present, the viewer

Review inbox shows a count on the navigation badge.

Emergency snapshot from Phase 2 stays the printable page. Add a short “how to hand this to a clinician” note: give them this printout or the C-CDA download, not a login.

Backup:
- scripts/backup.sh dumps Postgres, the document volume, and the Orthanc volume into a timestamped directory
- scripts/restore.sh restores those three into a fresh Compose project
- README documents a restore drill
- Run that drill once on the synthetic fixture data and record the command in the README

Check the finished app against AGENTS.md non-goals and remove anything that crept in.

Final acceptance:
- A new user can follow the README from an empty server to a running app, create a profile, enter a medication, upload the synthetic CCD, see sodium on a trend, and download a C-CDA
- Backup and restore return the same medication and the same sodium result
- Default `docker compose up` does not start Ollama or a second proxy
- Memory limits are still in the Compose file
- The footer disclaimer is present
- No signup page exists

Stop. The build defined by these prompts is complete.
```

---

## What you still type yourself

The agent should not invent these. Put them in `.env` when you deploy:

- `BOOTSTRAP_USERNAME` and `BOOTSTRAP_PASSWORD`
- Postgres password
- Orthanc username and password
- Public URL behind your existing proxy
- `LLM_API_KEY`, base URL, and model, only if you later turn the model on

Turn on TOTP before you put real records on a server that is reachable from the internet.
