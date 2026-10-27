# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Two apps live in this repo — know which one you're touching

1. **The real product (Docker/VPS):** FastAPI `backend/` + Vite/React 18 `frontend/` + Postgres + Orthanc, wired by `docker-compose.yml`. Phases 1–8 are complete here, and all new work (Phases 9+) targets this stack.
2. **A stale preview port (Grok App Builder):** root `package.json`, `src/` (TanStack Start, React 19, Better Auth, Kysely), `server/`, `scripts/*.mjs`, `migrations/*.sql`, `public/__grok/`, `.grok/`. It only ever reached Phase 2. `AGENTS.md` / `AGENTS.project.md` are instructions for *that* sandbox (port 8080, `/workspace`, "no Docker/FastAPI") and do **not** apply to the Docker app. Don't edit it unless asked.

The product spec is `household-phr-agent-prompts.md` (the "standing spec" + Phases 1–8). New phase plans live in `docs/phases/` (start with `docs/phases/README.md` for the index, build-order hints, and quick context).

## Commands

Run the stack (web on http://localhost:5173; API is only reachable through the web proxy at `/api`):

```bash
cp .env.example .env          # set BOOTSTRAP_USERNAME / BOOTSTRAP_PASSWORD
docker compose up --build
docker compose --profile proxy up --build      # adds Caddy on :80 (deploy/Caddyfile)
docker compose --profile local-llm up          # adds Ollama; not for an 8 GB box with Orthanc
```

Backend tests (pytest; tests are copied into the API image, which has tesseract/poppler for OCR tests):

```bash
docker compose run --rm api pytest tests                          # all
docker compose run --rm api pytest tests/test_phase4.py -k <name> # one test
# or locally: cd backend && pip install -r requirements.txt && pytest tests/test_lab_parse.py
```

Tests set `DATABASE_URL` to SQLite files under `/tmp` at import time and override `get_db`; `conftest.py` sets `AUTH_DISABLED=1`. Tests are organised per phase (`test_phase3.py` … `test_phase7.py`) plus `test_lab_parse.py`; follow that pattern.

Frontend: `cd frontend && npm run build` (`tsc && vite build`) is the type check. No frontend tests or linter.

Backup drill: `./scripts/backup.sh` then `./scripts/restore.sh backup_YYYYMMDD_HHMMSS`.

The root `npm run test|lint|typecheck` scripts belong to the preview port only.

## Backend architecture (`backend/app/`)

- `main.py` — the FastAPI app and most routes (profiles, encounters, orders, labs, trends, imaging, documents, jobs, proposals/review inbox, C-CDA export, DICOM, Orthanc proxy, viewer). A cookie-auth HTTP middleware guards everything except `PUBLIC_PATHS`. On startup: `Base.metadata.create_all` (no Alembic tree exists, despite it being in requirements — derive any migration number at build time), load `seed/analytes.csv`, bootstrap the single household user from env.
- `chart_routes.py` — manual-chart CRUD router (medications, allergies, problems, providers, insurance, etc.); `_profile()` scopes lookups to the caller's household.
- `auth.py` — Argon2 passwords, httpOnly `session` cookie stored in DB, optional TOTP (enforced only once enrolled), active profile stored on the session row. `AUTH_DISABLED` env bypasses auth (tests only).
- `models.py` / `schemas.py` — SQLAlchemy models and Pydantic I/O.
- Document pipeline: upload stores bytes on the `documents` volume (`STORAGE_ROOT`) and enqueues a `Job`. `worker.py` is a separate container polling a Postgres queue (`FOR UPDATE SKIP LOCKED`) and calling `processor.process_job`, which uses `extraction.py` (PDF text/OCR, lab-line parsing, panel/date detection) and optionally `model_client.py`. Output is `Proposal` rows reviewed in the Review inbox; accepting a proposal files clinical rows.
- `lab_matching.py` — maps raw lab names to `CanonicalAnalyte` via aliases, unit normalization, abnormal flags.
- `ccda.py` — C-CDA build/parse (import and export round-trip). `orthanc_client.py` — DICOM upload/delete against Orthanc.

Frontend is essentially one file, `frontend/src/App.tsx` (react-router), calling the API via `frontend/src/api.ts` with `/api` prefix; Vite's dev server proxies `/api` → `api:8000` and strips the prefix.

## Domain rules that must hold

- Every clinical row belongs to a `profile`; every profile to a `household`. Resolve the household server-side from the session — never trust client-sent household/user ids.
- No hard deletes of profiles or filed rows; void with `entered_in_error`.
- An office visit and a same-day lab are separate encounters linked by an order.
- Lab trends join on canonical analyte (from `seed/analytes.csv`), not panel name. Keep original value, unit, and reference range. Never invent ranges, never plot mixed units on one axis, don't add LOINC codes not in the seed file.
- Model extraction is off by default and produces proposals only; auto-file stays off unless the user's setting enables it.
- The footer disclaimer is always visible.
- No real names or sample patients in the repo; fixtures are synthetic (`backend/tests/fixtures/synthetic_ccd.xml`, DOB 1980-01-01).
- Non-goals: multi-household SaaS, public signup, FHIR server, HL7 v2, med-interaction engine, audit-log screen, native apps, local LLM in default Compose.
- Orthanc/Postgres/Ollama ports stay unpublished; only `web:5173` is published. Respect the Compose `mem_limit`s (8 GB target box).

## Workflow

Work is organised as phases: `/plan-phase` writes a doc from `docs/phases/phase-template.md` and opens a GitHub issue (repo `rwb5510/PHR`), `/start-phase` builds in a worktree under `.claude/worktrees/`, `/finish-phase` opens the PR, `/cleanup-phases` removes merged worktrees. Update the phase doc's status and post-build sections when shipping.
