# Household PHR — Phase 4

Personal health record. Phase 4 implements document intake, extraction, OCR, Postgres job queue, and review inbox.

## Acceptance tests

All logic acceptance criteria are covered by automated tests in `backend/tests/test_phase4.py`:

- Text PDF of a BMP produces sodium, potassium, and other matched lines as chart components with units and ranges; source PDF opens
- Scanned image with no text layer gets OCR text stored
- Unknown analyte name waits in the inbox and is not charted
- Duplicate upload is rejected with a visible warning
- Worker crash mid-job leaves the file stored and the job retryable

## Run tests

```bash
cd backend
pip install -r requirements.txt
# Requires tesseract-ocr and poppler-utils for OCR tests
python -m pytest tests/test_phase4.py -v
```

## Run stack

```bash
docker compose up --build
```

Backend: http://localhost:8000  
Frontend: http://localhost:5173  
Worker: processes the Postgres job queue

Documents stored in the `documents` volume at `/data/documents`.

Seed analytes load automatically on startup from `seed/analytes.csv`. No extra LOINC codes.

## Size limit

Default maximum upload size is 50 MB per file. Documented here and enforced on upload.

## Phase 4 scope only

No C-CDA mapping, language model, or DICOM upload. XML files are stored and their text is shown; clinical XML parsing is Phase 5.
