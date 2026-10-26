# Household PHR

Personal household health record. FastAPI + Vite + Postgres + Orthanc, run with Docker Compose.

## Quick start

```bash
cp .env.example .env
# set BOOTSTRAP_USERNAME and BOOTSTRAP_PASSWORD
docker compose up --build
```

Open http://localhost:5173 and sign in with the bootstrap user. There is no signup page.

- Web: http://localhost:5173 (the only published app port)
- API is reached through the web proxy at `/api`
- Default `docker compose up` does not start Ollama or a second proxy
- Memory limits: Postgres 1g, Orthanc 2g, worker 1g, api 512m, web 128m
- First boot creates the household user from env
- Footer disclaimer is always present

Postgres, Orthanc (8042 and 4242), and Ollama stay on the Docker network.

## Required env vars

See `.env.example`.

- `BOOTSTRAP_USERNAME` / `BOOTSTRAP_PASSWORD` — first user
- `POSTGRES_PASSWORD`
- `ORTHANC_USER` / `ORTHANC_PASS`
- `LLM_API_KEY` — only if you later turn the model on in Settings

## Acceptance path

1. Sign in.
2. Create a profile. For the CCD fixture use date of birth **1980-01-01**.
3. Enter a medication.
4. Upload `backend/tests/fixtures/synthetic_ccd.xml` on Documents.
5. Open Review inbox and accept proposals. Sodium appears on the trend.
6. Download C-CDA from the profile or emergency page.

## Authenticator (TOTP)

Login works without TOTP until you enroll it under Settings. After it is enabled, login without a valid code fails.

## Reverse proxy

TLS is the outer proxy’s job. The app works behind Caddy, Traefik, or nginx.

- Forward `Host`, `X-Forwarded-Proto`, `X-Forwarded-For`
- Allow upload bodies of at least 50 MB
- Proxy the public hostname to the `web` service on port 5173

Optional Compose profile if this machine has no proxy yet:

```bash
docker compose --profile proxy up --build
```

## Local language model

Ollama is a Compose profile, not part of the default 8 GB stack. Do not run it next to Orthanc on an 8 GB box.

```bash
docker compose --profile local-llm up
```

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
