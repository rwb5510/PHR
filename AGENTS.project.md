# Household chart — project spec

Personal health record for one household. One login can hold several people and switch whose chart is open. Later household members may edit every profile. This is not a clinic system and not a medical device.

The platform contract in `/workspace/AGENTS.md` wins on tooling. This file wins on product behavior.

## Where this build differs from the VPS prompt pack

The prompt pack at `artifacts/household-phr-agent-prompts.md` targets a private Docker server. This preview cannot run that stack. Do not add Docker, Orthanc, FastAPI, Redis, Celery, Alembic, a `.env` file, or TOTP.

Use what is already here:

- TanStack Start, React, Tailwind v4, file routes under `src/routes/`
- Postgres through `@/lib/db` and `migrations/*.sql` (Neon when published, embedded Postgres in the preview)
- Sign-in through the existing Better Auth wiring only: email and password, Google, and X. Do not edit files under `src/lib/auth/` except `src/lib/auth/email-password.ts`
- No authenticator-app (TOTP) flow. The platform does not support it. Do not fake one
- Uploads in later phases go in Postgres, not the server disk
- The dev server is `npm run dev` via `/workspace/startup.sh`, bound for the preview. Do not start Vite directly

## Status

Phase 2 is implemented: providers, encounters, problems, allergies, medications, immunizations, procedures, family history, social history, vitals, implants, insurance, pharmacy, emergency contacts, appointments, and a printable emergency snapshot. Void hides a row. Do not redo Phase 1 or Phase 2. Start at Phase 3 when asked.

Implement one phase per session. Do not start the next phase in the same session.

1. Sign-in, household, profiles, shell. Done.
2. Manual chart: providers, encounters, problems, allergies, medications, immunizations, procedures, family history, social history, vitals, implants, insurance, pharmacy, emergency contacts, appointments, printable emergency snapshot. **Current.**
3. Orders, lab reports, canonical analytes, trends, imaging reports by modality.
4. Document upload, text extraction, review inbox. OCR only if a pure-JS or already-installed path exists. Do not `apt` install Tesseract.
5. C-CDA import and export.
6. Optional model extraction, off by default, proposals only.
7. DICOM studies with an in-browser viewer and a link from a report to a study. No Orthanc.
8. Dashboard polish and a backup export the user can download.

## Rules that already apply

- Every clinical row belongs to a `profile`. Every profile belongs to a `household`.
- Server functions use `authMiddleware`. Resolve the caller's household on the server. Never trust a household id or user id sent by the browser.
- Any member of the household may read and edit every profile in it. No other household's rows are visible.
- The active profile is stored on the membership row, not only in the browser.
- Void with `entered_in_error`. Do not hard-delete clinical rows.
- An office visit and a same-day lab are separate encounters, linked by an order.
- Lab trends join on a canonical analyte, not the panel name. Keep the original value, unit, and reference range. Do not invent ranges. Do not plot mixed units on one axis. The seeded analyte list and unit factors are in the prompt pack. Do not add LOINC codes.
- Model output never auto-files unless a setting is on. That setting stays off.
- Footer disclaimer, always visible: "This is a personal household record. It is not a medical device, not an emergency service, and not a substitute for your clinicians or the original report. Ranges shown are the ranges that came with the result."
- No sample patients. No real names in the repo.

## Visual system

Paper chart, not a generic dashboard.

- Paper `#f3efe6`, card `#fffcf7`, ink `#1c1915`, muted `#5e584e`, line `#e4dccf`
- One green `#1f4b43` for primary actions
- One red `#8d3b32` reserved for abnormal results and destructive actions
- Sans: "Public Sans". The person's name: "Newsreader"
- No gradient heroes, no emoji icons, no purple theme
- Mobile first. Tap targets at least 44px. Profile switcher always reachable

## Phase 1 done when

- A signed-in person gets one household automatically
- They can add two people, edit them, and switch the active person
- The switch survives a refresh
- A guessed profile id from another household is rejected
- Empty sections say they come later. Do not build chart forms yet
- Disclaimer is in the footer
- Sign-out works. Signed-out visitors can reach sign-in. Gate sessions must not see a redundant sign-in button while already signed in
