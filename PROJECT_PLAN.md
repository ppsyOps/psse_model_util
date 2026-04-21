# PROJECT_PLAN.md — psse_model_util

> **Purpose:** Master project plan, decisions, scope, and status. Each major work item gets its own Discord channel when we start it. This document is the source of truth for what we're doing and why.

*Last updated: 2026-04-21 by Advena*

---

## 🎯 Project Summary

**`psse_model_util`** is a Python library for reading, editing, validating, and comparing PSS/E power system models (RAW v33/34/35 and RAWX formats). The two central components are:

- **`Model`** — reads, validates, edits, and visualizes a single PSS/E model. Supports RAW → RAWX conversion, DataFrame-based access to all network sections, NetworkX one-line diagram in memory, area/voltage filtering, pickle cache.
- **`ModelComparison`** — compares two `Model` instances. Identifies added/removed equipment, impedance changes, load/generation changes, and — critically — topological changes like sectionalizations and merges/bypasses. Primary use case: comparing IDC summer vs. winter models.

**Core import format:** RAWX (JSON). RAW files (v33/34/35) are first converted via `raw_to_rawx.py` using `dataformat/rawx_raw_map.csv` as the field mapping, then loaded by the standard RAWX loader.

---

## ✅ Decisions Locked

| Topic | Decision |
|-------|----------|
| Build system | **PDM** for dependency management + lock file; **Hatch** for build metadata and publishing |
| GUI / visualization | **React web UI** — all GUIs target the browser for OS interoperability. No desktop/Qt. |
| One-line diagram | Scrap current Plotly `draw_one_line`. Rebuild from scratch as a React web app fed by a Python API. |
| Anonymizer | Text portions of names only (never numbers). Single persistent master mapping file so real name always → same fake name across all models (required for `ModelComparison` correctness). |
| RAWX export bug | Known issue, low priority. Log it and address in Phase 2. |
| Channel strategy | One Discord channel per active work item. Keeps LLM context clean and focused. |
| Versioning (Phase 1.1) | Keep `version.py` `__version__` hardcoded string for now (Option A). Manually edit before releases. Calver makes this trivial. |
| Versioning (Phase 1.2) | Retire `version.py` + `build_utils/` entirely. Migrate to `hatch version` with `[tool.hatch.version]` sourcing from `__about__.py` (or `src/_version.py`) — modern best practice. Hatch manages all bumps. |

---

## 🗂️ Project Phases

### Phase 1 — Foundation & Hygiene
> Goal: Clean base before adding features.

| ID | Item | Channel | Status |
|----|------|---------|--------|
| 1.1 | Migrate build system: `setup.py` → PDM + Hatch | #hatch-pdm-migration | 🔄 In Progress |
| 1.2 | Project structure review — dead code ID (review w/ Chris before removing) | TBD | ⬜ Queued |
| 1.3 | README.md + ARCHITECTURE.md + RAW-to-RAWX technical doc | TBD | ⬜ Queued |
| 1.4 | Test coverage baseline: add `pytest` + `pytest-cov`, measure gaps | TBD | ⬜ Queued |
| 1.5 | Fix CSV export — missing columns (e.g. `network_acline.csv` missing bus numbers; root cause: `index=False` + index holds bus fields) | TBD | ⬜ Queued |
| 1.6 | Code quality pass — linting (`ruff`), type hints, docstring audit | TBD | ⬜ Queued |
| 1.7 | Remove `arrow` dependency — replace `arrow.Arrow` usage in `common/dataframe_util.py` with stdlib `datetime` | TBD | ⬜ Queued |

### Phase 2 — Core Correctness
> Goal: Fix known bugs, improve output quality.

| ID | Item | Channel | Status |
|----|------|---------|--------|
| 2.1 | RAWX export bug — diff exported JSON vs. known-good `.rawx`; likely small fix | TBD | 🐛 Logged / Low Priority |
| 2.2 | Improve comparison output — add equipment names, area names, bus names to sectionalization/bypass CSVs | TBD | ⬜ Queued |
| 2.3 | **Model anonymizer** — bidirectional name scrambler, persistent master mapping file, safe to share BES models for UAT | TBD | ⬜ Queued |
| 2.4 | Test suite expansion — target meaningful coverage on parser, compare, graph modules | TBD | ⬜ Queued |

### Phase 3 — Features
> Goal: Add missing capabilities.

| ID | Item | Channel | Status |
|----|------|---------|--------|
| 3.1 | **One-line diagram** — React web UI, research OSS patterns, Python API backend | TBD | ⬜ Queued |
| 3.2 | IDEV/INCH export — model update + export (partially scaffolded) | TBD | ⬜ Queued |
| 3.3 | Model validation — detect unreasonable impedance, disconnected buses, data quality issues | TBD | ⬜ Queued |
| 3.4 | Model editing — update bus data, change equipment parameters, write back | TBD | ⬜ Queued |

### Phase 4 — Polish
> Goal: Production-grade finishing.

| ID | Item | Channel | Status |
|----|------|---------|--------|
| 4.1 | CURRENT / open-source integration assessment — evaluate contributions or design patterns | TBD | ⬜ Queued |
| 4.2 | Performance profiling — large model load time, graph generation | TBD | ⬜ Queued |
| 4.3 | API docs — Sphinx or mkdocs-material | TBD | ⬜ Queued |

---

## 🌐 Web UI Strategy

**All GUIs are browser-based.** No desktop frameworks (no PyQt, no Tk, no Electron).

**Stack:**
- **Frontend:** React (likely Vite scaffold). Component library TBD (MUI or shadcn/ui are candidates).
- **Backend:** Python FastAPI (or Flask) serving model data as JSON to the React frontend.
- **Packaging:** The web UI lives in a separate `psse_model_util_ui/` package or monorepo subfolder.

**Why React:**
- OS-agnostic — runs in any browser, on any machine
- D3.js / React Flow / Cytoscape.js are all strong options for graph/one-line rendering
- Separates visualization concerns from the core model library cleanly

**One-line diagram approach (Phase 3.1):**
- Scrap current `draw_one_line` (Plotly, doesn't scale)
- Python backend exposes a `/graph` endpoint returning node/edge JSON from `model.network.graph()`
- React frontend renders using **React Flow** or **Cytoscape.js** (both handle large graphs well; React Flow has better UX polish, Cytoscape has better power-system layout algorithms — evaluate in 3.1)
- Interactivity goals: pan/zoom, click node for bus detail, highlight paths

---

## 📌 Notes
- No `setup.py`, `pyproject.toml`, or tests directory found in copied code — these need to be created from scratch in 1.1 and 1.4
- `common/pyqt5.py` exists — likely dead code; flag for 1.2 review
- `delete_me.py` at root — obviously dead; confirm with Chris before removing
- `build_utils/` has a legacy wheel build script (`.cmd`) — replace entirely with Hatch in 1.1
- `__pycache__` for both Python 3.10 and 3.11 present — target Python version to be set in `pyproject.toml` in 1.1

---

## 🔁 Channel Map

| Channel | Topic |
|---------|-------|
| #psse-model-util | General / onboarding |
| #project-plan | Master plan and status |
| #hatch-pdm-migration | Phase 1.1 — build system migration |
