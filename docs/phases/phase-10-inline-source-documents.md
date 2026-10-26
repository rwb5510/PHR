# Phase 10 — In-browser source documents

**Status:** 📋 Planned
**GitHub Issue:** [#2](https://github.com/rwb5510/PHR/issues/2)
**Prerequisites:** none (if Phase 9 already shipped an inline helper, extend it rather than forking a second file endpoint)
**Blocks:** none

---

## Goal *(planning-time)*

Lab report, imaging, and document list “Open source” / filename links already use `target="_blank"` (`frontend/src/App.tsx` LabReportView ~332, ImagingLibrary ~416, Documents ~489). The API still serves those URLs as downloads: `FileResponse(..., filename=doc.filename)` in `GET /documents/{document_id}/file` (`backend/app/main.py` ~386) sets `Content-Disposition: attachment`, so Chromium/Edge open a Save As dialog instead of a tab. This phase serves previewable originals inline with a correct Content-Type so a new tab shows the PDF or image. Spreadsheets that the browser cannot preview may still download.

---

## Features *(planning-time)*

- Clicking “Open source document”, a document filename, or an imaging “source” link opens a **new browser tab** that displays PDF, JPEG, PNG, TIFF, TXT, MD, and XML when the browser can render them.
- Response uses `Content-Disposition: inline` plus a real `Content-Type` (not `application/octet-stream` when the suffix is known).
- Links keep `target="_blank"` and `rel="noreferrer"` (existing markup). Same-origin `/api/documents/{id}/file` so the session cookie is sent (`SameSite=Lax`).
- CSV / XLS / XLSX / JSON (Phase 15 types) may still trigger a download; say so in the Documents help line if those types are already accepted, otherwise no UI copy change is required here.
- No full Microsoft Office previewer.

---

## Design *(planning-time)*

### Root cause

Starlette/FastAPI `FileResponse(path, filename=doc.filename, media_type=doc.mime_type)` defaults `content_disposition_type="attachment"`. Passing `filename` is what names the download; it does not by itself choose inline. Upload stores `file.content_type` from the client (`main.py` ~352), which is often empty or `application/octet-stream`.

### Backend / API

Single endpoint, no new path:

```
GET /documents/{document_id}/file
```

Implementation sketch:

1. Load `Document` by id. 404 if missing or file not on `STORAGE_ROOT`.
2. **Access:** join `Profile`; require `profile.household_id == request.state.user.household_id`. 404 if not. Do not trust query-string profile ids. (If Phase 9 already added this check, keep one helper.)
3. Resolve media type:

   | Suffix / stored mime | Serve as |
   |---|---|
   | `.pdf` / `application/pdf` | `application/pdf` |
   | `.jpg` `.jpeg` / `image/jpeg` | `image/jpeg` |
   | `.png` / `image/png` | `image/png` |
   | `.tif` `.tiff` / `image/tiff` | `image/tiff` |
   | `.txt` | `text/plain; charset=utf-8` |
   | `.md` | `text/markdown; charset=utf-8` or `text/plain` |
   | `.xml` | `application/xml` |
   | `.csv` | `text/csv` (browser may still download) |
   | `.xls` | `application/vnd.ms-excel` (download) |
   | `.xlsx` | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` (download) |
   | `.json` | `application/json` (tab of text is fine) |

   Prefer a suffix map over a lying client mime. If neither is known, keep stored mime.

4. Return `FileResponse(path, media_type=resolved, filename=doc.filename, content_disposition_type=disposition)` where `disposition` is `inline` for pdf/image/text/xml/json and `attachment` for xls/xlsx (and csv if we observe browsers still downloading — `inline` is still preferred so a new tab can show CSV as text).

5. Optional: `Content-Security-Policy` is **not** added here. Do not add a CSP that blocks `https://grok.com` on the unrelated preview stack. This FastAPI app has no CSP today.

CCD export (`GET /profiles/{id}/export-ccd`) stays `attachment`; that is a download by design.

### Frontend

- LabReportView, Documents list, ImagingLibrary: keep `<a href={/api/documents/${id}/file} target="_blank" rel="noreferrer">`. No `download` attribute.
- Inbox iframe (Phase 9) uses the same URL.
- Do not `window.open` blob URLs that strip cookies unless fetch-with-credentials + blob is required for a picky browser; prefer the plain GET.
- If a future auth change puts the API on another host, this design must be revisited (cookie won’t follow `noreferrer` cross-site). Today Vite proxies `/api` to the API and Compose Caddy does the same for production.

### Data model

No schema change. `create_all` unchanged.

### Tests

- Extend `test_phase4.py` `test_text_pdf_bmp_auto_files_and_source_opens` (already `GET /documents/{id}/file` and asserts `%PDF`):

  - Assert `content-disposition` is `inline` (case-insensitive, may include `filename=`).
  - Assert `content-type` starts with `application/pdf`.

- Upload a PNG (existing OCR test) and assert `image/png` + `inline`.
- Upload a `.txt` and assert `text/plain` + `inline`.
- If xlsx is accepted by then (Phase 15), assert it is allowed to be `attachment`; if not yet accepted, skip.

### Out of scope

- In-app PDF.js (Phase 9 optional).
- LibreOffice / Excel Online preview.
- Changing storage paths or SHA duplicate rules.
- Hard-delete of documents.

---

## Decisions Needed From User / Open Design Questions *(planning-time)*

1. Spreadsheets and CSV: preview vs download.
   **Answer:** Browsers that cannot preview may download. That is acceptable. No Office previewer in this phase.

2. Should `filename` stay on the Content-Disposition line when inline?
   **Answer:** *(pending — default yes, so “Save as” from the PDF viewer still has the original name)*

---

## Risks *(planning-time)*

- Some browsers ignore `inline` for `application/octet-stream`. Mitigate with suffix-based mime.
- TIFF preview is uneven in Chrome; PNG/JPEG/PDF are the important cases. TIFF may still download; acceptable.
- Phase 9 iframe and this tab share one endpoint — a regression to `attachment` breaks both.
- `rel="noreferrer"` is fine same-origin; do not add `download`.

---

## Definition of Done

- [ ] `GET /documents/{id}/file` serves PDF, JPEG, PNG, and TXT with `Content-Disposition: inline` and a matching Content-Type.
- [ ] Lab report “Open source document” opens a new tab that displays the PDF (no Save-As prompt for PDF).
- [ ] Document list filename links and imaging source links behave the same.
- [ ] Links remain `target="_blank"` `rel="noreferrer"` with no `download` attribute.
- [ ] File GET is household-scoped from the session cookie.
- [ ] CSV/XLSX may still download; no Office previewer.
- [ ] CCD export remains an attachment.
- [ ] Tests assert inline disposition and PDF content-type; existing Phase 4 source-open test still passes.
