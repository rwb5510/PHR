# Phase Documentation

Each file covers one phase: completed phases have a summary of what was built, decisions
made, and known issues. Planned phases have architecture and design detail. These files are
the primary context handoff between sessions.

The original product was built from `household-phr-agent-prompts.md` as Phases 1–8 (auth,
manual chart, labs, documents, C-CDA, optional model, DICOM, dashboard). Those phases are
complete in the Docker/FastAPI app under `backend/` and `frontend/`. Numbered files in this
folder start at Phase 9.

---

## Index

| File | Phase | Status |
|---|---|---|
| [phase-9-review-inbox-source.md](phase-9-review-inbox-source.md) | 9 — Review inbox source viewer | ✅ Built |
| [phase-10-inline-source-documents.md](phase-10-inline-source-documents.md) | 10 — In-browser source documents | ✅ Built |
| [phase-11-multi-panel-names.md](phase-11-multi-panel-names.md) | 11 — Multi-panel names on one document | ✅ Built |
| [phase-12-panel-catalog.md](phase-12-panel-catalog.md) | 12 — Panel catalog and data management | ✅ Built |
| [phase-13-imaging-document-proposals.md](phase-13-imaging-document-proposals.md) | 13 — Imaging-report proposals from documents | 📋 Planned |
| [phase-14-lab-results-matrix.md](phase-14-lab-results-matrix.md) | 14 — Lab results matrix over time | 📋 Planned |
| [phase-15-structured-lab-file-import.md](phase-15-structured-lab-file-import.md) | 15 — Structured CSV / XLS / XLSX / JSON lab import | 📋 Planned |

---

## Quick Context for New Sessions

- Intended local/VPS product: FastAPI + Vite + Postgres + Orthanc via `docker-compose.yml`
  (`backend/`, `frontend/`). Preview/TanStack Start under `src/` is a separate, incomplete
  port (Phases 3–8 not built there).
- Schema is created with SQLAlchemy `Base.metadata.create_all` on API boot. Alembic is in
  requirements but there is no `alembic/` tree. Do not pin concrete Alembic revision numbers;
  if a build adds a migration, derive the number at build time.
- Auth: one household, one bootstrap user, httpOnly session cookie, optional TOTP. Every
  clinical row is scoped to `profile_id` in that household. Do not trust client-sent
  household or user ids.
- Labs join on canonical analytes from `seed/analytes.csv`. Do not invent reference ranges.
  Do not add LOINC codes that are not in that seed file.
- Documents: PDF/TIFF/JPG/PNG/TXT/MD/XML, 50 MB default. Review inbox for proposals.
  Auto-file only when the standing spec's lab/C-CDA rules pass.
- Non-goals: multi-household SaaS, public signup, FHIR, HL7 v2, med-interaction engine,
  audit-log screen, native apps, hard-delete of filed rows.
- **Build-order hint for 9–15:** implement **9, then 11, then 14** first (inbox source,
  multi-panel names, results matrix). 10, 12, 13, and 15 are medium. They are standalone
  phases, not a hub. None are hard blockers for planning; for build, 9 makes 13's inbox
  nicer, 11 makes 14's grouping honest, and 12 improves 11/15 matching. Phase 11 should
  ship heuristic panel titles even if the catalog (12) is later.
