# Household PHR — Phase 5

Personal health record. Phase 5 implements C-CDA import and export.

## Acceptance

- Import of synthetic CCD into a profile with matching DOB, accept proposals, export, import into a second empty profile with the same DOB produces equal counts for problems, allergies, medications, and sodium results.
- Conflicting date of birth blocks auto-file and shows the mismatch in the proposal.
- Tests in `backend/tests/test_phase5.py` cover the round trip and the DOB-mismatch case.
- No ONC certification claimed.

## Run tests

```bash
cd backend
pip install -r requirements.txt
python -m pytest tests/test_phase5.py -v
```

## Export

On a profile page, use the Export CCD link. Author text states this is a self-generated personal record. Template OIDs are from the HL7 CDA R2.1 Implementation Guide (cited in `backend/app/ccda.py`).

## Phase 5 scope only

No language model, no DICOM upload. XML that is not a ClinicalDocument remains a plain document as in Phase 4.
