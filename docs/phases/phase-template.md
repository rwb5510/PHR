<!--
  Phase doc template — copy this file to phase-NN-short-name.md (or phase-NNx-name.md for a
  hub's lettered sub-phase) and fill in the placeholders below.

  - Number/name the file to match the phase: phase-12-example-feature.md. Hub sub-phases use
    a trailing letter: phase-12a-sub-feature.md.
  - Sections marked "(planning-time)" are written when the phase is proposed, before any code
    exists. Sections marked "(post-build)" are only added once the phase actually ships —
    leave them out of the doc entirely while status is still 📋 Planned.
  - Workflow: /plan-phase writes this doc and opens the GitHub issue. /start-phase isolates
    the build in a worktree and marks it in progress. /finish-phase ships it and marks it
    built. /cleanup-phases removes the worktree/branch once merged.
-->

# Phase {NN} — {Descriptive Name}

**Status:** {📋 Planned / 🔨 In Progress / ⏸️ Deferred / ✅ Built}
**GitHub Issue:** [#{issue}](https://github.com/{owner}/{name}/issues/{issue})
**Prerequisites:** {other phases or infra that must land first, or "none"}
**Blocks:** {other phases/work waiting on this one, or "none"}
**Parent hub:** {[phase-N-plan.md](phase-N-plan.md), if this is a hub child — omit line otherwise}

---

## Goal *(planning-time)*

{One paragraph: what this feature does and why it's being built.}

---

## Features *(planning-time)*

{Bullet list of user-facing capabilities this phase delivers.}

---

## Design *(planning-time)*

{Narrative of the approach and key tradeoffs. Break into subsections as needed for this repo's
stack (e.g. Database, Backend/API, Frontend, Security) — adjust headings to match how this
repo actually organizes a change.}

---

## Decisions Needed From User / Open Design Questions *(planning-time)*

1. {question}
   **Answer:** *(pending)*

---

## Risks *(planning-time)*

{What could go wrong — technical risk, data risk, scope creep, external dependency risk.}

---

## Definition of Done

- [ ] {concrete, checkable item}

---
---

## What Shipped *(post-build — add only once Status is ✅ Built)*

{Summary of what was actually built.}

## Deviations from the Original Plan *(post-build)*

{Anywhere the build diverged from the Design section above, and why.}

## Verification Performed *(post-build)*

{Concrete checks run — tests, manual verification, anything that couldn't be verified and
needs follow-up.}

## Deferred / Not Built *(post-build)*

- {item}
