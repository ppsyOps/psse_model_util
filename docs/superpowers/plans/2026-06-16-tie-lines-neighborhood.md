# Tie-Line Identification and Bus Neighborhood Queries — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add four methods to `Network` in `model.py` for identifying tie lines and finding the electrical neighborhood around any set of buses.

**Architecture:** All four methods live on `Network` only — no `Model`-level wrappers. `_buses_within_n_hops` is a private traversal engine used by `neighborhood`, which is used by `tie_line_neighborhood`. `find_tie_lines` is independent and feeds `tie_line_neighborhood` as a convenience wrapper.

**Tech Stack:** pandas, NetworkX (already imported in `model.py`), pytest, Model_1.raw test fixture.

---

## File Map

| File | Action | What changes |
|---|---|---|
| `model.py` | Modify | Add 4 methods to `Network` class after `graph()` (~line 1224) |
| `tests/test_network_queries.py` | Create | All tests for the 4 new methods |

### Key facts about the test fixture (`tests/data/Model_1.raw`)

- Areas: 1, 2, 3, 4, 5, 6 (none overlap with the default `INCLUDE_AREAS`, so always pass explicit `native_areas`)
- `NATIVE_AREAS = {1: "CENTRAL", 2: "EAST", 3: "CENTRAL_DC"}` for tests
- `find_tie_lines(native_areas={1,2,3})` → 4 lines: 152→3004, 154→3008, 213→2000, 2000→214
- `find_tie_lines(native_areas={1,2,3}, kv_min=345)` → 1 line: 152→3004 (500 kV both ends)
- `_buses_within_n_hops({152}, n=0)` → `{152}`
- `_buses_within_n_hops({152}, n=1)` → `{152, 151, 202, 3004, 153, 3021, 3022}` (3 direct bus edges + 3 buses through transformer synthetic nodes)
- Bus 101 has no direct bus edges — connects only through a transformer synthetic node to bus 151

### Known graph limitation

3-winding transformers create two separate synthetic nodes in the current graph (known bug): `('transformer', i, j, k)` connected to buses i and j, and `('transformer', i, j)` connected to bus k only. These are not connected to each other. Model_1.raw does not have 3-winding transformers so this limitation does not affect the test suite.

---

## Task 1: `Network.find_tie_lines()`

**Files:**
- Modify: `model.py` (add method after `graph()` ~line 1224)
- Create: `tests/test_network_queries.py`

- [ ] **Step 1: Create the test file with a failing test**

Create `tests/test_network_queries.py`:

```python
"""
test_network_queries.py — Tests for Network.find_tie_lines, _buses_within_n_hops,
neighborhood, and tie_line_neighborhood.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from psse_model_util.model import Model, Network

DATA_DIR = Path(__file__).resolve().parent / "data"
MODEL1_RAW = DATA_DIR / "Model_1.raw"

# Model_1.raw uses areas 1-6. INCLUDE_AREAS uses different area numbers (200+).
# Always pass explicit native_areas in tests.
NATIVE_AREAS = {1: "CENTRAL", 2: "EAST", 3: "CENTRAL_DC"}


@pytest.fixture(scope="module")
def net():
    m = Model(file_path_or_json=MODEL1_RAW, force_recalculate=True)
    return m.network


# ---------------------------------------------------------------------------
# find_tie_lines
# ---------------------------------------------------------------------------

def test_find_tie_lines_returns_dataframe(net):
    result = net.find_tie_lines(native_areas=NATIVE_AREAS)
    assert isinstance(result, pd.DataFrame)


def test_find_tie_lines_xor_logic(net):
    result = net.find_tie_lines(native_areas=NATIVE_AREAS)
    # All 4 expected tie lines: 152→3004, 154→3008, 213→2000, 2000→214
    assert len(result) == 4
    native_set = set(NATIVE_AREAS.keys())
    ibus_native = result["ibus_area"].isin(native_set)
    jbus_native = result["jbus_area"].isin(native_set)
    # XOR: exactly one end must be in native areas
    assert (ibus_native ^ jbus_native).all()


def test_find_tie_lines_enriched_columns(net):
    result = net.find_tie_lines(native_areas=NATIVE_AREAS)
    for col in ("ibus_area", "jbus_area", "ibus_baskv", "jbus_baskv", "ibus_name", "jbus_name"):
        assert col in result.columns, f"Missing column: {col}"


def test_find_tie_lines_kv_filter(net):
    result = net.find_tie_lines(native_areas=NATIVE_AREAS, kv_min=345)
    # Only 152→3004 has both ends at 500 kV
    assert len(result) == 1
    assert result["ibus_baskv"].iloc[0] >= 345
    assert result["jbus_baskv"].iloc[0] >= 345


def test_find_tie_lines_no_internal_lines(net):
    # Lines 152→202, 154→203, 154→205 connect areas 1 and 2 — both native, should be excluded
    result = net.find_tie_lines(native_areas=NATIVE_AREAS)
    native_set = set(NATIVE_AREAS.keys())
    # No row should have BOTH ends in native areas
    both_native = result["ibus_area"].isin(native_set) & result["jbus_area"].isin(native_set)
    assert not both_native.any()


def test_find_tie_lines_empty_when_no_match(net):
    # area 99 doesn't exist in the model
    result = net.find_tie_lines(native_areas={99: "GHOST"})
    assert result.empty
```

- [ ] **Step 2: Run to verify tests fail**

```
pdm run pytest tests/test_network_queries.py -v
```

Expected: `AttributeError: 'Network' object has no attribute 'find_tie_lines'`

- [ ] **Step 3: Add `find_tie_lines` to `Network` in `model.py`**

Insert after the closing `return self._graph` of `graph()` at line 1224, before `def draw_one_line`:

```python
    def find_tie_lines(
        self,
        native_areas: dict | list | set | None = None,
        kv_min: float | None = None,
        kv_max: float | None = None,
    ) -> pd.DataFrame:
        """Return AC lines where exactly one terminal bus is in native_areas.

        Lines where both terminals are native (internal) and lines where neither
        terminal is native (external-to-external) are excluded.

        Args:
            native_areas: Areas considered "native". Defaults to INCLUDE_AREAS.
                Accepts dict {area_num: name}, list, or set of area numbers.
            kv_min: If set, both terminal buses must have baskv >= kv_min.
            kv_max: If set, both terminal buses must have baskv <= kv_max.

        Returns:
            Enriched acline DataFrame with ibus_area, ibus_baskv, ibus_name,
            jbus_area, jbus_baskv, jbus_name columns appended.
        """
        if native_areas is None:
            native_areas = INCLUDE_AREAS
        area_set = set(native_areas.keys()) if isinstance(native_areas, dict) else set(native_areas)

        df = self.section_with_bus('acline')

        ibus_native = df['ibus_area'].isin(area_set)
        jbus_native = df['jbus_area'].isin(area_set)
        df = df[ibus_native ^ jbus_native]

        if kv_min is not None:
            df = df[(df['ibus_baskv'] >= kv_min) & (df['jbus_baskv'] >= kv_min)]
        if kv_max is not None:
            df = df[(df['ibus_baskv'] <= kv_max) & (df['jbus_baskv'] <= kv_max)]

        return df
```

- [ ] **Step 4: Run tests and verify they pass**

```
pdm run pytest tests/test_network_queries.py -v -k "find_tie_lines"
```

Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add model.py tests/test_network_queries.py
git commit -m "feat(network): add Network.find_tie_lines() with XOR area filter and kV range"
```

---

## Task 2: `Network._buses_within_n_hops()`

**Files:**
- Modify: `model.py` (add method after `find_tie_lines`)
- Modify: `tests/test_network_queries.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_network_queries.py`:

```python
# ---------------------------------------------------------------------------
# _buses_within_n_hops
# ---------------------------------------------------------------------------

def test_buses_within_n_hops_zero(net):
    # n=0 returns exactly the seed set
    result = net._buses_within_n_hops({152}, 0)
    assert result == {152}


def test_buses_within_n_hops_one_direct(net):
    # Bus 152 has direct bus edges to 151, 202, 3004
    # and reaches 153, 3021, 3022 through transformer synthetic nodes
    result = net._buses_within_n_hops({152}, 1)
    assert result == {152, 151, 202, 3004, 153, 3021, 3022}


def test_buses_within_n_hops_includes_seed(net):
    result = net._buses_within_n_hops({152, 154}, 0)
    assert 152 in result
    assert 154 in result


def test_buses_within_n_hops_missing_bus_silently_skipped(net):
    # Bus 99999 does not exist — should not raise
    result = net._buses_within_n_hops({99999}, 1)
    assert isinstance(result, set)
    assert 99999 not in result


def test_buses_within_n_hops_two_hops_superset_of_one(net):
    one_hop = net._buses_within_n_hops({152}, 1)
    two_hop = net._buses_within_n_hops({152}, 2)
    assert one_hop.issubset(two_hop)
    assert len(two_hop) >= len(one_hop)


def test_buses_within_n_hops_through_transformer_synthetic_node(net):
    # Bus 101 has NO direct bus edges — only connects through a transformer
    # synthetic node ('transformer', 101, 151) to bus 151.
    # At n=1, bus 151 should be reachable from bus 101.
    result = net._buses_within_n_hops({101}, 1)
    assert 101 in result   # seed always included
    assert 151 in result   # reached through transformer pass-through
```

- [ ] **Step 2: Run to verify tests fail**

```
pdm run pytest tests/test_network_queries.py -v -k "buses_within_n_hops"
```

Expected: `AttributeError: 'Network' object has no attribute '_buses_within_n_hops'`

- [ ] **Step 3: Add `_buses_within_n_hops` to `Network` in `model.py`**

Insert after `find_tie_lines`:

```python
    def _buses_within_n_hops(
        self,
        seed_buses: set | list,
        n: int,
    ) -> set[int]:
        """Return bus numbers reachable within N bus-to-bus hops from seed_buses.

        One hop = traversal from one bus to an adjacent bus through any
        connecting equipment. AC lines and 2-winding transformers each count as
        one hop. The synthetic node of a 3-winding transformer is treated as a
        pass-through (not a hop). Seed buses are included in the result (0 hops
        from themselves). Seed buses absent from the graph are silently skipped.

        Args:
            seed_buses: Iterable of ibus integers to start from.
            n: Number of bus hops to traverse.

        Returns:
            Set of ibus integers within N bus hops of any seed bus.
        """
        if n == 0:
            return set(seed_buses)

        g = self.graph()
        frontier = {('bus', ibus) for ibus in seed_buses if ('bus', ibus) in g}
        visited = set(frontier)

        for _ in range(n):
            next_frontier: set = set()
            for node in frontier:
                for neighbor in g.neighbors(node):
                    if neighbor[0] == 'bus':
                        # Direct bus-to-bus edge (AC line)
                        if neighbor not in visited:
                            next_frontier.add(neighbor)
                    else:
                        # Pass-through node (transformer synthetic node, equipment)
                        # Look one level further for bus nodes
                        for far in g.neighbors(neighbor):
                            if far[0] == 'bus' and far not in visited:
                                next_frontier.add(far)
            visited |= next_frontier
            frontier = next_frontier
            if not frontier:
                break

        return {ibus for (_, ibus) in visited}
```

- [ ] **Step 4: Run tests and verify they pass**

```
pdm run pytest tests/test_network_queries.py -v -k "buses_within_n_hops"
```

Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add model.py tests/test_network_queries.py
git commit -m "feat(network): add Network._buses_within_n_hops() N-hop bus traversal engine"
```

---

## Task 3: `Network.neighborhood()`

**Files:**
- Modify: `model.py` (add method after `_buses_within_n_hops`)
- Modify: `tests/test_network_queries.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_network_queries.py`:

```python
# ---------------------------------------------------------------------------
# neighborhood
# ---------------------------------------------------------------------------

def test_neighborhood_returns_network_by_default(net):
    result = net.neighborhood(152, n=1)
    assert isinstance(result, Network)


def test_neighborhood_accepts_single_int(net):
    # Passing a bare int should be accepted (converted to {int} internally)
    result = net.neighborhood(152, n=1)
    assert isinstance(result, Network)
    assert 152 in result.bus.index


def test_neighborhood_bus_set_correct(net):
    result = net.neighborhood(152, n=1)
    expected = {152, 151, 202, 3004, 153, 3021, 3022}
    assert set(result.bus.index) == expected


def test_neighborhood_n0_returns_seed_only(net):
    result = net.neighborhood(152, n=0)
    assert set(result.bus.index) == {152}


def test_neighborhood_includes_connected_equipment(net):
    # Bus 152 has a load and fixshunt — they should appear in the neighborhood
    result = net.neighborhood(152, n=0)
    assert not result.load.empty or not result.fixshunt.empty


def test_neighborhood_output_dict(net):
    result = net.neighborhood(152, n=1, output='dict')
    assert isinstance(result, dict)
    assert 'bus' in result
    assert 'acline' in result
    assert isinstance(result['bus'], pd.DataFrame)
    assert set(result['bus'].index) == {152, 151, 202, 3004, 153, 3021, 3022}


def test_neighborhood_output_dataframe(net):
    result = net.neighborhood(152, n=1, output='dataframe')
    assert isinstance(result, pd.DataFrame)
    assert 'section' in result.columns
    assert 'bus' in result['section'].values


def test_neighborhood_invalid_output_raises(net):
    with pytest.raises(ValueError, match="output"):
        net.neighborhood(152, n=1, output='excel')


def test_neighborhood_does_not_mutate_original(net):
    original_bus_count = len(net.bus)
    net.neighborhood(152, n=1)
    assert len(net.bus) == original_bus_count
```

- [ ] **Step 2: Run to verify tests fail**

```
pdm run pytest tests/test_network_queries.py -v -k "neighborhood and not tie_line"
```

Expected: `AttributeError: 'Network' object has no attribute 'neighborhood'`

- [ ] **Step 3: Add `neighborhood` to `Network` in `model.py`**

Insert after `_buses_within_n_hops`:

```python
    def neighborhood(
        self,
        seed_buses: int | set | list,
        n: int,
        output: str = 'network',
    ) -> 'Network | dict[str, pd.DataFrame] | pd.DataFrame':
        """Return all buses within N bus-hops of seed_buses plus connected equipment.

        Calls _buses_within_n_hops to determine the bus set, then filters every
        network section to rows whose bus_cols intersect that set. The result
        includes all equipment (generators, loads, shunts, etc.) connected to
        the neighborhood buses.

        Args:
            seed_buses: Single ibus int or iterable of ibus integers.
            n: Number of bus hops to traverse.
            output: Return format.
                'network' (default) — filtered Network copy.
                'dict' — dict[str, DataFrame] keyed by section name.
                'dataframe' — flat DataFrame with 'section' column prepended;
                    intended for Excel/CSV export, not programmatic use.

        Returns:
            Filtered network data in the requested format.

        Raises:
            ValueError: If output is not 'network', 'dict', or 'dataframe'.
        """
        if output not in ('network', 'dict', 'dataframe'):
            raise ValueError(f"output must be 'network', 'dict', or 'dataframe'; got {output!r}")

        if isinstance(seed_buses, int):
            seed_buses = {seed_buses}

        bus_set = self._buses_within_n_hops(seed_buses, n)
        result = self.copy()

        for attr_name, df in result.__dict__.items():
            if not isinstance(df, pd.DataFrame):
                continue
            meta = df._metadata
            if 'bus_cols' not in meta:
                continue

            bus_cols = meta['bus_cols']
            index_bus_cols = [c for c in bus_cols if c in df.index.names]
            column_bus_cols = [c for c in bus_cols if c in df.columns]

            if index_bus_cols:
                mask = df.index.get_level_values(index_bus_cols[0]).isin(bus_set)
                for col in index_bus_cols[1:]:
                    mask |= df.index.get_level_values(col).isin(bus_set)
            elif column_bus_cols:
                mask = np.any(np.isin(df[column_bus_cols].values, list(bus_set)), axis=1)
            else:
                continue

            filtered = df[mask]
            filtered._metadata = meta
            setattr(result, attr_name, filtered)

        result._graph = nx.Graph()

        if output == 'network':
            return result
        elif output == 'dict':
            return result.model_dfs()
        else:  # 'dataframe'
            frames = []
            for section, df in result.model_dfs().items():
                df = df.reset_index()
                df.insert(0, 'section', section)
                frames.append(df)
            return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
```

- [ ] **Step 4: Run tests and verify they pass**

```
pdm run pytest tests/test_network_queries.py -v -k "neighborhood and not tie_line"
```

Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add model.py tests/test_network_queries.py
git commit -m "feat(network): add Network.neighborhood() N-hop bus neighborhood query"
```

---

## Task 4: `Network.tie_line_neighborhood()`

**Files:**
- Modify: `model.py` (add method after `neighborhood`)
- Modify: `tests/test_network_queries.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_network_queries.py`:

```python
# ---------------------------------------------------------------------------
# tie_line_neighborhood
# ---------------------------------------------------------------------------

def test_tie_line_neighborhood_returns_network(net):
    result = net.tie_line_neighborhood(n=1, native_areas=NATIVE_AREAS)
    assert isinstance(result, Network)


def test_tie_line_neighborhood_both_has_internal_and_external(net):
    result = net.tie_line_neighborhood(n=0, native_areas=NATIVE_AREAS, side='both')
    areas_in_result = set(result.bus['area'].unique())
    native_set = set(NATIVE_AREAS.keys())
    # n=0: only tie-line terminal buses. Some are native, some external.
    assert areas_in_result & native_set        # at least one native area present
    assert areas_in_result - native_set        # at least one external area present


def test_tie_line_neighborhood_internal_only_native_areas(net):
    result = net.tie_line_neighborhood(n=1, native_areas=NATIVE_AREAS, side='internal')
    native_set = set(NATIVE_AREAS.keys())
    assert result.bus['area'].isin(native_set).all()


def test_tie_line_neighborhood_external_no_native_areas(net):
    result = net.tie_line_neighborhood(n=1, native_areas=NATIVE_AREAS, side='external')
    native_set = set(NATIVE_AREAS.keys())
    assert not result.bus['area'].isin(native_set).any()


def test_tie_line_neighborhood_internal_subset_of_both(net):
    both = net.tie_line_neighborhood(n=1, native_areas=NATIVE_AREAS, side='both')
    internal = net.tie_line_neighborhood(n=1, native_areas=NATIVE_AREAS, side='internal')
    assert set(internal.bus.index).issubset(set(both.bus.index))


def test_tie_line_neighborhood_kv_filter_reduces_result(net):
    all_ties = net.tie_line_neighborhood(n=0, native_areas=NATIVE_AREAS)
    ehv_ties = net.tie_line_neighborhood(n=0, native_areas=NATIVE_AREAS, kv_min=345)
    assert len(ehv_ties.bus) <= len(all_ties.bus)


def test_tie_line_neighborhood_empty_when_no_tie_lines(net):
    # Area 99 has no buses — no tie lines found — returns empty-section Network
    result = net.tie_line_neighborhood(n=1, native_areas={99: "GHOST"})
    assert isinstance(result, Network)
    assert result.bus.empty


def test_tie_line_neighborhood_output_dict(net):
    result = net.tie_line_neighborhood(n=1, native_areas=NATIVE_AREAS, output='dict')
    assert isinstance(result, dict)
    assert 'bus' in result


def test_tie_line_neighborhood_output_dataframe(net):
    result = net.tie_line_neighborhood(n=1, native_areas=NATIVE_AREAS, output='dataframe')
    assert isinstance(result, pd.DataFrame)
    assert 'section' in result.columns
```

- [ ] **Step 2: Run to verify tests fail**

```
pdm run pytest tests/test_network_queries.py -v -k "tie_line_neighborhood"
```

Expected: `AttributeError: 'Network' object has no attribute 'tie_line_neighborhood'`

- [ ] **Step 3: Add `tie_line_neighborhood` to `Network` in `model.py`**

Insert after `neighborhood`:

```python
    def tie_line_neighborhood(
        self,
        n: int,
        native_areas: dict | list | set | None = None,
        side: str = 'both',
        kv_min: float | None = None,
        kv_max: float | None = None,
        output: str = 'network',
    ) -> 'Network | dict[str, pd.DataFrame] | pd.DataFrame':
        """Neighborhood around all tie-line terminals, optionally scoped by side.

        Convenience wrapper: finds tie lines via find_tie_lines(), seeds
        neighborhood() from their terminal buses, then optionally filters the
        result to buses on one side of the area boundary.

        Args:
            n: Number of bus hops to traverse from tie-line terminals.
            native_areas: Areas considered "native". Defaults to INCLUDE_AREAS.
            side: Which side of the boundary to return.
                'both' (default) — no area filter.
                'internal' — keep only buses in native_areas.
                'external' — keep only buses NOT in native_areas.
            kv_min: Passed to find_tie_lines(); filters by terminal bus kV.
            kv_max: Passed to find_tie_lines(); filters by terminal bus kV.
            output: 'network' (default), 'dict', or 'dataframe'.

        Returns:
            Filtered network data in the requested format. Returns an empty
            result (empty-section Network / empty dict / empty DataFrame) when
            no tie lines match the filter criteria.
        """
        if native_areas is None:
            native_areas = INCLUDE_AREAS
        area_set = set(native_areas.keys()) if isinstance(native_areas, dict) else set(native_areas)

        ties = self.find_tie_lines(native_areas=native_areas, kv_min=kv_min, kv_max=kv_max)

        if ties.empty:
            empty = self.copy()
            for attr_name, df in empty.__dict__.items():
                if isinstance(df, pd.DataFrame) and 'bus_cols' in getattr(df, '_metadata', {}):
                    empty_df = df.iloc[0:0].copy()
                    empty_df._metadata = df._metadata
                    setattr(empty, attr_name, empty_df)
            if output == 'network':
                return empty
            elif output == 'dict':
                return empty.model_dfs()
            else:
                return pd.DataFrame()

        seed_buses: set[int] = set()
        for level in ties.index.names:
            if level in ('ibus', 'jbus'):
                seed_buses |= set(ties.index.get_level_values(level))

        result = self.neighborhood(seed_buses, n, output='network')

        if side == 'internal':
            result = result.filter_by_area(list(area_set))
        elif side == 'external':
            external_areas = set(result.bus['area'].unique()) - area_set
            if external_areas:
                result = result.filter_by_area(list(external_areas))

        if output == 'network':
            return result
        elif output == 'dict':
            return result.model_dfs()
        else:  # 'dataframe'
            frames = []
            for section, df in result.model_dfs().items():
                df = df.reset_index()
                df.insert(0, 'section', section)
                frames.append(df)
            return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
```

- [ ] **Step 4: Run the full test file to verify all tests pass**

```
pdm run pytest tests/test_network_queries.py -v
```

Expected: all 30 tests pass

- [ ] **Step 5: Run full suite to check for regressions**

```
pdm run pytest --cov=psse_model_util --cov-report=term-missing -q
```

Expected: coverage >= 75%, no regressions

- [ ] **Step 6: Commit**

```bash
git add model.py tests/test_network_queries.py
git commit -m "feat(network): add Network.tie_line_neighborhood() convenience wrapper"
```
