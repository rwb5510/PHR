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

## Phase 6 — Optional model

- Settings: mode off (default), remote, or local. Base URL and model name. No API key field; key is `LLM_API_KEY` env var only.
- Per-upload “Use model” defaults off and is disabled when mode is off.
- OpenAI-compatible client. Local Ollama and remote vendor both work by changing URL and model.
- Output validated against the app’s JSON schema before any proposal is saved. Invalid JSON fails extraction; document stays stored.
- Model proposals appear in the review inbox and are marked `from_model`.
- `llm_autofile` defaults false and is labeled unsafe in the UI. When false, no model proposal becomes a chart row by itself.
- Accepting a lab proposal applies the Phase 3 matching and unit rules.
- Logs contain document id, duration, success/failure only. Never document text, the key, or the raw response.
- Compose profile `local-llm` starts Ollama and nothing else. Do not run it on the 8 GB box together with Orthanc.
- With mode off, Phase 4 and Phase 5 behavior is unchanged. No outbound model connection.
