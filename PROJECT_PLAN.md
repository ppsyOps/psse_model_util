# PROJECT_PLAN.md — psse_model_util

> **Purpose:** Master project plan, decisions, scope, and status. Each major work item gets its own Discord channel when we start it. This document is the source of truth for what we're doing and why.

*Last updated: 2026-04-30 by Advena*

---

## 🎯 Project Summary

**`psse_model_util`** is a Python library for reading, editing, validating, and comparing PSS/E power system models (RAW v33/34/35 and RAWX formats). The two central components are:

- **`Model`** — reads, validates, edits, and visualizes a single PSS/E model. Supports RAW → RAWX conversion, DataFrame-based access to all network sections, NetworkX one-line diagram in memory, area/voltage filtering, pickle cache.
- **`ModelComparison`** — compares two `Model` instances. Identifies added/removed equipment, impedance changes, load/generation changes, and — critically — topological changes like sectionalizations and merges/bypasses. Primary use case: comparing seasonal BES model variants (summer vs. winter).

**Core import format:** RAWX (JSON). RAW files (v33/34/35) are first converted via `raw_to_rawx.py` using `dataformat/rawx_raw_map.csv` as the field mapping, then loaded by the standard RAWX loader.

---

## ✅ Decisions Locked

| Topic               | Decision                                                                                                                                                                                |
| ------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Build system        | **PDM** for dependency management + lock file; **Hatch** for build metadata and publishing                                                                                              |
| GUI / visualization | **React web UI** — all GUIs target the browser for OS interoperability. No desktop/Qt.                                                                                                  |
| One-line diagram    | Scrap current Plotly `draw_one_line`. Rebuild from scratch as a React web app fed by a Python API.                                                                                      |
| Anonymizer          | Text portions of names only (never numbers). Single persistent master mapping file so real name always → same fake name across all models (required for `ModelComparison` correctness). |
| RAWX export bug     | Known issue, low priority. Log it and address in Phase 2.                                                                                                                               |
| Channel strategy    | One Discord channel per active work item. Keeps LLM context clean and focused.                                                                                                          |

---

## 🗂️ Project Phases

### Phase 1 — Foundation & Hygiene

> Goal: Clean base before adding features.

| ID      | Item                                               | Channel                                  | Status      |
| ------- | -------------------------------------------------- | ---------------------------------------- | ----------- |
| **1.1** | **Migrate build system: `setup.py` → PDM + Hatch** | **#hatch-pdm-migration**                 | ✅ Completed |
| 1.2     | Project structure review — dead code ID            | #project-structure (1496271268712943626) | ✅ Completed |
| 1.3     | README.md + ARCHITECTURE.md + RAW-to-RAWX doc      | #documentation (1496293366495969372)     | ✅ Completed |
| 1.4     | Test coverage baseline & unit tests                | #unit-tests (1496574177472286944)        | ✅ Completed |
| 1.5     | Fix CSV export                                     | #csv-fix (1496588327745487110)           | ✅ Completed |
| 1.6     | Code quality pass (linting)                        | #ci-linting (1497211799030726828)        | ✅ Completed |

### Phase 2 — Core Correctness

> Goal: Fix known bugs, improve output quality.

| ID      | Item                             | Channel                               | Status                   |
| ------- | -------------------------------- | ------------------------------------- | ------------------------ |
| **2.1** | **CI/CD Pipeline Setup**         | **#ci-linting (1497211799030726828)** | ✅ **Completed**          |
| 2.2     | RAWX export bug                  | TBD                                   | 🐛 Logged / Low Priority |
| **2.3** | **Improve comparison output**    | **#2-3-comparison-output (1499205715875598347)** | ✅ **Completed**          |
| 2.4     | **Model anonymizer**             | TBD                                   | ⬜ Queued                 |
| 2.5     | Test suite expansion             | TBD                                   | ⬜ Queued                 |
| 2.6     | **Bus Data Enrichment Strategy** | TBD                                   | ⬜ Queued                 |

### Phase 3 — Features

> Goal: Add missing capabilities.

| ID  | Item                                | Channel | Status   |
| --- | ----------------------------------- | ------- | -------- |
| 3.1 | **One-line diagram** — React web UI | TBD     | ⬜ Queued |
| 3.2 | IDEV/INCH export                    | TBD     | ⬜ Queued |
| 3.3 | Model validation                    | TBD     | ⬜ Queued |
| 3.4 | Model editing                       | TBD     | ⬜ Queued |

### Phase 4 — Polish

> Goal: Production-grade finishing.

| ID  | Item                                         | Channel | Status   |
| --- | -------------------------------------------- | ------- | -------- |
| 4.1 | CURRENT / open-source integration assessment | TBD     | ⬜ Queued |
| 4.2 | Performance profiling                        | TBD     | ⬜ Queued |
| 4.3 | API docs — Sphinx or mkdocs-material         | TBD     | ⬜ Queued |

### Phase P — Prepare for PyPI

> Goal: Publish `psse-model-util` to public PyPI (stable) and TestPyPI (rehearsals),
> with PEP 440 pre-releases for beta. Plan: `docs/superpowers/plans/2026-06-18-prepare-for-pypi.md`.

| ID  | Item                                                                                                                     | Status      |
| --- | ------------------------------------------------------------------------------------------------------------------------ | ----------- |
| P.1 | Real-system scrub (PJM/MMWG/IDC/real paths) + MIT relicense                                                               | ✅ Completed |
| P.2 | `src/` package layout — wheel installs cleanly as `psse_model_util`                                                       | ✅ Completed |
| P.3 | Register PyPI + TestPyPI accounts, enable 2FA, configure **Trusted Publishing** (OIDC) for `ppsyOps/psse_model_util`      | ⬜ Queued    |
| P.4 | TestPyPI rehearsal: publish a `…b1` pre-release, `pip install --pre` from TestPyPI into a clean venv, smoke test          | ⬜ Queued    |
| P.5 | CD automation: extend `cd.yml` to publish on tag — `v*b*/rc*`→TestPyPI, `vX.Y.Z`→PyPI — via `pypa/gh-action-pypi-publish` | ⬜ Queued    |
| P.6 | Document the beta convention: CalVer + PEP 440 suffix (`2026.5.0b1`, `rc1`); beta installs via `pip install --pre`        | ⬜ Queued    |
| P.7 | Native-areas config + neighbor discovery ([issue #8](https://github.com/ppsyOps/psse_model_util/issues/8))                | ⬜ Queued    |

---

## 🔁 Channel Map

| Channel                                  | Topic                                |
| ---------------------------------------- | ------------------------------------ |
| #psse-model-util                         | General / onboarding                 |
| #project-plan                            | Master plan and status               |
| #hatch-pdm-migration                     | Phase 1.1 — build system migration   |
| #project-structure (1496271268712943626) | Phase 1.2 — Project structure review |
| #documentation (1496293366495969372)     | Phase 1.3 — Documentation            |
| #unit-tests (1496574177472286944)        | Phase 1.4 — Test coverage baseline   |
| #csv-fix (1496588327745487110)           | Phase 1.5 — CSV export fix           |
| #ci-linting (1497211799030726828)        | Phase 1.6 & 2.1 — Linting and CI/CD  |
