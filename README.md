# psse_model_util

Python library for reading, editing, validating, and comparing PSS/E power system models (RAW v33/34/35 and RAWX formats).

> **Status:** Active development — proprietary, internal use only.

---

## Overview

`psse_model_util` parses PSS/E RAW and RAWX files into structured Python objects backed by pandas DataFrames and a NetworkX graph. Its primary use case is comparing IDC summer vs. winter Bulk Electric System (BES) models.

**Key capabilities:**

- Load RAW (v33/34/35) or RAWX (JSON) files into a `Model` object
- Filter networks by area, voltage level, or arbitrary query
- Compare two models: DataFrame-level deltas + graph topology diffs (added/removed edges, path sectionalizations, bypasses)
- Export to CSV or pickle for downstream analysis
- Build a NetworkX graph for topological analysis (shortest paths, connectivity, etc.)

---

## Installation

### Prerequisites

- Python 3.11 (3.12–3.13 supported; 3.14.1 excluded)
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
# Filter by area
filtered = model.filter_by_area(areas=[101, 102, 103])

# Filter by voltage level (kV)
ehv = model.filter_by_kv(low_value=345)

# Filter a specific section by query
model.filter_section("bus", "baskv >= 230", inplace=True)
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

### Export a model

```python
# Export all network sections to CSV
model.to_csv()

# Cache as pickle (fast reload)
model.to_pickle()

# Reload from cache
model2 = Model("path/to/model.raw")  # auto-loads from cache if available
```

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
    └── test_placeholder.py    # Placeholder — test suite (Phase 1.4)
```

---

## Dev Setup

```bash
# Lint
pdm run ruff check .

# Test
pdm run pytest

# Test with coverage
pdm run pytest --cov=psse_model_util

# Version (hatch-managed calver)
hatch version
```

---

## Versioning

Uses calver: `YYYY.M.micro` — managed by Hatch via `__about__.py`.

```
2026.4.3  →  year=2026, month=4, micro=3
```

---

## Known Issues / Roadmap

| Issue | Phase |
|-------|-------|
| RAWX export bug — exported `.rawx` doesn't load in PSS/E | 2.1 |
| CSV export missing columns (index dropped with `index=False`) | 1.5 |
| INCH/IDEV export scaffolded but not functional | 3.2 |
| No real test data (anonymized BES model needed for UAT) | 2.3 |

---

## License

Proprietary — internal use only.
