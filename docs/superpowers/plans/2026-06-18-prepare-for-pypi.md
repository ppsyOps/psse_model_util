# Prepare for PyPI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `psse-model-util` cleanly publishable to public PyPI — scrub all real-system (PJM / MMWG / NERC-IDC / real utility) references, relicense to MIT, fix the broken package layout so the wheel installs correctly, and record the publishing automation work on the roadmap.

**Architecture:** Five sequential phases on branch `prep/pypi-publish` (already created off `origin/main` @ `470a825`). Scrub and functional API changes land first on current file paths; the package relocation (`src/` layout) lands last so git move history is clean and every prior edit travels with the move. Each phase ends with a verification gate (`ruff` + `pytest`, plus a wheel-content check in the restructure phase).

**Tech Stack:** PDM (env/deps), Hatchling (build + CalVer from `__about__.py`), Ruff (lint), pytest + pytest-cov (40% gate). Python 3.11.

**Verified baseline (origin/main @ 470a825):** `ruff check` clean on tracked source; `pytest` = 435 passed, 1 skipped. The current wheel is structurally broken (flat top-level layout). These are the invariants every phase must preserve (test count may rise as fixtures/tests are edited).

**Decisions locked (from the user):**
- Publish target: **public PyPI** (stable) + **TestPyPI** (rehearsals) + **PEP 440 pre-releases** for beta. (Accounts/automation = Phase 6 roadmap, not built here.)
- License: **MIT**.
- `flowgate.DEFAULT_SC`: **remove it — `sc` becomes a required argument** (no default).
- Scrub scope: **entire repo** (GitHub going public): code, README, ARCHITECTURE, CLAUDE.md, PROJECT_PLAN, `docs/superpowers/**`, test fixtures.
- **DO NOT TOUCH** the PSS/E RAW-format field named `IDC` (Multi-Terminal DC bus number) in `dataformat/rawx_raw_map.csv` and every `.raw`/`.rawx` fixture. That `IDC` is file-format spec, unrelated to NERC's Interchange Distribution Calculator. Scrub `IDC` only where it refers to the NERC tool (prose/docstrings).
- `tests/legacy_tests/` is untracked and not shipped/run — **out of scope** for this plan (flag only).

**Resolved (user, 2026-06-18):** `NATIVE_AREAS`/`NEIGHBOR_AREAS` stay as constants in `common/constants.py`, set to the generic synthetic areas matching `Model_1.raw` (`{1:'CENTRAL', 2:'EAST', 3:'CENTRAL_DC'}` + `{4:'EAST_COGEN1', 5:'WEST', 6:'EAST_COGEN2'}`); `INCLUDE_AREAS` stays derived from them. For now, users set their own footprint by **manually editing `NATIVE_AREAS`** in that file. The richer design — store native areas in `user_config_dir` (not in the repo/package) and **discover** neighbor areas from the model via `find_tie_lines` instead of hardcoding — is **deferred to a future logged issue** (sketch captured in `PROJECT_PLAN.md`), not built in this plan.

---

## File Structure

After this plan, the repo root holds only project/config/docs/tests; all importable code lives under `src/psse_model_util/`:

```
src/psse_model_util/
    __init__.py          # exposes __version__ (+ optionally Model/ModelComparison)
    __about__.py         # version source of truth (moved from root)
    model.py  compare.py  flowgate.py  raw_to_rawx.py  inch.py  version.py
    common/  dataformat/  util/
tests/                   # unchanged location; NOT shipped in wheel
docs/                    # specs, plans, RAW_TO_RAWX.md
pyproject.toml  README.md  pdm.lock  LICENSE  ARCHITECTURE.md  CLAUDE.md  PROJECT_PLAN.md
.github/workflows/ci.yml  cd.yml
```

Imports are already `psse_model_util.`-namespaced everywhere, so the move requires **no source edits** — only `git mv` plus `pyproject.toml`/CI path updates.

---

## Phase 1 — MIT license + metadata polish

**Files:**
- Create: `LICENSE`
- Modify: `pyproject.toml`

- [ ] **Step 1.1: Add the MIT LICENSE file**

Create `LICENSE` (repo root) with the standard MIT text, copyright line: `Copyright (c) 2026 cadvena`.

- [ ] **Step 1.2: Update `pyproject.toml` `[project]` metadata**

Replace `license = { text = "Proprietary" }` with:

```toml
license = "MIT"
license-files = ["LICENSE"]
```

Add (after `keywords`):

```toml
classifiers = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Science/Research",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3 :: Only",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Topic :: Scientific/Engineering",
]

[project.urls]
Homepage = "https://github.com/ppsyOps/psse_model_util"
Repository = "https://github.com/ppsyOps/psse_model_util"
Issues = "https://github.com/ppsyOps/psse_model_util/issues"
```

- [ ] **Step 1.3: Fix the deprecated Ruff config keys** (emits a warning every run)

Change `[tool.ruff]` `select`/`ignore` to the `lint` section:

```toml
[tool.ruff]
target-version = "py311"
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "W", "I"]
ignore = ["E501"]
```

- [ ] **Step 1.4: Verify build metadata renders**

Run: `pdm run hatch build -t wheel && pipx run twine check dist/*` (or `pdm run python -m twine check dist/*`)
Expected: `PASSED`; metadata shows `License: MIT`. Then `git add -A && git commit -m "chore(packaging): relicense to MIT, add classifiers/urls, fix ruff lint config"`.

> Note: `license = "MIT"` (SPDX string) + `license-files` requires Hatchling ≥ 1.27 / a recent build backend. If `twine check` or the build complains about the SPDX form, fall back to `license = { text = "MIT" }` and keep the classifier — functionally equivalent for this purpose.

---

## Phase 2 — Scrub real-system references in code (non-flowgate)

**Files:**
- Modify: `common/constants.py`, `model.py`, `compare.py`, `raw_to_rawx.py`

- [ ] **Step 2.1: Genericize `common/constants.py` area dictionaries**

Current (lines ~22–33) has a commented generic block followed by **live real footprint data** — real area numbers mapped to real utility codes (values redacted here; they are the confidential footprint being removed):

```python
# (commented generic placeholders, already present)
# NATIVE_AREAS = {1: 'CENTRAL', 2: 'EAST', 3: 'CENTRAL_DC'}
# NEIGHBOR_AREAS = {4: 'EAST_COGEN1', 5: 'WEST', 6: 'EAST_COGEN2'}

# live dicts: real area-number -> utility-code mappings  <-- REMOVE
NATIVE_AREAS = {<real native area codes — redacted>}
NEIGHBOR_AREAS = {<real neighbor area codes — redacted>}
```

Replace the whole block so the **live** dicts are the generic synthetic ones and no real names/PJM wording remain:

```python
# Native areas — the system footprint used as the default for area filtering and
# comparison. These are synthetic placeholders matching the bundled sample model
# (tests/data/Model_1.raw). Edit this to your own system's area numbers/names.
# (Future: load from user_config_dir + discover neighbors from the model — see PROJECT_PLAN.)
NATIVE_AREAS = {1: 'CENTRAL', 2: 'EAST', 3: 'CENTRAL_DC'}

# Neighboring areas (synthetic; matches tests/data/Model_1.raw).
NEIGHBOR_AREAS = {4: 'EAST_COGEN1', 5: 'WEST', 6: 'EAST_COGEN2'}
```

Leave `INCLUDE_AREAS = NEIGHBOR_AREAS.copy() | NATIVE_AREAS.copy()` and `NETWORK_DF_COMPARISON_QUERIES` as-is — they now derive from the generic dicts. No `PJM` wording remains in the comments.

- [ ] **Step 2.2: Run the suite — this is the functional-change checkpoint**

Run: `pdm run pytest -q`
Expected: still green. The area-number change (200s → 1–6) only affects defaults; tests pass `native_areas` explicitly (see `tests/test_network_queries.py:17-18`). If anything fails, it depended on the real defaults — inspect and fix the test to pass explicit areas, do **not** restore real data.

- [ ] **Step 2.3: Scrub `model.py` prose/comments**

- Line ~52 (module docstring): `large power system models such as MMWG or IDC cases used in the Eastern Interconnection.` → `large bulk-electric-system (BES) power-flow models.`
- Line ~1163 (comment): `Skip substations, as they are complex and not present in IDC models.` → `Skip substations, as they are complex and not present in typical planning models.`
- Lines ~1909 & ~1925 (docstrings): `The MMWG based .rawx files do not contain harmonics/timeseries data` → `RAW-sourced .rawx files do not contain harmonics/timeseries data`.
- `__main__` demo block (~2705–2720): delete the commented real-system file path at line ~2705 (a `# fp = Path(r'K:\...redacted real case file...')` reference) entirely. At lines ~2713 & ~2716, genericize the comments — `# Dictionary of native ... areas ...` → `# Example native areas`, `# Dictionary of neighboring areas ...` → `# Example neighboring areas` — and **keep** the synthetic example dict values (`{101: 'CENTRAL', ...}`).

- [ ] **Step 2.4: Scrub `model.py` docstring example paths**

Lines ~322, ~1969, ~2575, ~2578, ~2620 hardcode the author's local absolute path (a `C:\...\psse_model_util\...` location). Replace each with a neutral placeholder, e.g. `>>> fp = r"path/to/Model_1.raw"` and the cache-path example with `path/to/cache/Model_1.model`.

- [ ] **Step 2.5: Scrub `util/contingency_util.py` real paths**

Lines ~60 & ~75: the real hardcoded `BASE_FOLDER` / `CONTINGENCY_DEFINITIONS_FOLDER` paths (a `K:\...redacted...` location) → neutral placeholders, e.g. `BASE_FOLDER = r''  # set to your contingencies folder` (or `Path.cwd()`-relative). This file is WIP/excluded from coverage but still ships in the wheel, so the real path must go.

- [ ] **Step 2.6: Scrub `compare.py`**

Line ~1046 comment: `# Filter the models to a subset of areas (PJM + 1st tier)` → `# Filter the models to a subset of areas (native + first-tier neighbors)`.

- [ ] **Step 2.7: Scrub `raw_to_rawx.py`**

Line ~6 docstring: `Industry power-system files distributed by ISOs (PJM, ISO-NE, MISO, etc.)` → `Industry power-system files distributed by ISOs/RTOs`.

- [ ] **Step 2.8: Verify + commit**

Run: `pdm run ruff check . --exclude .claude --exclude tests/legacy_tests && pdm run pytest -q`
Expected: ruff clean; pytest green.
Then: `git add -A && git commit -m "refactor: scrub real-system (PJM/MMWG/IDC) references from library code"`.

---

## Phase 3 — flowgate: remove `DEFAULT_SC`, make `sc` required + scrub

**Files:**
- Modify: `flowgate.py`
- Test: `tests/test_flowgate_parse.py`, `tests/test_flowgate_collect.py`, `tests/test_flowgate_resolve.py`, `tests/test_flowgate_cli.py`

- [ ] **Step 3.1: Update flowgate tests first (TDD)** — for each occurrence of `DEFAULT_SC` and the `"PJM"` literal in the four test files: (a) drop assertions like `assert flowgate.DEFAULT_SC == "PJM"` / `assert fg.sc == "PJM"` defaulting, and any `test_*default*sc*` test that asserts the default; (b) replace remaining `"PJM"`/`"OTHER"` SC literals with generic tokens `"SCA"` / `"SCB"`; (c) update calls to `filter_by_sc(fgs)` and `collect_*(...)` to pass an explicit `sc="SCA"`.

- [ ] **Step 3.2: Run the flowgate tests — expect failures**

Run: `pdm run pytest tests/test_flowgate_parse.py tests/test_flowgate_collect.py tests/test_flowgate_resolve.py tests/test_flowgate_cli.py -q`
Expected: FAIL (tests now require an `sc` arg / generic tokens the code/fixture don't yet provide).

- [ ] **Step 3.3: Change the flowgate API**

In `flowgate.py`:
- Line ~31: delete `DEFAULT_SC: str = "PJM"          # SC = Security Coordinator`.
- Line ~81 dataclass field comment: `sc: str  # Security Coordinator (e.g. "PJM"). Empty string means no SC declared.` → `sc: str  # Security Coordinator (e.g. "SCA"). Empty string means no SC declared.`
- Line ~342: `def filter_by_sc(fgs: list[Flowgate], sc: str = DEFAULT_SC) -> list[Flowgate]:` → `def filter_by_sc(fgs: list[Flowgate], sc: str) -> list[Flowgate]:`
- Line ~862 (collect function signature): `sc: str = DEFAULT_SC,` → `sc: str,` (make required; move it before any defaulted params if needed to keep valid signature ordering).
- Line ~889 docstring: `sc : str, default DEFAULT_SC` → `sc : str` (drop "default").
- Check the CLI `argparse` (`--sc`): if it has `default=DEFAULT_SC`, change to `required=True` (no default).

- [ ] **Step 3.4: Run flowgate tests — expect pass**

Run: same command as Step 3.2.
Expected: PASS.

- [ ] **Step 3.5: Rename + genericize the synthetic fixture**

- `git mv tests/data/synthetic_pjm.mon tests/data/synthetic_flowgates.mon`
- In the renamed `.mon`: replace `SC PJM`→`SC SCA`, `TP PJM PJM`→`TP SCA SCA`, the `SC OTHER`/`TP OTHER OTHER` block → `SC SCB`/`TP SCB SCB`, and the description `'synthetic non-PJM'` → `'synthetic SCB flowgate'`.
- In `tests/build_synthetic_mon.py`: `OUT_FILE = DATA_DIR / "synthetic_pjm.mon"` → `"synthetic_flowgates.mon"`; rename `MODEL_1_PJM_AREAS`→`MODEL_1_SC_AREAS`; replace all `"PJM"` SC literals with `"SCA"`, the non-PJM/`OTHER` path with `"SCB"`, and update the `pjm_branches`/`non_pjm`/`pjm_gen` variable names + comments to generic (`sc_branches`, `other_branches`, `sc_gen`).
- Update any test that references the old filename (`synthetic_pjm.mon`) or the SC tokens accordingly.

- [ ] **Step 3.6: Verify + commit**

Run: `pdm run ruff check . --exclude .claude --exclude tests/legacy_tests && pdm run pytest -q`
Expected: ruff clean; full suite green.
Then: `git add -A && git commit -m "refactor(flowgate)!: require sc argument (remove DEFAULT_SC), genericize PJM fixtures"`.

---

## Phase 4 — Scrub docs (public-facing + design history)

**Files:**
- Modify: `README.md`, `ARCHITECTURE.md`, `CLAUDE.md`, `PROJECT_PLAN.md`, `docs/RAW_TO_RAWX.md`, `docs/superpowers/specs/2026-05-29-flowgate-key-elements-design.md`, `docs/superpowers/specs/2026-06-16-tie-lines-neighborhood-design.md`, `docs/superpowers/plans/2026-05-29-flowgate-key-elements.md`, `docs/superpowers/plans/2026-06-16-tie-lines-neighborhood.md`

- [ ] **Step 4.1: Shipped/public docs** — replace every NERC-IDC / MMWG / PJM use-case phrasing with generic wording:
  - `README.md:11` `comparing IDC summer vs. winter Bulk Electric System (BES) models` → `comparing seasonal Bulk Electric System (BES) model variants (e.g. summer vs. winter)`.
  - `ARCHITECTURE.md:280,294` and `docs/RAW_TO_RAWX.md:240`: `MMWG/IDC scale` → `large BES scale (tens of thousands of buses)`; `Anonymized BES model needed for MMWG/IDC-scale UAT` → `Anonymized large-scale BES model needed for scale UAT`.
  - `CLAUDE.md:84`: `Large BES models (MMWG/IDC scale)` → `Large BES models`.
  - `PROJECT_PLAN.md:14`: `comparing IDC summer vs. winter models` → `comparing seasonal BES model variants`.

- [ ] **Step 4.2: Design-history docs (`docs/superpowers/**`)** — these are PJM-heavy (SC examples, `DEFAULT_SC = "PJM"`, real utility tokens like `LGEE`, "production sample" references, IDC use-cases). Replace `PJM`→`SCA`, the secondary SC `OTHER`/`LGEE`→`SCB`, `DEFAULT_SC = "PJM"` references → "`sc` is required (no default)", and IDC/MMWG use-case phrasing → generic BES wording. These are historical records; preserve structure, just neutralize the references.

- [ ] **Step 4.3: Final scrub sweep — must come back empty**

Run (the `--exclude` skips this meta-plan, which documents the scrub by naming the categories and contains the sweep pattern itself; all real *values* in it are redacted):
```bash
grep -rniE "\bPJM\b|\bMMWG\b|\bMISO\b|\bERCOT\b|\bWECC\b|\bNYISO\b|\bCAISO\b|\bLGEE\b|\bEKPC\b|\bDUQ\b|\bOVEC\b|interchange distribution calculator|panc|idctr|sum24|C:\\\\Personal" . \
  --include=*.py --include=*.md --include=*.mon --include=*.csv \
  --exclude-dir=.claude --exclude-dir=.venv --exclude-dir=legacy_tests --exclude-dir=.git \
  --exclude=2026-06-18-prepare-for-pypi.md
```
Expected: **no matches** (the PSS/E `IDC` format field in `rawx_raw_map.csv`/`.raw` is the only allowed `IDC`, and is not matched by these patterns). If anything remains, scrub it.

> `tests/legacy_tests/` is **out of scope** (untracked, not shipped) but contains real IDC case paths in `example_compare.py`. If it is ever committed to the public repo, scrub it first.

- [ ] **Step 4.4: Verify + commit**

Run: `pdm run pytest -q` (docs-only, but confirm nothing broke).
Then: `git add -A && git commit -m "docs: scrub real-system references repo-wide for public release"`.

---

## Phase 5 — Restructure to `src/` layout (the wheel fix)

**Files:**
- Move: package code → `src/psse_model_util/`
- Modify: `pyproject.toml`, `.github/workflows/cd.yml`
- Create: `src/psse_model_util/__init__.py` content

- [ ] **Step 5.1: Move the package into `src/psse_model_util/`**

```bash
mkdir -p src/psse_model_util
git mv model.py compare.py flowgate.py raw_to_rawx.py inch.py version.py __about__.py __init__.py src/psse_model_util/
git mv common dataformat util src/psse_model_util/
```
(Keep at root: `tests/`, `docs/`, `pyproject.toml`, `README.md`, `pdm.lock`, `ARCHITECTURE.md`, `CLAUDE.md`, `PROJECT_PLAN.md`, `LICENSE`, `.github/`, `.gitignore`.) No import edits — imports are already `psse_model_util.`-prefixed.

- [ ] **Step 5.2: Populate `src/psse_model_util/__init__.py`** (currently ~empty)

```python
"""psse_model_util — read, edit, validate, and compare PSS/E power system models."""

from psse_model_util.__about__ import __version__

__all__ = ["__version__"]
```

- [ ] **Step 5.3: Update `pyproject.toml` paths**

```toml
[tool.hatch.version]
path = "src/psse_model_util/__about__.py"

[tool.hatch.build.targets.wheel]
packages = ["src/psse_model_util"]
```
Remove the now-irrelevant `exclude = ["*.cmd", "dist/"]` (nothing of that sort lives under the package dir now; harmless to keep but cleaner to drop). In `[tool.coverage.run]`: set `source = ["src/psse_model_util"]` and re-path the omit entries (`util/contingency_util.py` → `src/psse_model_util/util/contingency_util.py`, `inch.py` → `src/psse_model_util/inch.py`, `version.py` → `src/psse_model_util/version.py`; drop `one_line_diagram.py` if that file does not exist).

- [ ] **Step 5.4: Update `cd.yml` version-read path**

In `.github/workflows/cd.yml` the "Read version" step does `open('__about__.py')` → change to `open('src/psse_model_util/__about__.py')`.

- [ ] **Step 5.5: Reinstall the editable env (src layout changes the install)**

Run: `pdm install`
Expected: success. Then `pdm run python -c "import psse_model_util; print(psse_model_util.__version__)"` → prints `2026.4.4`.

- [ ] **Step 5.6: Verify the wheel is now correct**

Run:
```bash
pdm run hatch build -t wheel
pdm run python -c "import zipfile,glob; w=sorted(glob.glob('dist/*.whl'))[-1]; print('\n'.join(n for n in zipfile.ZipFile(w).namelist() if not n.endswith('/')))"
```
Expected: every code path is under `psse_model_util/...` (e.g. `psse_model_util/model.py`, `psse_model_util/common/constants.py`). **No** top-level `model.py`, `pdm.lock`, `pyproject.toml`, etc.

- [ ] **Step 5.7: Clean-venv install smoke test (the real proof)**

```bash
python -m venv /tmp/pmu-smoke
/tmp/pmu-smoke/bin/python -m pip install dist/psse_model_util-*.whl   # Windows: use Scripts\python.exe
/tmp/pmu-smoke/bin/python -c "from psse_model_util.model import Model; from psse_model_util.compare import ModelComparison; import psse_model_util; print('OK', psse_model_util.__version__)"
```
Expected: `OK 2026.4.4`. (Use a PowerShell-equivalent venv path on Windows.)

- [ ] **Step 5.8: Full gate + commit**

Run: `pdm run ruff check . --exclude .claude --exclude tests/legacy_tests && pdm run pytest -q`
Expected: ruff clean; pytest green (count matches Phase 4).
Then: `git add -A && git commit -m "build!: adopt src/ package layout so the wheel installs as psse_model_util"`.

---

## Phase 6 — Roadmap: "Prepare for PyPI" umbrella (accounts, rehearsal, CD)

**Files:**
- Modify: `PROJECT_PLAN.md`

- [ ] **Step 6.1: Add a "Prepare for PyPI" phase to `PROJECT_PLAN.md`**

Add a new phase table (or a Phase 4 sub-section) capturing the work this plan does *not* execute — the publishing setup that needs human/account action:

| ID | Item | Status |
|----|------|--------|
| P.1 | Real-system scrub (PJM/MMWG/IDC) + MIT relicense | ✅ (this plan) |
| P.2 | `src/` package layout — wheel installs as `psse_model_util` | ✅ (this plan) |
| P.3 | Register PyPI + TestPyPI accounts, enable 2FA, configure **Trusted Publishing** (OIDC) for `ppsyOps/psse_model_util` | ⬜ |
| P.4 | TestPyPI rehearsal: publish a `…b1` pre-release, `pip install --pre` from TestPyPI in a clean venv, smoke test | ⬜ |
| P.5 | CD automation: extend `cd.yml` to publish on tag — `v*b*/rc*`→TestPyPI, `vX.Y.Z`→PyPI — via `pypa/gh-action-pypi-publish` + `id-token: write` (switch trigger from push-to-`main` to tag `v*`) | ⬜ |
| P.6 | Document the beta convention in `__about__.py`/README: CalVer + PEP 440 suffix (`2026.5.0b1`, `rc1`); beta installs via `pip install --pre` | ⬜ |
| P.7 | **Native-areas config + neighbor discovery** ([issue #8](https://github.com/ppsyOps/psse_model_util/issues/8) — see sketch below) | ⬜ |

**P.7 design sketch (deferred — confirmed with user 2026-06-18):**
- **Native areas → user config, not a shipped constant.** Store the user's footprint in `user_config_dir/native_areas.json` (path already provided by `common/dirs.py`; platformdirs, never in the repo/package). Provide `get_native_areas()` / `set_native_areas()` helpers; fall back to the synthetic `NATIVE_AREAS` constant when no config file exists, so the package still works out of the box.
- **Neighbors → discovered, not hardcoded.** Add `Network.find_neighbor_areas(native_areas, kv_min, kv_max)` built on the existing `find_tie_lines` (the areas on the far side of native tie lines). Delete the `NEIGHBOR_AREAS` constant.
- **Decouple comparison queries.** `NETWORK_DF_COMPARISON_QUERIES` is currently built from `INCLUDE_AREAS` at import time (`constants.py:47`). Refactor it into a `build_comparison_queries(include_areas)` function so the area list can come from config/discovery per comparison instead of module load.
- Interim behavior (this plan): users manually edit `NATIVE_AREAS` in `common/constants.py`.

- [ ] **Step 6.2: Commit**

`git add PROJECT_PLAN.md && git commit -m "docs(roadmap): add Prepare-for-PyPI umbrella + deferred native-areas config/discovery"`.

---

## Self-Review notes

- **Spec coverage:** item 0 (scrub) → Phases 2–4; item 1 (standard structure) → Phase 5; item 2 (MIT) → Phase 1; items 4–6 (accounts/rehearsal/CD) → Phase 6 roadmap. ✔
- **IDC landmine:** Phase 2/4 scrub steps explicitly target NERC-IDC prose only; the format-field `IDC` is excluded by the regex in Step 4.3 and called out in the locked decisions. ✔
- **Ordering:** functional changes (constants areas, flowgate API) carry their own pytest checkpoints before the move; the file relocation is last and verified by wheel-content + clean-venv install. ✔
- **Token consistency:** SC placeholders are `SCA`/`SCB` everywhere (fixture, tests, design docs). ✔
