# ARCHITECTURE.md — psse_model_util

> Architecture reference for `psse_model_util` v2026.4.x

---

## Toolchain

| Tool | Role | Notes |
|------|------|-------|
| **PDM** | Dependency management & virtual environment | Primary tool for `install`, `run`, and `lock` |
| **Hatch** | Build backend & packaging | Invoked via `pdm run hatch build`; config in `pyproject.toml` |
| **Ruff** | Linter & import sorter | Replaces `flake8`; configured in `pyproject.toml` under `[tool.ruff.lint]` |
| **pytest + pytest-cov** | Test runner & coverage | Run via `pdm run pytest --cov=psse_model_util` |

> **Local dev setup:** `pip install pdm && pdm install -G lint`  
> **Run linter:** `pdm run ruff check .`  
> **Run tests:** `pdm run pytest --cov=psse_model_util`  
> **Build package:** `pdm run hatch build`

---

## CI/CD Workflows

Defined in `.github/workflows/`:

| File | Trigger | Jobs |
|------|---------|------|
| `lint.yml` | push/PR to `main` | Lint (Ruff), Test (pytest + coverage ≥80%), Build (Hatch) |
| `cd.yml` | push/PR to `main` | Same gates as CI + deployment placeholder |

---

## High-Level Overview

`psse_model_util` is a Python library for loading, filtering, and comparing PSS/E power system models. It translates proprietary PSS/E file formats (RAW, RAWX) into pandas DataFrames and a NetworkX graph, exposing them through a clean object model.

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Entry Points                               │
│           Model("file.raw")          ModelComparison(m1, m2)       │
└──────────────────────┬──────────────────────────┬───────────────────┘
                       │                          │
          ┌────────────▼────────────┐  ┌──────────▼──────────────────┐
          │       model.py          │  │         compare.py           │
          │  Model                  │  │  ModelComparison             │
          │    ├─ General           │  │    ├─ compare_network_dfs()  │
          │    ├─ Network           │  │    ├─ compare_graph()        │
          │    │    ├─ bus (DF)     │  │    └─ to_csv()               │
          │    │    ├─ acline (DF)  │  └─────────────────────────────┘
          │    │    ├─ generator…   │
          │    │    └─ _graph (nx)  │
          │    ├─ Harmonics         │
          │    └─ TimeSeries        │
          └────────────┬────────────┘
                       │
          ┌────────────▼────────────────────────────────┐
          │              Import Pipeline                 │
          │                                             │
          │  .raw  ──► raw_to_rawx.py ──► rawx dict    │
          │                 ▲                           │
          │         rawx_raw_map.csv                    │
          │                                             │
          │  .rawx ──► json_util.py ──► rawx dict      │
          └────────────┬────────────────────────────────┘
                       │
          ┌────────────▼────────────────────────────────┐
          │          dataformat/                         │
          │  rawx_json_template.py  (section schema)    │
          │  rawx_raw_map.csv       (field mapping)     │
          └─────────────────────────────────────────────┘
```

---

## Module Map

### Root modules

| Module | Purpose |
|--------|---------|
| `model.py` | Core object model. `Model` is the primary user-facing class. |
| `raw_to_rawx.py` | Parses PSS/E RAW files into a RAWX-compatible Python dict. |
| `compare.py` | `ModelComparison` — compares two `Model` instances at the DataFrame and graph level. |
| `inch.py` | WIP: IDEV/INCH export scaffolding (Phase 3.2, not functional). |
| `__about__.py` | Single source of truth for version (`__version__ = "2026.4.3"`). |
| `version.py` | Legacy shim — **deprecated**, kept for compatibility only. |

### `common/`

| Module | Purpose |
|--------|---------|
| `constants.py` | `INCLUDE_AREAS`, `DEFAULT_KV_FILTER`, `NETWORK_DF_COMPARISON_QUERIES`, `ALT_PATH_MAX_PATH_LENGTH` |
| `dataframe_util.py` | `convert_df_column_dtypes()` — safe dtype coercion for DataFrames |
| `dirs.py` | Canonical app directories via `platformdirs` (site-level and user-level) |
| `file_util.py` | `to_pickle()`, `read_pickle()`, `wait_for_file()` |
| `json_util.py` | `load_and_clean_json()` — loads and sanitizes RAWX JSON |
| `logging_config.py` | Logger setup (`setup_logger()`, `get_log_file_path()`) |

### `dataformat/`

| File | Purpose |
|------|---------|
| `rawx_raw_map.csv` | Field-level mapping: RAW column names ↔ RAWX field names, per PSS/E version (v34, v35) |
| `rawx_json_template.py` | RAWX section schema: `fields`, `data_type`, `id_cols`, `bus_cols` per network subsection |
| `classes.py` | Supporting data classes |
| `inch_templates.py` | INCH format field templates (WIP) |

---

## Class Hierarchy

```
Model
├── general:    General         # Model metadata (version, base MVA, etc.)
├── network:    Network         # All power system component DataFrames + graph
│   ├── bus:         pd.DataFrame   (indexed by ibus)
│   ├── acline:      pd.DataFrame   (indexed by ibus, jbus, ckt)
│   ├── transformer: pd.DataFrame   (indexed by ibus, jbus, kbus, ckt)
│   ├── generator:   pd.DataFrame
│   ├── load:        pd.DataFrame
│   ├── fixshunt:    pd.DataFrame
│   ├── swshunt:     pd.DataFrame
│   ├── area:        pd.DataFrame
│   ├── zone:        pd.DataFrame
│   ├── owner:       pd.DataFrame
│   ├── twotermdc:   pd.DataFrame
│   ├── vscdc:       pd.DataFrame
│   ├── facts:       pd.DataFrame
│   ├── rating:      pd.DataFrame
│   ├── caseid:      pd.DataFrame
│   └── _graph:      nx.Graph
├── harmonics:  Harmonics       # RAWX-only; empty for RAW-sourced models
└── timeseries: TimeSeries      # RAWX-only; empty for RAW-sourced models
```

`Network` and `Harmonics`/`TimeSeries` extend `AbstractSection`, which provides the generic `_create_dataframe()` logic. `Network` overrides `_create_dataframe()` to add metadata-driven dtype coercion and index setting from `rawx_json_template`.

---

## Import Pipeline

### RAW file path

```
RAW file (.raw)
    │
    ▼
raw_to_rawx.raw_file_to_rawx_dict()
    │  1. Read file (latin-1 encoding)
    │  2. Detect PSS/E version from line 2
    │  3. Load rawx_raw_map.csv filtered to that version
    │  4. Parse line-by-line:
    │       - Case identification (lines 1–2) → result['network']['caseid']
    │       - System-wide data (GENERAL/GAUSS/NEWTON/…) → result['network'][section]
    │       - Network sections (BUS DATA, BRANCH DATA, …):
    │           * section_divider lines → update current section name
    │           * column_names lines   → map RAW columns → RAWX field names
    │           * data lines           → parse CSV, pad to column count
    │           * multi-row records    → TRANSFORMER, TWO-TERMINAL DC, etc.
    │           * substation section   → special nested parser
    │
    ▼
rawx-compatible dict  {  'general': {...},  'network': { 'bus': {'fields': [...], 'data': [...]}, ... }  }
    │
    ▼
Model.__init__() → Network.__init__() → _create_dataframe() per subsection
    │  1. Pull fields + data from dict
    │  2. Look up metadata in rawx_json_template (data_type, id_cols, bus_cols)
    │  3. Pad short rows
    │  4. Build pd.DataFrame
    │  5. Coerce dtypes via convert_df_column_dtypes()
    │  6. Set index from id_cols
    │  7. Store df on Network and register its SectionSchema in Network._section_schemas[section]
    │
    ▼
Model.network.<subsection>  — typed, indexed pd.DataFrame
```

### RAWX file path

```
RAWX file (.rawx)
    │
    ▼
common.json_util.load_and_clean_json()
    │
    ▼
rawx dict  (same structure as above)
    │
    ▼
Model.__init__() → Network.__init__() → _create_dataframe()  [same as above]
```

### Pickle cache path

```
Model.__init__()
    │  checks site_cache_dir / "<stem>.model"
    │  if exists and not force_recalculate → load_pickle()  (fast path)
    │  else → parse + to_pickle()  (write cache for next time)
```

---

## Section-Schema Registry (`Network._section_schemas`)

Schema metadata is stored in a per-`Network` registry, not on individual DataFrames. `Network._create_dataframe()` builds a `SectionSchema` from `dataformat/rawx_json_template.py` for each section and stores it in `self._section_schemas: dict[str, SectionSchema]` keyed by section name.

`SectionSchema` (`dataformat/section_schema.py`) is a frozen dataclass:

| Field | Type | Description |
|-------|------|-------------|
| `data_type` | `Mapping[str, type]` | Per-column dtype hints |
| `id_cols` | `tuple` | Columns used as the DataFrame index (unique equipment identifier) |
| `bus_cols` | `tuple` | Column names that contain bus numbers (used by `filter_by_area`, `graph()`) |

Access via `network.section_schema(name)`, `network.bus_cols(name)`, or `network.id_cols(name)`. Because the registry lives on `Network`, it survives all pandas operations (merge/concat/filter/copy) and pickle round-trips. New sections must have an entry in `dataformat/rawx_json_template.py`.

---

## NetworkX Graph Structure

`Network.graph()` builds a `nx.Graph` from the loaded DataFrames:

| Element type | Node/Edge | Node ID format |
|---|---|---|
| Bus | Node | `("bus", ibus)` |
| Generator, load, fixshunt, swshunt | Node | `("generator", ibus, id)` |
| AC line, transformer (2-winding) | Edge | between `("bus", ibus)` and `("bus", jbus)` |
| Transformer (3-winding) | Central node + 3 edges | `("transformer", i, j, k)` → each bus |

Node and edge attributes carry all DataFrame row fields.

Regeneration is lazy by default (`regenerate=False`). Call `graph(regenerate=True)` explicitly or set `generate_graph=True` in `Network.__init__()`.

---

## Model Comparison Flow

```
ModelComparison(model1, model2)
    │
    ├─ compare_network_dfs()
    │    For each network section:
    │      outer-join df1 + df2 on index
    │      add _delta columns (numeric diff or bool change)
    │      add 'presence' column: both | model1_only | model2_only
    │      detect bus_num_changes (same name/area/baskv, different ibus)
    │
    └─ compare_graph()
         removed_edges = edges in graph1 not in graph2
         added_edges   = edges in graph2 not in graph1
         path_sectionalizations: for each removed edge, find alt paths in graph2
         path_bypasses:          for each added edge, find alt paths in graph1
```

Results exportable via `to_csv()` → `site_data_dir/<stem>/`.

---

## Directory Layout (Runtime)

All runtime paths are managed by `common/dirs.py` using `platformdirs`:

| Path constant | Purpose |
|---------------|---------|
| `site_cache_dir` | Pickle cache (`.model`, `.modcomp` files) |
| `site_data_dir` | CSV export output |
| `site_temp_dir` | Temp JSON output from RAW conversion |
| `site_log_dir` | Log files |

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| RAW files converted to RAWX-compatible dict before parsing | Single downstream code path; RAWX is the canonical internal format |
| `rawx_raw_map.csv` drives all RAW→RAWX field mapping | Keeps field mappings data-driven and version-aware (v34 vs v35 columns side-by-side) |
| Section-schema registry on `Network._section_schemas` | Schema survives all pandas ops (merge/concat/copy) and pickle round-trips; looked up via `network.section_schema(name)` — drives `filter_by_area()` and `graph()` |
| Pickle cache keyed by raw file stem | Parsing large BES models (tens of thousands of buses) is slow; cache makes repeated loads fast |
| `filter_by_area()` filters all DFs via `bus_cols` metadata | Single filter method covers all equipment types without hard-coding section names |
| NetworkX graph built lazily | Graph construction is expensive; only done when needed |
| Plotly/Dash visualization is in-scope but slated for replacement | Current `draw_one_line()` is functional but will be replaced with a React + FastAPI web UI (Phase 3.1) |

---

## Known Limitations

| Limitation | Notes |
|------------|-------|
| RAWX export bug | Exported `.rawx` doesn't reload in PSS/E — small format diff. Tracked for Phase 2.1. |
| CSV export drops index columns | `index=False` in `to_csv()` loses bus numbers. Fix in Phase 1.5. |
| `v33` support | Inferred but not explicitly tested. v34/v35 are primary targets. |
| No large-scale BES test data | Anonymized large-scale BES model needed for scale UAT (Phase 2.3). Synthetic test fixtures in `tests/data/` cover unit and integration tests. |
| Substation section parsing | Present but complex; substations excluded from NetworkX graph. |
