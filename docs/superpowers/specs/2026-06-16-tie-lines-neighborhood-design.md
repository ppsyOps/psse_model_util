# Design: Tie-Line Identification and Bus Neighborhood Queries

**Date:** 2026-06-16
**Status:** Approved, pending implementation

---

## Overview

Adds four methods to `Network` in `model.py` for identifying tie lines and finding the electrical neighborhood around any set of buses. Primary use case: IDC BES summer/winter comparisons where users need to identify area boundary equipment and reason about what's electrically close to those boundaries.

All methods live on `Network` only. No `Model`-level delegation wrappers are added — this is the correct pattern going forward. See the deprecation roadmap item for the existing wrappers.

---

## Scope

**In scope:**
- `Network.find_tie_lines()` — identify AC lines crossing area boundaries
- `Network._buses_within_n_hops()` — private traversal engine (N bus-to-bus hops)
- `Network.neighborhood()` — N-hop neighborhood of any seed buses, including connected equipment
- `Network.tie_line_neighborhood()` — convenience wrapper combining the above with optional area scoping

**Out of scope:**
- Transformer tie lines (only `acline` section for now)
- Inplace modification (all methods are pure-query, returning new objects)
- Changes to `Model`, `ModelComparison`, or any other class

---

## Architecture

Four additions to `Network` in `model.py`:

| Method | Visibility | Returns |
|---|---|---|
| `find_tie_lines(native_areas, kv_min, kv_max)` | public | `pd.DataFrame` |
| `_buses_within_n_hops(seed_buses, n)` | private | `set[int]` |
| `neighborhood(seed_buses, n, output)` | public | `Network` / `dict` / `DataFrame` |
| `tie_line_neighborhood(n, native_areas, side, kv_min, kv_max, output)` | public | same as above |

`tie_line_neighborhood` is a convenience wrapper around the other three. Users call everything via `model.network.<method>()`.

---

## Method Designs

### `find_tie_lines(native_areas, kv_min, kv_max)`

Identifies all AC lines where exactly one terminal bus is in `native_areas`. Lines where both terminals are native (internal) and lines where neither terminal is native (external-to-external) are excluded.

```python
def find_tie_lines(
    self,
    native_areas: dict | list | set | None = None,
    kv_min: float | None = None,
    kv_max: float | None = None,
) -> pd.DataFrame:
```

**`native_areas`:** Defaults to `INCLUDE_AREAS` from `common/constants.py`. Accepts the same `dict | list | set` input types as `filter_by_area` (area numbers with optional name labels).

**Filter logic:** `(ibus_area IN native_areas) XOR (jbus_area IN native_areas)`. For example, with `native_areas = {A, B, C}`:
- A→D: kept (tie line — one native, one external)
- A→B: excluded (both native — internal line)
- D→E: excluded (neither native)

**kV filter:** Applied to both terminal buses. A line is kept only if both `ibus_baskv` and `jbus_baskv` fall within `[kv_min, kv_max]`. Bounds that are `None` are ignored. For AC lines both terminals are almost always the same voltage class, so this is the practical behavior.

**Implementation:** Calls `section_with_bus('acline')` to get the enriched line DataFrame (all `acline` columns plus `ibus_area`, `ibus_baskv`, `ibus_name`, `jbus_area`, `jbus_baskv`, `jbus_name`), then applies the XOR area filter and optional kV filter.

**Returns:** Enriched `acline` DataFrame with bus metadata columns appended.

---

### `_buses_within_n_hops(seed_buses, n)`

Private traversal engine. Returns all bus numbers reachable within N bus-to-bus hops, including the seed buses themselves (0 hops).

```python
def _buses_within_n_hops(
    self,
    seed_buses: set | list,   # ibus integers
    n: int,
) -> set[int]:
```

**Hop counting:** One hop = moving from one bus to an adjacent bus through any connecting equipment:
- AC line or 2-winding transformer: direct graph edge between two bus nodes = 1 hop
- 3-winding transformer: `bus_A → ("transformer", i, j, k) → bus_B` = 1 hop (synthetic node is a pass-through, not counted as a bus)

**Algorithm:** Expands outward one bus-hop at a time. At each step, for each bus in the current frontier, examines all graph neighbors. Bus neighbors are direct 1-hop destinations. Transformer synthetic node neighbors are looked through one more step to find the buses on the other sides (still 1 hop total).

**Edge cases:**
- `n=0` returns `set(seed_buses)` (no traversal)
- Seed buses absent from the graph are silently skipped (consistent with `RESILIENT = True`)
- Disconnected buses stop traversal naturally at the island boundary

---

### `neighborhood(seed_buses, n, output)`

Returns all buses within N bus-hops of any seed bus, plus all equipment (generators, loads, shunts, etc.) directly connected to those buses.

```python
def neighborhood(
    self,
    seed_buses: int | set | list,
    n: int,
    output: str = 'network',   # 'network' | 'dict' | 'dataframe'
) -> Network | dict[str, pd.DataFrame] | pd.DataFrame:
```

**`seed_buses`:** Accepts a single `int` (converted to a one-element set internally), or any list/set of ibus integers.

**Equipment inclusion:** After `_buses_within_n_hops` returns the bus set, every network section is filtered to rows where any `bus_col` is in that set. This naturally includes all generators, loads, shunts, and other equipment connected to neighborhood buses without special-casing any section.

**Output formats:**
- `'network'` (default): `self.copy()` with each section DataFrame replaced by its filtered version. Same object type — users continue to use `result.bus`, `result.generator`, etc.
- `'dict'`: `dict[str, pd.DataFrame]` keyed by section name, same shape as `network_dfs()`. Useful for inspection or iteration.
- `'dataframe'`: all sections concatenated into one flat DataFrame with a `section` column prepended. Columns absent from a given section are `NaN`. Intended for Excel/CSV export; not recommended for programmatic use.

**Usage:**
```python
# All buses and equipment within 2 hops of bus 1501 (single int accepted)
nbhd = model.network.neighborhood(1501, n=2)
nbhd.generator   # generators in the neighborhood

# For Excel export
df = model.network.neighborhood(1501, n=2, output='dataframe')
df.to_excel("neighborhood.xlsx", index=False)
```

---

### `tie_line_neighborhood(n, native_areas, side, kv_min, kv_max, output)`

Convenience wrapper. Finds all tie lines, seeds the neighborhood from their terminal buses, and optionally filters the result to one side of the area boundary.

```python
def tie_line_neighborhood(
    self,
    n: int,
    native_areas: dict | list | set | None = None,
    side: str = 'both',        # 'internal' | 'external' | 'both'
    kv_min: float | None = None,
    kv_max: float | None = None,
    output: str = 'network',   # 'network' | 'dict' | 'dataframe'
) -> Network | dict[str, pd.DataFrame] | pd.DataFrame:
```

**Steps:**
1. Calls `find_tie_lines(native_areas, kv_min, kv_max)` to get tie-line DataFrame. If the result is empty (no tie lines match), returns an empty `Network`/`dict`/`DataFrame` immediately without traversal.
2. Extracts all terminal bus numbers (both `ibus` and `jbus` from the result) as the seed set
3. Calls `neighborhood(seed_buses, n)` → full N-hop neighborhood across both sides of the boundary
4. Applies area filter based on `side`:
   - `'internal'`: keep only buses whose `area` is in `native_areas`
   - `'external'`: keep only buses whose `area` is **not** in `native_areas`
   - `'both'`: no area filter (default)
5. Converts to the requested `output` format

**Usage:**
```python
# All generators within 2 buses of any tie line, on the native side
nbhd = model.network.tie_line_neighborhood(n=2, side='internal')
nbhd.generator

# Neighbor-area buses within 1 hop of any EHV tie line, for Excel review
df = model.network.tie_line_neighborhood(
    n=1, side='external', kv_min=345, output='dataframe'
)
df.to_excel("external_tie_neighborhood.xlsx", index=False)
```

---

## Deprecation Roadmap (tracked separately)

The existing pattern of surfacing `Network` methods on `Model` (e.g., `Model.filter_by_area`, `Model.filter_by_kv`, `Model.filter_section`) is identified as a design mistake. These will be deprecated in a future release:

1. Add `DeprecationWarning` to each `Model`-level wrapper pointing users to `model.network.<method>()`
2. Remove the wrappers in a subsequent release

This work is tracked as a roadmap item and is not part of this implementation.

---

## Testing

- `test_find_tie_lines`: fixture with known tie lines; assert XOR area logic; assert kV filter; assert enriched columns present
- `test_buses_within_n_hops_zero`: `n=0` returns exactly the seed set
- `test_buses_within_n_hops_n1`: known graph; assert correct 1-hop neighbors
- `test_buses_within_n_hops_transformer`: 3-winding transformer traversal counts as 1 hop
- `test_neighborhood_single_int`: passing a bare `int` seed is accepted
- `test_neighborhood_output_dict`: dict keys match `network_dfs()` keys
- `test_neighborhood_output_dataframe`: `section` column present; all sections represented
- `test_tie_line_neighborhood_internal`: result buses are all in `native_areas`
- `test_tie_line_neighborhood_external`: result buses have no area in `native_areas`
- `test_tie_line_neighborhood_both`: superset of internal + external results
