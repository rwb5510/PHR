# Phase 12 — Panel catalog and data management

**Status:** 📋 Planned
**GitHub Issue:** [#pending](https://github.com/rwb5510/PHR/issues)
**Prerequisites:** none (improves Phase 11 matching and Phase 15 imports; neither is a hard blocker)
**Blocks:** none

---

## Goal *(planning-time)*

Canonical **analytes** already live in `seed/analytes.csv` (Sodium, WBC, A1c, …). **Panels** (CMP, CBC, lipid) are only ad-hoc regexes in `PANEL_NAMES`. The owner has no place to teach the app that a printed title or a component alias belongs to a panel. This phase adds a household-level Data management screen: download a CSV/JSON template, upload panel definitions (name, aliases, ordered component aliases pointing at known analytes when possible), seed a starter catalog (CMP, BMP, CBC, lipid, A1c, TSH) from existing aliases, and use that catalog when detecting headers and grouping imports. Unknown component names still go to the review inbox. Do not add LOINC codes.

---

## Features *(planning-time)*

- New **Data management** entry, household-scoped (top bar next to Settings), not inside a profile chart.
- List current panel definitions: name, aliases, ordered components (original alias → canonical analyte name or “unmatched”).
- Download **CSV** and **JSON** templates with the starter catalog filled in as examples.
- Upload a filled template: **merge** (default) or **replace-all** (explicit checkbox / query flag). Merge updates panels of the same name (case-insensitive) and inserts new ones.
- Starter seed on empty catalog: CMP, BMP, CBC, Lipid Panel, Hemoglobin A1c, TSH — component aliases taken from `seed/analytes.csv` groupings below. No new LOINC.
- Parser/processor may use catalog aliases as extra panel-header patterns (Phase 11 function should accept `extra_patterns`). If Phase 11 is not built yet, `detect_panel_name` can still search catalog names after `PANEL_NAMES`.
- Teaching a panel does **not** auto-file unknown analytes. Matching remains exact case-insensitive alias → exactly one canonical row (`lab_matching.match_analyte`). Ambiguous / unknown names still become inbox proposals.

---

## Design *(planning-time)*

### Why a new table (not analytes.csv)

`canonical_analyte` is the trend join key and is seed-owned. Panels are ordered bundles of component aliases and printed titles. Owners will add “Quest CMP” aliases without touching LOINC. Keep analytes seed-only; keep panels household-editable.

### Data model

New SQLAlchemy models. Schema is created with `Base.metadata.create_all` on API boot. Alembic is in `requirements.txt` but there is **no** `alembic/` tree — do **not** pin a revision number. If a migration file is added later, its number is derived at build time.

```
panel_definition
  id
  household_id      FK household.id, not null, indexed
  name              string not null          # canonical display: "CMP"
  aliases           text not null default "" # comma-separated, case-insensitive
  created_at, updated_at

  UniqueConstraint(household_id, name)  # compare names case-insensitively in app code

panel_component_definition
  id
  panel_definition_id  FK, not null
  sequence             int not null
  original_alias       string not null       # "sodium", "na", "wbc"
  canonical_analyte_id FK canonical_analyte.id, nullable
  created_at
```

No `profile_id`. No `user_id` from the client. `created_by` optional (session user id) if easy; not required for v1.

Do not store LOINC on panel tables. Component rows may point at an existing `canonical_analyte.id` when `original_alias` matches exactly one analyte (same `match_analyte` rules). If not, `canonical_analyte_id` is null — that alias still helps header grouping and Phase 15 column mapping, but values with that name still wait in review until the **result line** matches an analyte.

### Starter catalog (seed in code, not extra LOINC)

Seed only when this household has zero `panel_definition` rows (first visit to Data management or API startup after models exist).

| Panel name | Aliases (examples) | Components (aliases → existing canonical names) |
|---|---|---|
| CMP | comprehensive metabolic, complete metabolic, cmp | Sodium, Potassium, Chloride, Bicarbonate, Urea nitrogen, Creatinine, Glucose, Calcium, Albumin, Total protein, Alkaline phosphatase, ALT, AST, Bilirubin, total |
| BMP | basic metabolic, bmp | Sodium, Potassium, Chloride, Bicarbonate, Urea nitrogen, Creatinine, Glucose, Calcium |
| CBC | complete blood count, cbc | Leukocytes, Erythrocytes, Hemoglobin, Hematocrit, Platelets, MCV, MCH, MCHC, RDW |
| Lipid Panel | lipid panel, lipid profile, lipids | Cholesterol, total, HDL cholesterol, Triglycerides |
| Hemoglobin A1c | hemoglobin a1c, hba1c, a1c panel | Hemoglobin A1c |
| TSH | thyroid, thyroid panel, tsh panel | TSH |

Component aliases on each row should include the canonical name plus that analyte’s CSV aliases (e.g. Leukocytes also `wbc`, `white blood cells`). LDL calculated/direct and eGFR stay **out** (standing spec: do not merge lookalikes; they wait in review).

### Backend / API

All routes require the session cookie. Resolve `household_id` from `request.state.user.household_id` only.

```
GET    /panel-catalog
       → { panels: [ { id, name, aliases: [str], components: [ { sequence, original_alias, canonical_analyte_id, canonical_name } ] } ] }

GET    /panel-catalog/template.csv
       Content-Disposition: attachment; filename=panel-catalog-template.csv

GET    /panel-catalog/template.json
       attachment; filename=panel-catalog-template.json

POST   /panel-catalog/import?mode=merge|replace
       multipart file (csv or json) OR JSON body matching the template
       → { imported, updated, skipped, unmatched_components: [...] }

DELETE /panel-catalog/{panel_id}
       removes one definition (catalog row only — does **not** delete filed LabReport rows)
```

`mode=replace` deletes this household’s `panel_definition` rows (and their components) then inserts the file. It does **not** touch `lab_report` / `lab_component`. That is catalog data, not filed clinical rows.

CSV template (long format, one component per row):

```
panel_name,panel_aliases,sequence,component_alias,canonical_name
CMP,"comprehensive metabolic,complete metabolic,cmp",1,sodium,Sodium
CMP,"comprehensive metabolic,complete metabolic,cmp",2,na,Sodium
CBC,"complete blood count,cbc",1,wbc,Leukocytes
```

JSON template:

```
{
  "version": 1,
  "panels": [
    {
      "name": "CMP",
      "aliases": ["comprehensive metabolic", "complete metabolic", "cmp"],
      "components": [
        { "sequence": 1, "alias": "sodium", "canonical_name": "Sodium" }
      ]
    }
  ]
}
```

`canonical_name` is optional. If present, it must match `canonical_analyte.name` exactly (case-insensitive). If it does not match, skip the link, keep the alias, list it in `unmatched_components`. **Never create a new CanonicalAnalyte from this upload.**

### Using the catalog at parse time

In `process_job`, load this household’s panels (via `doc.profile.household_id`). Pass names+aliases into `detect_panel_headers` / `detect_panel_name`. Catalog does not replace analyte matching.

Phase 15 structured import can map a `panel_name` column through the same aliases.

### Frontend

- Top bar (`App` header ~665): add `Link to="/data"` labeled **Data management** next to Settings. Not under `ProfileNav`.
- Route `/data` (household, no `:id`).
- Paper-chart visual system; table of panels; expand to see components.
- Buttons: Download CSV template, Download JSON template, file input, checkbox “Replace all panels (does not delete filed lab reports)”, Upload.
- Empty state: “Starter panels (CMP, BMP, CBC, lipid, A1c, TSH) load the first time. You can add aliases without adding lab codes.”
- Mobile: stacked cards per panel, 44px targets, no horizontal trap except the component table which may scroll.
- Footer disclaimer stays.

### Access control

- One household in v1; still write `household_id` from the session.
- Tests: catalog GET is empty/404 without cookie when `AUTH_DISABLED` is off; with two households (if fixtures allow) A cannot read B. If tests stay `AUTH_DISABLED=1`, still persist `household_id` from the profile’s household and filter on it.

### Tests

`backend/tests/test_phase12.py`:

- Empty household seeds six starter panels; CMP includes Sodium; CBC includes Leukocytes; no new `canonical_analyte` rows vs seed count.
- Import JSON merge adds a panel `Iron panel` with alias `iron studies` and unmatched component `ferritin` (`canonical_analyte_id` null).
- Replace does not delete `LabReport` rows.
- Template CSV has the required headers.
- Upload that names a fake canonical `MagicEnzyme` does not insert a LOINC / analyte.
- Parser: with catalog alias `COMPREHENSIVE METABOLIC PANEL` already seeded, `detect_panel_name` / headers still return CMP (regression).

### Out of scope

- Extra LOINC codes, invented ranges, FHIR value sets.
- Per-profile catalogs.
- Editing `seed/analytes.csv` from the UI.
- Hard-delete of filed lab reports.
- Public signup / multi-tenant SaaS.

---

## Decisions Needed From User / Open Design Questions *(planning-time)*

1. Household vs per-profile catalog.
   **Answer:** Household-level. (Interview.)

2. Default import mode.
   **Answer:** *(pending — default merge; replace only when the owner opts in)*

3. May owners add analyte aliases from this screen?
   **Answer:** *(pending — default no; aliases for **panels** and **component names that already map to seed analytes**. New tests still go to the inbox until they match `seed/analytes.csv`.)*

---

## Risks *(planning-time)*

- Catalog aliases that are too short (`ca`, `k`) used as **panel** headers could split documents incorrectly. Panel aliases should be title-like (length > 2, not equal to a single analyte alias unless the panel is that one test, e.g. TSH).
- Replace-all looks destructive; copy must say filed labs stay.
- Seeding on every boot could duplicate without the empty-check.
- Scope creep into a terminology server.

---

## Definition of Done

- [ ] Data management is reachable from the household chrome (not a profile tab) and lists panel definitions.
- [ ] CSV and JSON templates download; upload merge/replace updates the catalog only.
- [ ] Starter CMP, BMP, CBC, Lipid Panel, Hemoglobin A1c, TSH exist without adding LOINC codes.
- [ ] Unknown component aliases stay unmatched and do not auto-file.
- [ ] Catalog rows are scoped to the session household; no client-sent household id.
- [ ] Filed `LabReport` rows survive a catalog replace.
- [ ] Tests cover seed, merge, unmatched canonical names, and “no new analytes.”
- [ ] Mobile layout is usable; paper-chart tokens only.
