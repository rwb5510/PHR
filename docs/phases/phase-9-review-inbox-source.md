# Phase 9 — Review inbox source viewer

**Status:** ✅ Built
**GitHub Issue:** [#1](https://github.com/rwb5510/PHR/issues/1)
**Prerequisites:** none (build may land a small inline `Content-Disposition` change that Phase 10 later owns fully)
**Blocks:** none (Phase 13 reuses this pane when present; it is not a hard blocker)

---

## Goal *(planning-time)*

The review inbox currently shows candidate chart rows (`lab_line` proposals) with the extracted `quote` string and Accept / Reject buttons, but not the original page those candidates came from. The owner cannot tell whether the parser read the right line. This phase puts the source document beside the selected proposal, scrolls to the matching excerpt, and highlights that excerpt so accept/reject is a visual check against the original report — not a guess from a one-line quote.

---

## Features *(planning-time)*

- Split review inbox: proposal list on one side, source pane on the other.
- Selecting a proposal loads that proposal’s `document_id` in the source pane (filename, mime, extracted text, original file).
- Extracted text is always shown with the proposal `quote` highlighted (case-insensitive substring; first match wins). The pane auto-scrolls so the highlight is in view.
- For PDFs, render the original bytes in-browser (iframe to the file endpoint, or PDF.js if the iframe cannot search). If the PDF text layer contains the quote, highlight that occurrence. Do not invent pixel-accurate OCR bounding boxes.
- For images (JPG/PNG/TIFF), show the image in the pane. Highlight lives on the extracted-text panel underneath, not as a drawn box on pixels.
- For TXT/MD/XML, the extracted text *is* the source; highlight in place.
- Keyboard/click: clicking another proposal swaps the source and highlight without leaving the page.
- Mobile: stack the list above the source pane (or a two-tab switcher: Proposals / Source). Do not require a side-by-side viewport.
- Keep the existing inbox copy that unknown names / missing dates / non-numeric values wait here, and that letterhead is not listed.

---

## Design *(planning-time)*

### Current behavior (do not regress)

- Route: `frontend/src/App.tsx` `Inbox()` (~line 557), path `/profile/:id/inbox`.
- Data: `GET /profiles/{profile_id}/proposals` in `backend/app/main.py` (~429). Each row already includes `id`, `document_id`, `type`, `payload`, `quote`, `from_model`, `created_at`.
- Source bytes: `GET /documents/{document_id}/file` (~386) returns `FileResponse(..., filename=doc.filename, media_type=doc.mime_type)`. Starlette treats `filename=` as `Content-Disposition: attachment`, which is why browsers Save-As. Phase 10 owns the full inline/mime fix; this phase needs **inline serving for the inbox iframe to work even if Phase 10 is later**.
- Extracted text: `GET /documents/{document_id}/text` (~396) returns `{ extracted_text, ocr_used, page_count }`. `Document.extracted_text` is the only location store; there are **no glyph/OCR bounding boxes** on `Document` or `Proposal` (`backend/app/models.py`).
- Proposals for labs that did not auto-file are created in `backend/app/processor.py` with `quote=line["quote"]` (a short snippet from `parse_lab_lines`).

### Highlight fidelity (locked)

The pipeline stores extracted text plus a quote string. It does not store PDF operator positions or Tesseract word boxes. Therefore:

1. **Always** highlight the quote in the extracted-text view (`<mark>` around the first case-insensitive match; if no match, show the quote above the text with a “not found in extracted text” note — OCR drift is real).
2. **Optionally** use PDF.js text-layer search to mark the same string on the PDF. Treat a miss as acceptable (scanned PDFs, hyphenation, column extract order).
3. **Do not** promise pixel boxes over a rasterized page. Do not add a new OCR coordinate table in this phase.

### Backend / API

Keep existing list/accept/reject endpoints. Add only what the pane needs.

1. **Inline file helper** (shared with Phase 10; implement here if 10 is not already merged):

   ```
   GET /documents/{document_id}/file
   ```

   Change `FileResponse` so previewable types use `content_disposition_type="inline"` and a correct `media_type`. Map by stored mime first, then filename suffix: `application/pdf`, `image/jpeg`, `image/png`, `image/tiff`, `text/plain`, `text/markdown`, `application/xml` / `text/xml`. Do not force download for PDF/images. See Phase 10 for the full matrix (CSV/XLSX still download).

2. **Optional convenience (only if the UI would otherwise N+1):**

   ```
   GET /profiles/{profile_id}/proposals/{proposal_id}
   → { proposal fields, document: { id, filename, mime_type, extracted_text, ocr_used, page_count } }
   ```

   Not required if the client already has the list payload and can call `/documents/{id}/text` + `/file`. Prefer the two existing GETs unless grouping by document is painful.

3. **Access control.** Session cookie already required by `auth_middleware`. Every document/proposal fetch must:

   - Resolve the session user (never a client-sent `user_id` / `household_id`).
   - Load `Document` / `Proposal` by id, join `Profile`, require `Profile.household_id == session.user.household_id`.
   - For profile-scoped list endpoints, also require `profile_id` to belong to that household (existing list already filters `Proposal.profile_id == profile_id`; still verify the profile is in-household).
   - Today `GET /documents/{id}/file` and `/text` do **not** check household/profile. Fix that as part of this phase (otherwise the iframe is a cross-profile leak inside a future multi-user household). Return 404, not 403, for the wrong household.

   Any household member may read any profile in the household (standing spec). Do not add per-profile ACLs.

### Frontend

- Replace the single-column `<ul>` in `Inbox()` with a layout:

  - Desktop (`min-width: ~800px`): CSS grid `minmax(280px, 1fr) minmax(320px, 1.4fr)` inside `.shell`. The shell is currently `max-width: 960px` (`frontend/src/styles.css`); allow the inbox card to use the full shell width. Do not introduce a second visual system — paper `#f3efe6`, card `#fffcf7`, ink, muted, line, green primary, red only for reject / abnormal.
  - Phone: list first; selected proposal’s source pane directly below. Sticky Accept / Reject row so thumbs do not need to scroll past a tall PDF. Tap targets ≥ 44px.

- Proposal list: keep `lab_line` rendering (`original_name`, `value_text`, `unit_original`, `ref_text`, muted `quote`). Other types keep the generic `type` + quote/payload line so Phase 13 imaging proposals can appear later without a rewrite. Selected row gets a visible border (`var(--line)` / green), not a new color.

- Source pane states:

  - No selection: “Select a candidate to see the original page.”
  - Loading.
  - Missing file: “Original file is not on disk.” (matches `GET /file` 404 `"file missing"`).
  - PDF: `<iframe title="Source document" src={/api/documents/${id}/file} />` (credentials are cookies on same origin via the Vite `/api` proxy). Under the iframe, a collapsible “Extracted text” `<pre>` with highlight.
  - Image: `<img alt={filename} src={.../file} />` plus extracted text.
  - Text/XML: extracted text only (or iframe for `text/plain` if the browser renders it).

- Highlight implementation for extracted text: escape HTML, wrap the first match of `quote` (trim, collapse whitespace, case-insensitive). If `quote` is empty, no mark.

- PDF.js is optional. If added, load it as a production dependency of `frontend/` (not a `devDependency`; deploy skips those). Do not pull a second PDF stack if the iframe + text pane already lets the owner verify the line. Prefer shipping iframe + text highlight first; PDF.js only if iframe is blank in the target browsers.

- Accept / Reject stay `POST /proposals/{id}/accept` and `/reject`. After accept/reject, refresh the list; if the selected id is gone, select the next pending item for the same `document_id` (so a stack of lines from one report stays on that source).

- Do not add an editor, crop tool, or “correct the PDF.”

### Data model

No new tables. Use `Proposal.quote`, `Proposal.document_id`, `Proposal.payload`, `Document.extracted_text`, `Document.mime_type`, `Document.filename`, `Document.storage_path`.

Schema continues to come from SQLAlchemy `Base.metadata.create_all` on API boot. Do not add an Alembic revision in this phase.

### Tests to add

- `backend/tests/test_phase9.py` (or extend `test_phase4.py`):

  - Upload a text/PDF lab that produces at least one `lab_line` proposal; `GET /documents/{id}/file` returns 200, body starts with `%PDF` or the original bytes, and `Content-Disposition` contains `inline` (not `attachment`).
  - `GET /documents/{id}/text` includes a substring of the proposal `quote`.
  - Proposal list payload still includes `document_id` and `quote`.
  - Profile A cannot read profile B’s document file/text (create two profiles; request B’s document while the URL uses A’s id if such a path exists; at minimum, a document id that belongs to another profile in a second household is 404 — if tests remain single-household, assert a missing id is 404 and that listing is profile-filtered).
  - Existing Phase 4 tests (`test_text_pdf_bmp_auto_files_and_source_opens`, etc.) still pass.

- Parser tests in `test_lab_parse.py` are unchanged.

### Out of scope

- Editing or annotating the stored PDF.
- Pixel-accurate OCR bounding boxes.
- Imaging-report proposal UI specifics (Phase 13). The pane must not assume `type === lab_line` for *loading* the source; it may keep lab-specific payload formatting in the list.
- Full office-document preview (xlsx).
- Audit-log screen, FHIR, public signup.

---

## Decisions Needed From User / Open Design Questions *(planning-time)*

1. PDF highlight: search-in-text vs true OCR bounding boxes.
   **Answer:** Search-in-text plus quote highlight in extracted text. No glyph boxes unless a later phase stores them. (Interview.)

2. Must Phase 9 wait for Phase 10’s inline file endpoint?
   **Answer:** No. Phase 9 may land the minimal `Content-Disposition: inline` change (or a shared helper) so the iframe works. Phase 10 then covers all source links, mime mapping, and types that still download.

3. PDF.js vs native iframe.
   **Answer:** Native iframe plus extracted-text highlight. PDF.js was not added.

---

## Risks *(planning-time)*

- Scanned PDFs have little or no text layer; iframe shows the page but search cannot highlight. Mitigate with the extracted-text pane (OCR already fills `extracted_text` when the page had almost no text).
- Quote strings may not match extract order (wrapped columns, hyphenation). Show the quote even when `indexOf` fails.
- `Content-Disposition: attachment` (current `FileResponse`) will keep triggering Save As inside an iframe until the inline header lands.
- Same-origin iframe needs the existing `/api` proxy; do not point the iframe at a different origin without cookies.
- Scope creep into a PDF editor or OCR box pipeline.

---

## Definition of Done

- [x] Review inbox shows the original source (file and/or extracted text) beside the selected proposal.
- [x] The proposal `quote` is highlighted in extracted text when that substring exists, and the text pane scrolls to it.
- [x] PDFs and images open in the pane without a Save-As dialog (inline file response for those types).
- [x] Selecting another proposal updates the source pane; Accept/Reject still file or drop the candidate as today.
- [x] Document file/text GETs are household-scoped via the session; they do not trust client-sent household/user ids.
- [x] Layout is usable at ~390px width (stacked or tabbed, 44px targets).
- [x] No PDF editing. No OCR bounding-box storage.
- [x] New tests cover inline disposition and proposal `document_id`/`quote`; existing Phase 4 document tests still pass.

---

## What Shipped *(post-build — add only once Status is ✅ Built)*

Split review inbox: selectable proposal list and a source pane that loads the selected candidate’s original file and extracted text. The proposal `quote` is highlighted in extracted text (first case-insensitive match, including collapsed whitespace) and the text pane scrolls to the mark. PDFs use an iframe to `GET /documents/{id}/file`; images use `<img>`; text/XML highlight in place. Accept/Reject remain on the selected item and, after a decision, select the next pending line from the same document.

Backend helper `backend/app/documents.py` serves previewable types with `Content-Disposition: inline` and a resolved media type. File and text GETs (and the proposal list) are household-scoped from the session; other-household ids return 404. `GET /documents/{id}/text` also returns `filename` and `mime_type`. File endpoint accepts HEAD so the pane can probe without downloading the body.

## Deviations from the Original Plan *(post-build)*

- PDF.js was not added; iframe plus extracted-text highlight was enough once inline disposition landed.
- Filename and mime are returned on `/text` instead of adding a dedicated proposal-detail endpoint.
- Proposal list and source pane scroll independently so a large inbox stays usable; mobile still stacks list above source with a sticky Accept/Reject row.
- Phase 10 still owns the full download-vs-inline matrix for office types (xlsx/csv).

## Verification Performed *(post-build)*

- `pytest tests/test_phase9.py`: 8 passed (inline PDF bytes and disposition, quote in extracted text, `document_id`/`quote` on the list, missing file 404, other-household 404, profile-filtered list).
- `pytest tests/test_phase4.py`: 8 passed against the new file/text helpers.
- Live API through the Vite `/api` proxy: `GET /documents/{id}/file` returned `Content-Disposition: inline` and `%PDF` bytes; HEAD returned 200 after the route allowed it.
- Vite served the new Inbox module (source pane copy present). A full click-through in a headed browser was not run in this session.

## Deferred / Not Built *(post-build)*

- PDF.js text-layer search on the rendered PDF.
- Pixel OCR bounding boxes.
- Full Phase 10 mime/disposition matrix for types that should still download.
