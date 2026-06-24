# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Toolchain

- **PDM** — dependency management and virtual environment. Primary tool for `install`, `run`, and `lock`.
- **Hatch** — build backend (via `pdm run hatch build`). Manages calver versioning sourced from `__about__.py`.
- **Ruff** — linter and import sorter. Config in `pyproject.toml` under `[tool.ruff]`. Line length 120; E501 ignored.
- **pytest + pytest-cov** — test runner. Coverage threshold: 90% (CI gate, `pyproject.toml` `fail_under`).
- **Sphinx** — API docs (`docs/`), generated from Google-style docstrings via `autodoc` + `napoleon`. Built with `sphinx-build -W` (warnings-as-errors) in CI. Docstrings are Google-style throughout `src/`.

## Common Commands

```bash
# Install all dependencies
pdm install

# Install dev/lint extras only
pdm install -G dev

# Lint
pdm run ruff check .

# Run all tests
pdm run pytest

# Run a single test file
pdm run pytest tests/test_phase_2_2.py

# Run a specific test by name
pdm run pytest tests/test_phase_2_2.py -k "test_name"

# Test with coverage
pdm run pytest --cov=psse_model_util --cov-report=term-missing

# Build
pdm run hatch build

# Check current version
hatch version
```

## Architecture

### Data flow

All file types (RAW and RAWX) converge on a single internal `rawx dict` before being materialized into DataFrames:

```
.raw  →  raw_to_rawx.raw_file_to_rawx_dict()  →  rawx dict
.rawx →  common.json_util.load_and_clean_json()  →  rawx dict
                              ↓
            Model.__init__() → Network._create_dataframe()
                              ↓
              model.network.<section>  (typed, indexed pd.DataFrame)
```

The field mapping between RAW column names and RAWX field names is entirely data-driven: `dataformat/rawx_raw_map.csv` is loaded at parse time, filtered to the detected PSS/E version (v34 or v35).

### Key classes

- **`Model`** (`model.py`) — primary user-facing class. Composes `General`, `Network`, `Harmonics`, `TimeSeries`.
- **`Network`** (`model.py`) — holds one `pd.DataFrame` per PSS/E section (`bus`, `acline`, `transformer`, `generator`, `load`, etc.) plus a lazy `nx.Graph`. Extends `AbstractSection`.
- **`ModelComparison`** (`compare.py`) — compares two `Model` instances. `compare_network_dfs()` produces outer-joined DataFrames with `_delta` and `presence` columns. `compare_graph()` detects added/removed edges, sectionalizations, and bypasses.
- **`flowgate`** (package) — `.mon` flowgate parsing and key-facility neighborhood extraction. Parses PSS/E `.mon` flowgate-definition files, resolves their monitored/contingency elements against a `Model`, expands an n-hop bus neighborhood, and emits DataFrames (branches, generators, 3-winding transformers, unresolved). Public API (`extract_key_facilities`, `parse_mon_file`, `resolve_elements`, `neighborhood_buses`, `collect_key_facilities`, dataclasses `Flowgate`/`FlowgateElement`/`ResolvedSeed`) is re-exported from `flowgate/__init__.py`; the implementation lives in underscore-prefixed submodules (`_parse`, `_resolve`, `_graph`, `_collect`, `_api`, `_types`).

### DataFrame metadata convention

Every network DataFrame carries `df._metadata` (a dict) with three keys set during `Network._create_dataframe()`:

| Key | Use |
|-----|-----|
| `id_cols` | Columns used as the DataFrame index (unique equipment id) |
| `bus_cols` | Columns holding bus numbers — drives `filter_by_area()` and `graph()` |
| `data_type` | Per-column dtype hints for coercion |

These are defined in `dataformat/rawx_json_template.py` and applied once at load time. Any new network section must have an entry there.

### NetworkX graph

`Network.graph()` builds a `nx.Graph` lazily. Node IDs are tuples: `("bus", ibus)`, `("generator", ibus, id)`, etc. 3-winding transformers get a synthetic central node `("transformer", i, j, k)` connected to all three buses. Call `graph(regenerate=True)` to force a rebuild.

### Pickle cache

`Model.__init__()` checks `site_cache_dir/<stem>.model` before parsing. If found (and `force_recalculate=False`), it loads directly from pickle. Large BES models are slow to parse; the cache is critical for interactive use.

### Runtime directories

All runtime paths are resolved by `common/dirs.py` via `platformdirs`:

| Constant | Purpose |
|----------|---------|
| `site_cache_dir` | Pickle cache (`.model`, `.modcomp`) |
| `site_data_dir` | CSV export output |
| `site_temp_dir` | Temp JSON from RAW conversion |
| `site_log_dir` | Log files |

## Key Files

| File | Role |
|------|------|
| `dataformat/rawx_raw_map.csv` | Source of truth for RAW ↔ RAWX field mapping per PSS/E version |
| `dataformat/rawx_json_template.py` | RAWX section schema: fields, data_type, id_cols, bus_cols |
| `common/constants.py` | `INCLUDE_AREAS`, `DEFAULT_KV_FILTER`, `NETWORK_DF_COMPARISON_QUERIES`, `ALT_PATH_MAX_PATH_LENGTH`, `RESILIENT` |
| `__about__.py` | Single source of truth for version string |
| `version.py` | Deprecated shim — do not use |
| `flowgate/__init__.py` | Public API surface for `.mon` flowgate parsing / key-facility extraction (re-exports underscore submodules) |
| `docs/` | Sphinx API docs (autodoc + napoleon); build with `sphinx-build -W -b html docs docs/_build/html` |

## Test Suite

Active tests live in `tests/test_phase_*.py`. `tests/legacy_tests/` contains pre-refactor scripts that are **not run by pytest** (not on the pytest path) and serve as the source for new test files being ported into the active suite.

Structure of `tests/legacy_tests/`:
- `test_model.py` / `test_model2.py` — `Model` and `Network` method tests
- `test_compare.py` — `ModelComparison` tests
- `common/` — unit tests for `common/` utilities (`test_dataframe_util.py`, `test_dirs.py`, `test_file_util.py`, `test_json_util.py`, `test_pyqt5.py`)
- `dataformat/test_classes.py` — `dataformat/classes.py` tests
- `rawx/test_model-1.py` — additional RAWX-focused model tests
- `example_model.py` / `example_compare.py` — runnable usage examples (not tests)

When porting a legacy test, place the new file in `tests/` (e.g., `tests/test_model.py`) and fix:
1. Data paths: use `DATA_DIR = Path(__file__).resolve().parent / "data"` (same pattern as `test_phase_1_4.py`)
2. Area numbers: `sample_v35.rawx` uses areas 1–5; `Model_1.raw` uses areas 1–5 for the small test fixtures
3. The `model_dfs()` assertion for exact section names — the exact set depends on which sections are present in the RAWX template; use a subset check for robustness

## Important Constraints

- `RESILIENT = True` in `constants.py` — most parsing errors log warnings and continue rather than raising. Be aware when debugging silent failures.
- `inch.py` and `util/contingency_util.py` are WIP scaffolding — excluded from coverage and not yet functional.
- The RAWX export (`.rawx` output) has a known format bug that prevents reloading in PSS/E. This is tracked but low priority (Phase 2.2).
- v33 RAW support is inferred but not explicitly tested. v34 and v35 are primary targets.
- `Harmonics` and `TimeSeries` sections are populated only from RAWX sources; they will be empty for RAW-sourced models.
- Test fixtures live in `tests/data/`. `Model_1.raw` and `Model_2.raw` are the primary integration fixtures for `ModelComparison` tests; their documented differences are in `tests/data/Model_1 and 2 differences.txt`.

## Versioning

CalVer: `YYYY.M.micro` (e.g., `2026.4.5`; pre-releases use PEP 440 suffixes like `2026.4.5b1`). Managed by Hatch via `__about__.py`. To bump, edit `__about__.py` directly — Hatch reads the pattern `__version__ = "..."`.
