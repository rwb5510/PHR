# Phase 11 — Multi-panel names on one document

**Status:** 📋 Planned
**GitHub Issue:** [#3](https://github.com/rwb5510/PHR/issues/3)
**Prerequisites:** none (heuristic titles ship even if Phase 12’s catalog is later)
**Blocks:** none (Phase 14 grouping is nicer when this exists; not a hard blocker)

---

## Goal *(planning-time)*

One uploaded PDF often contains several panels (example: 2026-09-21 labs with a CMP then a CBC). Today `processor.py` calls `detect_panel_name(text)` **once for the whole document** and files **one** `LabReport`. `detect_panel_name` walks `PANEL_NAMES` in order and returns the first regex hit (`CMP` is first), so CBC lines are stored under CMP. When no regex hits, the name is the generic `"Imported Panel"`. This phase splits one extracted document into multiple lab reports, names each from the printed header above its lines, and keeps components on the panel they belong to.

---

## Features *(planning-time)*

- Detect **every** panel header in document order (CMP, CBC, BMP, lipid, A1c, TSH/thyroid, hepatic, plus catalog names when Phase 12 exists).
- Each parsed lab line belongs to the **most recent header above it**. Lines before any header use a fallback (see Design).
- Auto-file creates **one `LabReport` per panel**, not one per document.
- Same collection time + same performing lab still share **one lab encounter** (standing spec). CMP and CBC drawn together are two reports on one encounter.
- Lab report list shows the real panel name (`CBC`, `CMP`), not `"Imported Panel"`, when a header was found.
- Review-inbox `lab_line` payloads include that line’s `panel_name` so Accept files onto the correct report.
- Heuristic titles work without the Phase 12 catalog. Catalog aliases, when present, are an extra header source — not a gate.

---

## Design *(planning-time)*

### Current code

- `PANEL_NAMES` and `detect_panel_name` in `backend/app/extraction.py` (~120, ~380). First match on the **entire** text wins; default `"Imported Panel"`.
- `parse_lab_lines(text, analytes)` returns annotated rows with `original_name`, `value_text`, `unit_original`, refs, `quote`, `matched`, `analyte_id`, `plain_number`. **No `panel_name` per line.**
- `process_job` (`processor.py` ~95–177): one `panel_name = detect_panel_name(text)`, one `LabReport` for all auto-filed lines, every proposal gets that same `panel_name`.
- `POST /proposals/{id}/accept` (`main.py` ~456): finds **the first** `LabReport` with `source_document_id == prop.document_id` and appends the component. Accepting a CBC line after a CMP report exists will dump CBC onto CMP. **This must change.**

### Parsing

Replace “one name for the blob” with header spans.

Add pure functions in `extraction.py` (clinical rules stay out of route handlers):

```
detect_panel_headers(text, extra_patterns=None) -> list[{name, start, end_hint, quote}]
assign_panel_to_lines(text, lines, headers) -> lines with panel_name
```

Header detection:

1. Built-in `PANEL_NAMES` patterns, applied **per line** (and to short two-line windows), collecting **all** hits with character or line offsets. Do not return after the first hit.
2. Prefer the more specific pattern when two match the same line (`comprehensive metabolic` over a bare later hit).
3. If Phase 12 catalog rows exist, treat each panel’s `name` and `aliases` as additional case-insensitive whole-line / word-boundary patterns. Call catalog load from the processor, pass patterns in; keep `extraction.py` free of DB if possible.
4. Ignore headers inside skip/boilerplate lines (phone, CLIA, page N of M) using existing `_is_boilerplate` / `SKIP_LINE`.
5. TSH: today’s pattern `thyroid|tsh` can false-positive on a TSH **component** line. Header lines should look like titles: little or no lab unit on that line, or match `thyroid (panel|function)` / `TSH panel` / a line that is only `TSH` with no number. Document this in tests. A lone `TSH 1.8 m[IU]/L` is a component, not a panel split.

`parse_lab_lines` should attach `panel_name` using the nearest preceding header. Keep `detect_panel_name(text)` as a thin wrapper (`headers[0].name` or `"Imported Panel"`) so existing `test_panel_name_cmp` still holds for CMP-only fixtures.

Fallback name:

- If **at least one** header was found, lines before the first header inherit that first header **only if** they sit in the result zone immediately under a delayed title; otherwise `"Imported Panel"` for those orphan lines. Prefer: orphan lines before the first header → `"Imported Panel"`; everything after a header → that header until the next.
- If **no** header was found, all lines may use `"Imported Panel"` (same as today). Do **not** rename to the first component (`Sodium`) — that is the bug the user is seeing when CMP’s title is the only one detected.

Printed strings vs canonical short names: store the **display name from the matched rule** (`CMP`, `CBC`, `Lipid Panel`, …) on `LabReport.panel_name` (existing non-null string). If the line matched an alias `COMPLETE BLOOD COUNT`, store `CBC` (or the catalog’s canonical panel name). Do not add LOINC for panels.

### Processor / auto-file

After `parse_lab_lines`:

1. Group lines by `panel_name` **preserving first-seen order**.
2. `find_collection_date(text)` remains document-level unless a later phase parses per-panel dates. One collection timestamp for the file is the current extractor’s honesty.
3. Create **one** `Encounter` (`type=lab`, `start=coll_date`, `reason="Imported lab"`) when any line auto-files, shared by all panels from this document that share that collection time (only one date is known). Performing lab is not parsed today (`facility_name=None`); do not invent it. If a future extractor fills performing lab, the standing rule is: same collection time **and** same performing lab → one encounter.
4. For each panel group that has auto-fileable lines (`matched` + plain number + unit + collection date): insert a `LabReport` with that `panel_name`, `source_document_id`, `encounter_id`, `collection_time`.
5. Lines that cannot auto-file become `lab_line` proposals whose payload `panel_name` is that line’s panel, not the first panel in the file.

`reset_document_outputs` already deletes **all** `LabReport`s for the document and empty imported encounters. Keep that; reprocess must not leave duplicate panels.

### Accept path (critical)

`accept_proposal` for `lab_line` must locate or create a report matching **`(source_document_id, profile_id, panel_name)`**, not just the document:

- If a report for that panel exists on this document, append the component (`sequence = count`).
- If not, reuse the document’s existing **lab** encounter for this collection date if one exists (same spec: one encounter, many reports); else create encounter + report.
- Default panel if payload omitted: `"Reviewed Panel"` (today) is fine; do not steal another panel’s report.

Do not merge CMP and CBC components onto one report after accept.

### API / UI

- `GET /profiles/{id}/lab-reports` already returns `panel_name` per report. Lab Reports list (`LabReports()` ~302) already renders `r.panel_name`. No new endpoint required if the processor writes the right rows.
- Optional: group the list by `collection_time` then panel for readability — nice-to-have, not required.
- Inbox list may show `payload.panel_name` as a muted tag so two lines from one PDF are distinguishable.

### Data model

No new tables. `LabReport.panel_name` stays a required string. Multiple reports may share `source_document_id` and `encounter_id`.

Schema via `create_all` on boot. No Alembic revision number.

### Access control

Unchanged rules: reports and proposals carry `profile_id`; queries filter it; session household owns the profile. Accept uses `prop.profile_id` from the server row, never a client-sent profile id.

### Mobile

List of two reports on one date (`CMP — 2026-09-21`, `CBC — 2026-09-21`) is enough. No extra chrome.

### Tests

Add to `backend/tests/test_lab_parse.py` and a processor test (new `test_phase11.py` or extend `test_phase4.py`):

- Fixture text (and a PDF via reportlab) with:

  ```
  Collected: 2026-09-21
  COMPREHENSIVE METABOLIC PANEL
  Sodium 140 mmol/L (135-145)
  ...
  COMPLETE BLOOD COUNT
  WBC 6.2 10*3/uL
  Hemoglobin 13.5 g/dL
  ```

  Assert two reports, names `CMP` and `CBC` (or the mapped display names), Sodium not under CBC, WBC not under CMP, **one** lab encounter for that date.

- Header-only CMP document still names `CMP` (`test_panel_name_cmp` remains green).
- No headers → `"Imported Panel"` (do not use the first test name).
- TSH component line does not split a BMP.
- Accepting an unmatched CBC-named proposal does not append to an existing CMP report for the same document.
- Existing BMP auto-file test still creates one report named `BMP` (fixture title is `BASIC METABOLIC PANEL`).

### Out of scope

- Teaching the app new panels via CSV (Phase 12). Heuristics + current `PANEL_NAMES` are enough to ship.
- Per-panel collection dates if the PDF only prints one “Collected:” line.
- Invented reference ranges or extra LOINC codes.
- Changing auto-file rules (still: one canonical analyte, number, unit, collection date, DOB ok).

---

## Decisions Needed From User / Open Design Questions *(planning-time)*

1. Catalog (Phase 12) before heuristic titles?
   **Answer:** No. Phase 11 ships with built-in `PANEL_NAMES` / printed titles. Catalog later only adds aliases.

2. What to store when the print says `COMPLETE METABOLIC PANEL` vs `CMP`.
   **Answer:** *(pending — default: mapped short name from `PANEL_NAMES` / catalog canonical name, e.g. `CMP`)*

3. Lines above the first header.
   **Answer:** *(pending — default: `"Imported Panel"` for those orphans, not the first header)*

---

## Risks *(planning-time)*

- Header regexes matching component names (TSH, “lipid” in a comment). Mitigate with “title-like” line rules and tests.
- Quest stacked layouts already have special parsers (`_parse_stacked_blocks`); header assignment must run on the **original line offsets**, not only on de-duplicated rows. If offsets are lost, fall back to scanning the source `quote` against header positions.
- Accept-path bug (one report per document) will silently undo the split if forgotten.
- Reprocess deletes prior reports (`reset_document_outputs`); owners who edited a filed report then reprocess will lose those rows — existing behavior, document it, do not expand to hard-delete of unrelated chart rows.

---

## Definition of Done

- [ ] A single document with CMP then CBC (as in the 2026-09-21 example) files two lab reports with those panel names; components sit under the header above them.
- [ ] Lab report list does not label a named panel as `"Imported Panel"`.
- [ ] `"Imported Panel"` remains only when no panel header was detected (or for orphan lines, per Design).
- [ ] Same collection date from one file still uses one lab encounter and multiple reports.
- [ ] Inbox `lab_line` payloads carry the line’s `panel_name`; Accept appends to that panel’s report, not the first report on the document.
- [ ] Heuristic titles work without Phase 12.
- [ ] Tests cover the two-panel fixture, TSH-not-a-header, and the accept-path split; existing BMP/CMP parse tests still pass.
- [ ] No new LOINC codes; no invented ranges; no hard-delete of filed rows outside the existing reprocess reset.
