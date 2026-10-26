# Phase 14 — Lab results matrix over time

**Status:** 📋 Planned
**GitHub Issue:** [#pending](https://github.com/rwb5510/PHR/issues)
**Prerequisites:** none (Phase 11 makes multi-panel days easier to read; ship the matrix even if 11 is later)
**Blocks:** none

---

## Goal *(planning-time)*

The primary labs entry is a **Sodium-only** trend: Profile nav links to `/profile/:id/trends/Sodium` (`App.tsx` ~143) and `TrendView` plots one canonical analyte (`GET /profiles/{id}/trends/{analyte_name}` ~255). That is not how a household chart is used. This phase makes the Labs screen a **matrix**: rows are components (canonical analytes, then unmatched original names), columns are collection dates, cells are the value plus flag color. Clicking a row opens that component’s trend (existing `TrendView` as a drill-in). The dedicated Sodium nav link is removed as the featured labs entry.

---

## Features *(planning-time)*

- **Lab reports** nav item (`/profile/:id/labs`) becomes the matrix (or the matrix is the default view on that route with a way to list individual reports).
- Columns: collection dates (date part of `LabReport.collection_time`), newest first.
- Rows: seed-order canonical analytes that have at least one value, then unmatched `original_name` groups (case-insensitive).
- Cells: `value_text` + unit (prefer `unit_original`; if normalized and the column is mixed, still show original). Flag color: L/H use `--red`; N muted; unknown ink. No invented range band in the cell.
- Click a **row label** → `/profile/:id/trends/{analyte}` for canonical rows. Unmatched names: a list/trend of that original name (new query or reuse a `?original=` path) — do not force them onto Sodium.
- Click a **cell** → that `LabReport` (`/lab-report/:id`) so the owner can open the source document.
- Remove “Sodium trend” from `ProfileNav`. Dashboard “Flagged labs” may still link to the matching analyte’s trend (already `trends/${c.analyte || 'Sodium'}` — stop defaulting to Sodium when `analyte` is missing; link to the matrix or the original-name trend).
- Phone: table `overflow-x: auto`, **sticky first column** (component name), 44px row labels.
- Do not plot mixed units on one axis (existing TrendView / standing spec). Matrix cells are numbers-as-text; they may sit side by side even when units differ — show the unit in the cell so that is visible.

---

## Design *(planning-time)*

### API

Add a profile-scoped matrix endpoint. Do not send household/user ids from the client.

```
GET /profiles/{profile_id}/lab-matrix
```

Response shape:

```
{
  "dates": ["2026-09-21", "2026-05-01"],
  "rows": [
    {
      "key": "analyte:12",
      "kind": "canonical",
      "canonical_analyte_id": 12,
      "display_name": "Sodium",
      "canonical_unit": "mmol/L",
      "cells": {
        "2026-09-21": {
          "component_id": 91,
          "report_id": 7,
          "panel_name": "CMP",
          "value_text": "140",
          "value_numeric": 140,
          "unit_original": "mmol/L",
          "normalized_value": 140,
          "normalized_unit": "mmol/L",
          "abnormal_flag": "N",
          "ref_text": "135-145",
          "source_document_id": 3
        }
      }
    },
    {
      "key": "original:ferritin",
      "kind": "unmatched",
      "canonical_analyte_id": null,
      "display_name": "Ferritin",
      "canonical_unit": null,
      "cells": { "2026-05-01": { ... } }
    }
  ]
}
```

Rules:

- Scope: `LabReport.profile_id == profile_id` after verifying the profile is in the session household.
- Date key: `collection_time.date()` ISO `YYYY-MM-DD`. Reports with null collection_time: omit from columns or put under `"unknown-date"` at the end — prefer omit from matrix and leave them on the individual report list.
- Multiple panels the same day (CMP + CBC): **one column**. If the same canonical analyte appears twice that day (Sodium on CMP only is typical; a repeat BMP+CMP would collide): keep the later `reported_time` / higher `lab_report.id`, and expose `also: [{ report_id, panel_name, value_text }]` so the UI can show a `+1` or title tooltip. Do **not** average.
- Row order: `canonical_analyte.id` seed order (`load_analytes` / CSV order). Skip analytes with no cells. Then unmatched names sorted alphabetically.
- Unmatched key: `normalize_test_name(original_name).lower()` so “Sodium, Serum” that failed match still groups; if match succeeded it is not in this bucket.

Keep `GET /profiles/{id}/trends/{analyte_name}` for canonical drill-in. Add:

```
GET /profiles/{profile_id}/trends/original/{name}
```

for unmatched series (filter `canonical_analyte_id IS NULL` and normalized original name). Split by `unit_original` in the existing TrendView way. 404 if empty is unnecessary — return `{ points: [] }`.

### Frontend

- `LabReports()` (~302): become a two-section page:

  1. **Results over time** — the matrix (primary).
  2. **Reports** — existing list of `panel_name — collection_time` links (secondary). After Phase 11 this list is one row per panel.

- Nav: delete `<Link to=.../trends/Sodium>Sodium trend</Link>`. Keep `Lab reports` as the labs entry. `Route path="trends/:analyte"` stays.

- Matrix markup: `<table>` inside a `.matrix-scroll` wrapper (`overflow-x: auto; -webkit-overflow-scrolling: touch`). `th:first-child, td:first-child { position: sticky; left: 0; background: var(--card); z-index: 1 }`. Min column width ~72px. Flag L/H: `color: var(--red); font-weight: 600`. Do not use emoji.

- Empty: “No lab results yet. Upload a report or enter one.”
- Row click vs cell click: row header is a `Link` to trend; cell is a `Link` to `/lab-report/{id}`. Do not nest interactive elements illegally — use `<th><Link>` and `<td><Link>`.

- `TrendView`: keep unit-split lists; if uPlot is already a dependency, a small chart is welcome but not required for this phase (current UI is a list). Never mix units on one series.

- Dashboard flagged labs: link `c.analyte` when present, else `/labs`.

- Visual system: paper chart tokens only. `.shell` max-width 960px may clip many dates — allow the labs card to be `max-width: none` / full bleed within `.shell` and rely on horizontal scroll rather than shrinking type below 14px.

### Data model

No new tables. Reads `LabReport` + `LabComponent` + `CanonicalAnalyte`.

### Mobile

Sticky name column, swipe for dates, 44px row headers. Do not use hover-only tooltips; put unit in the cell (`140 mmol/L`). Title/tooltip can repeat range.

### Tests

`backend/tests/test_phase14.py` (and keep `test_phase3.py` sodium trend):

- Two reports on different dates with Sodium + a CBC Leukocytes on the later date → `dates` length 2, Sodium row has two cells, Leukocytes one cell, no Sodium-only page involved.
- Same-day CMP + CBC (if Phase 11 exists) → one column, both Sodium and Leukocytes filled. If Phase 11 is absent and both panels were wrongly one report, the matrix still shows both components on that date — test should not require 11.
- Unmatched `FooBar` appears as `kind: unmatched`.
- Mixed units for glucose (mg/dL vs mmol/L) appear as separate cell texts with their units; trend endpoint still splits series (`test_phase3.py` already covers mixed-unit trends).
- Profile filter: profile 2’s matrix does not include profile 1’s Sodium (`test_phase3.py` pattern).

Frontend is not unit-tested in this repo; do not add a Jest stack unless one exists.

### Out of scope

- Sodium-only as the home for labs (removed).
- Invented reference bands across labs.
- Extra LOINC.
- Replacing TrendView; it is the drill-in.
- Auth changes.

---

## Decisions Needed From User / Open Design Questions *(planning-time)*

1. Matrix vs keep a dedicated sodium page as primary.
   **Answer:** Matrix is primary; TrendView remains a drill-in; remove featured Sodium nav. (Interview.)

2. Keep the per-report list on the Labs page.
   **Answer:** *(pending — default yes, below the matrix)*

3. Two values for the same analyte on the same date.
   **Answer:** *(pending — default: latest report id wins, tooltip lists others)*

---

## Risks *(planning-time)*

- Wide matrices on phone — sticky column + scroll is mandatory or the page is unusable.
- Treating the matrix as a sparkline of mixed units. Cells must show units; charts stay split.
- Defaulting missing analyte links to Sodium (dashboard) reintroduces the problem.
- Performance: naive N+1 per cell. One query of components joined to reports for the profile is enough; assemble in Python.

---

## Definition of Done

- [ ] Labs primary view is a date-column matrix of components, not a Sodium-only page.
- [ ] “Sodium trend” is removed from profile nav; TrendView still works when opened from a row.
- [ ] Clicking a canonical row opens that analyte’s trend; clicking a cell opens the lab report.
- [ ] Unmatched names have their own rows (and a drill-in that is not Sodium).
- [ ] L/H cells use the red token; units visible; mixed units are not plotted on one axis.
- [ ] Phone: horizontal scroll + sticky first column.
- [ ] Matrix API is profile-scoped from the session household.
- [ ] Tests cover two dates, unmatched rows, and profile isolation; Phase 3 trend tests still pass.
