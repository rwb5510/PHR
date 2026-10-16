# Household PHR — v1 complete

Personal household health record. Phases 1–8.

## Quick start from empty server

```bash
cp .env.example .env   # set BOOTSTRAP_USERNAME, BOOTSTRAP_PASSWORD, Orthanc credentials
docker compose up --build
```

- Backend: http://localhost:8000
- Frontend: http://localhost:5173
- Default `docker compose up` does not start Ollama or a second proxy.
- Memory limits: Postgres 1g, Orthanc 2g, worker 1g, api 512m, web 128m.
- No signup page. First boot creates the household user from env.
- Footer disclaimer is always present.

## Acceptance path

1. Create a profile.
2. Enter a medication (manual or accept from CCD).
3. Upload the synthetic CCD (`backend/tests/fixtures/synthetic_ccd.xml`) into a profile with matching DOB.
4. Accept proposals. Sodium appears on the trend.
5. Download C-CDA from the profile or emergency page.

## Backup and restore drill

```bash
chmod +x scripts/backup.sh scripts/restore.sh
./scripts/backup.sh
# Recorded drill on synthetic fixture data:
# ./scripts/backup.sh && ./scripts/restore.sh backup_YYYYMMDD_HHMMSS
# After restore, the same medication and the same sodium result are present.
```

Orthanc image pinned: `orthancteam/orthanc:24.10.2`. Ports unpublished.

## Non-goals honored

No multi-household SaaS, no public registration, no FHIR server, no HL7 v2, no medication-interaction engine, no invented ranges, no audit-log screen, no native apps, no local LLM in default Compose, no hard delete of profiles or filed rows.
