# psse_model_util

Python library for reading, editing, validating, and comparing PSS/E power system models (RAW v33/34/35 and RAWX formats).

> **Status:** Active development — proprietary, internal use only.

---

## Overview

`psse_model_util` parses PSS/E RAW and RAWX files into structured Python objects backed by pandas DataFrames and a NetworkX graph. Its primary use case is comparing seasonal Bulk Electric System (BES) model variants (e.g. summer vs. winter).

**Key capabilities:**

- Load RAW (v33/34/35) or RAWX (JSON) files into a `Model` object
- Filter networks by area, voltage level, or arbitrary query
- Compare two models: DataFrame-level deltas + graph topology diffs (added/removed edges, path sectionalizations, bypasses)
- Export to CSV or pickle for downstream analysis
- Build a NetworkX graph for topological analysis (shortest paths, connectivity, etc.)

---

## Installation

### Prerequisites

- Python 3.11+ (tested through 3.14.4)
- [PDM](https://pdm-project.org/) for dependency management
- [Hatch](https://hatch.pypa.io/) for builds and versioning

### Install (editable / dev)

```bash
# Clone or copy the project directory
cd psse_model_util

# Install with PDM
pdm install

# Or install directly with pip (editable)
pip install -e .
```

### Install dev extras

```bash
pdm install -G dev
# Includes: pytest, pytest-cov, ruff
```

---

## Quick Start

### Load a model

```python
from psse_model_util.model import Model

# From a RAW file (v33/34/35)
model = Model("path/to/model.raw", name="Summer_Peak")

# From a RAWX file
model = Model("path/to/model.rawx", name="Summer_Peak")

# Access network data
buses      = model.network.bus          # pd.DataFrame
lines      = model.network.acline       # pd.DataFrame
generators = model.network.generator    # pd.DataFrame
```

### Filter a model

```python
# Filter by area (Model-level — delegates to network)
filtered = model.filter_by_area(areas={101: "AREA1", 102: "AREA2"})

# Filter by voltage level or section query (Network-level)
ehv = model.network.filter_by_kv(low_value=345)
model.network.filter_section("bus", "baskv >= 230", inplace=True)
```

### Build and query the network graph

```python
import networkx as nx

graph = model.network.graph(regenerate=True)

# Shortest path between two buses
path = nx.shortest_path(graph, ("bus", 101), ("bus", 205))

# Access bus properties
props = graph.nodes[("bus", 101)]
```

### Compare two models

```python
from psse_model_util.model import Model
from psse_model_util.compare import ModelComparison

model1 = Model("summer.raw", name="Summer")
model2 = Model("winter.raw", name="Winter")

# Filter to your area of interest first (recommended)
m1 = model1.filter_by_area(areas=[101, 102, 103])
m2 = model2.filter_by_area(areas=[101, 102, 103])

comp = ModelComparison(m1, m2)
comp.compare_network_dfs()   # DataFrame-level column deltas
comp.compare_graph()          # Topology: added/removed edges, path changes
comp.to_csv(df_comparison_to_csv=True, graph_comparison_to_csv=True)
```

### Export and serialise a model

```python
# Export all network sections to CSV
model.to_csv()

# Cache as pickle (fast reload)
model.to_pickle()

# Reload from cache
model2 = Model("path/to/model.raw")  # auto-loads from cache if available

# Serialise to a JSON string or file
json_str = model.to_json()
model.to_json(file_path="model_export.json")

# Load from a rawx dict (avoids the json_data mutation issue in to_json round-trips)
from psse_model_util.raw_to_rawx import raw_file_to_rawx_dict
rawx_dict = raw_file_to_rawx_dict("path/to/model.raw")
model2 = Model(file_path_or_json=rawx_dict)
```

> **Note:** `Model(file_path_or_json=json_str)` works for loading but a full
> `to_json()` → `Model(json_str)` round-trip is lossy due to a known internal
> mutation (see Known Issues). Use `raw_file_to_rawx_dict` as shown above
> when you need a lossless in-memory copy.

---

## Project Structure

```
psse_model_util/
├── model.py                   # Model, Network, General, Harmonics, TimeSeries classes
├── raw_to_rawx.py             # RAW file parser → rawx-compatible dict
├── compare.py                 # ModelComparison class
├── version.py                 # Legacy version shim (deprecated — use __about__.py)
├── inch.py                    # WIP: IDEV/INCH export (Phase 3.2)
├── __about__.py               # Version: 2026.4.3 (calver YYYY.M.micro)
├── __init__.py
├── CLAUDE.md                  # Architecture guide for Claude Code
├── common/
│   ├── constants.py           # INCLUDE_AREAS, filter constants, query defaults
│   ├── dataframe_util.py      # convert_df_column_dtypes()
│   ├── dirs.py                # Canonical app dirs (platformdirs)
│   ├── file_util.py           # to_pickle(), read_pickle(), wait_for_file()
│   ├── json_util.py           # load_and_clean_json()
│   └── logging_config.py      # Logger setup
├── dataformat/
│   ├── classes.py             # Data model classes
│   ├── inch_templates.py      # INCH format templates
│   ├── rawx_json_template.py  # RAWX section schema (fields, data_types, id_cols, bus_cols)
│   └── rawx_raw_map.csv       # RAW ↔ RAWX field mapping (v34 + v35 columns)
└── tests/
    ├── conftest.py            # Shared fixtures and sys.path setup
    ├── test_classes.py        # dataformat/classes.py domain types
    ├── test_compare.py        # ModelComparison
    ├── test_dataframe_util.py # common/dataframe_util helpers
    ├── test_dirs.py           # common/dirs platform paths
    ├── test_file_util.py      # common/file_util pickle helpers
    ├── test_model.py          # Model + Network (primary integration tests)
    ├── test_model2.py         # Supplemental Model method tests
    ├── test_raw_to_rawx.py    # RAW parser + substation section
    ├── test_rawx.py           # RAWX-format model loading
    ├── test_phase_*.py        # Feature-phase regression tests
    ├── legacy_tests/          # Pre-refactor scripts (not collected by pytest)
    └── data/                  # Test fixtures (do not delete)
        ├── Model_1.raw        # Synthetic v34 — baseline for ModelComparison tests
        ├── Model_2.raw        # Synthetic v34 — intentionally modified from Model_1
        ├── sample_34.raw      # Minimal v34 RAW file
        ├── sample2_34.raw     # Second minimal v34 RAW file
        ├── sample_v35.raw     # Minimal v35 RAW file
        ├── sample_v35.rawx    # Minimal v35 RAWX file
        ├── sample2_v35.rawx   # Second minimal v35 RAWX file
        ├── transformer.raw    # Transformer-focused test case
        ├── minimal.raw        # Smallest valid RAW file
        └── Model_1 and 2 differences.txt  # Documented delta between Model_1/Model_2
```

---

## Dev Setup

```bash
# Lint
pdm run ruff check .

# Run all tests
pdm run pytest

# Run a single test file
pdm run pytest tests/test_model.py

# Run a specific test by name
pdm run pytest tests/test_model.py -k "test_filter_by_area"

# Test with coverage report
pdm run pytest --cov=psse_model_util --cov-report=term-missing
# Current: 343 tests, 75% coverage (CI gate: 40%)

# Version (hatch-managed calver)
hatch version
```

> **Claude Code users:** `CLAUDE.md` at the repo root contains architecture
> notes, data-flow diagrams, and the rationale behind key design decisions.

---

## Versioning

Uses calver: `YYYY.M.micro` — managed by Hatch via `__about__.py`.

```
2026.4.3  →  year=2026, month=4, micro=3
```

---

## Known Issues / Roadmap

| Issue | Phase | Status |
|-------|-------|--------|
| RAWX export bug — exported `.rawx` doesn't reload in PSS/E | 2.2 | Open (low priority) |
| `to_json()` → `Model(json_str)` round-trip is lossy (`json_data` mutation in `_create_dataframe`) | — | Open |
| INCH/IDEV export scaffolded but not functional | 3.2 | Open |

---

## License

Proprietary — internal use only.
