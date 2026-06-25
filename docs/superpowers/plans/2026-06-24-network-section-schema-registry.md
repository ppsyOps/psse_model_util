# Network Section-Schema Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the misused per-DataFrame `df._metadata` dict with a typed `SectionSchema` registry held on `Network`, deleting every manual save/restore hack.

**Architecture:** A frozen `SectionSchema` value object (`id_cols`, `bus_cols`, `data_type`) lives in a new `dataformat/section_schema.py`. `Network` holds `self._section_schemas: dict[str, SectionSchema]` keyed by section name, built from `rawx_json_template` at load. Every consumer looks the schema up by section name (always in hand) instead of reading the frame. No metadata rides on any DataFrame, so no pandas op can drop it.

**Tech Stack:** Python 3.14, pandas, PDM, pytest + pytest-cov (gate ≥90%), ruff.

**Spec:** `docs/superpowers/specs/2026-06-24-network-section-schema-registry-design.md`

**Migration safety:** Tasks are ordered so the full suite stays green at every commit. The registry is added *additively* (Task 2) while the existing `df._metadata` writes remain; readers migrate (Tasks 3-4); the legacy `df._metadata` writes and save/restore hacks are removed only after no reader or test depends on them (Task 5).

**Commands:**
- Single test: `pdm run pytest tests/test_section_schema.py -v`
- Full suite + coverage: `pdm run pytest --cov=psse_model_util --cov-report=term-missing`
- Lint: `pdm run ruff check .`

---

## File Structure

| File | Responsibility | Change |
|------|----------------|--------|
| `src/psse_model_util/dataformat/section_schema.py` | `SectionSchema` value object + `from_template` | **Create** |
| `tests/test_section_schema.py` | `SectionSchema` unit tests | **Create** |
| `src/psse_model_util/model.py` | Registry on `Network`, accessors, read-site migration, hack deletion, pickle version sentinel | Modify |
| `src/psse_model_util/common/dataframe_util.py` | Purify `convert_df_column_dtypes`; drop `ModelDF` | Modify |
| `src/psse_model_util/dataformat/classes.py` | Delete dead `ModelDF` class | Modify |
| `src/psse_model_util/compare.py` | `_bus_num_changes` memoization → instance attribute | Modify |
| `tests/test_model.py` | Rewrite metadata-asserting tests/fixtures to registry | Modify |
| `tests/test_compare.py` | Drop vestigial `_metadata` line | Modify |
| `tests/test_phase_2_2.py` | Update 3 manual-init sites | Modify |
| `tests/test_pickle_cache_schema.py` | Pickle round-trip + stale-rebuild tests | **Create** |
| `CLAUDE.md`, `ARCHITECTURE.md`, `docs/RAW_TO_RAWX.md` | Doc the registry, not `df._metadata` | Modify |

---

## Task 1: `SectionSchema` value object

**Files:**
- Create: `src/psse_model_util/dataformat/section_schema.py`
- Test: `tests/test_section_schema.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_section_schema.py
from psse_model_util.dataformat.classes import BusId, Name, Voltage
from psse_model_util.dataformat.section_schema import SectionSchema


def test_empty_schema_defaults():
    s = SectionSchema()
    assert s.id_cols == ()
    assert s.bus_cols == ()
    assert s.data_type == {}


def test_explicit_construction_coerces_to_tuples():
    s = SectionSchema(id_cols=["ibus", "loadid"], bus_cols=["ibus"], data_type={"ibus": int})
    assert s.id_cols == ("ibus", "loadid")
    assert s.bus_cols == ("ibus",)
    assert s.data_type == {"ibus": int}


def test_is_frozen():
    import dataclasses
    s = SectionSchema()
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.id_cols = ("x",)


def test_from_template_zips_data_type_list_to_fields():
    template = {
        "fields": ["ibus", "name", "baskv"],
        "data": [],
        "data_type": [BusId, Name, Voltage],
        "bus_cols": ["ibus"],
        "id_cols": ["ibus"],
    }
    s = SectionSchema.from_template(template, fields=["ibus", "name", "baskv"])
    assert s.bus_cols == ("ibus",)
    assert s.id_cols == ("ibus",)
    assert s.data_type == {"ibus": BusId, "name": Name, "baskv": Voltage}


def test_from_template_missing_keys_yield_empty():
    s = SectionSchema.from_template({"fields": ["iarea"], "data": []}, fields=["iarea"])
    assert s.id_cols == ()
    assert s.bus_cols == ()
    assert s.data_type == {}


def test_from_template_uses_actual_fields_for_zip_length():
    # data_type list longer than actual fields -> zip truncates to fields
    template = {"data_type": [int, float, str], "id_cols": ["a"]}
    s = SectionSchema.from_template(template, fields=["a"])
    assert s.data_type == {"a": int}
```

Add `import pytest` at the top.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pdm run pytest tests/test_section_schema.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'psse_model_util.dataformat.section_schema'`

- [ ] **Step 3: Write the implementation**

```python
# src/psse_model_util/dataformat/section_schema.py
"""Typed per-section schema metadata for network DataFrames.

Replaces the legacy ``df._metadata`` dict. Instances are held in
``Network._section_schemas`` keyed by section name, never on the DataFrame.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class SectionSchema:
    """Schema metadata for one network section.

    Attributes:
        id_cols: Columns forming the unique-equipment index.
        bus_cols: Columns holding bus numbers.
        data_type: Per-column dtype hints, ``{column_name: type}``.
    """

    id_cols: tuple[str, ...] = ()
    bus_cols: tuple[str, ...] = ()
    data_type: Mapping[str, type] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Coerce list/sequence inputs to tuples without breaking frozen-ness.
        object.__setattr__(self, "id_cols", tuple(self.id_cols))
        object.__setattr__(self, "bus_cols", tuple(self.bus_cols))
        object.__setattr__(self, "data_type", dict(self.data_type))

    @classmethod
    def from_template(cls, template: Mapping[str, Any], fields: Sequence[str]) -> "SectionSchema":
        """Build a schema from a ``rawx_json_template['network'][section]`` entry.

        ``data_type`` in the template is a list aligned to the template's fields;
        it is zipped against the *actual* ``fields`` of the parsed DataFrame
        (mirroring the legacy ``_create_dataframe`` behavior, including
        zip-truncation when lengths differ).
        """
        raw_dt = template.get("data_type", [])
        data_type = dict(raw_dt) if isinstance(raw_dt, dict) else dict(zip(fields, raw_dt))
        return cls(
            id_cols=tuple(template.get("id_cols", ())),
            bus_cols=tuple(template.get("bus_cols", ())),
            data_type=data_type,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pdm run pytest tests/test_section_schema.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Lint and commit**

```bash
pdm run ruff check src/psse_model_util/dataformat/section_schema.py tests/test_section_schema.py
git add src/psse_model_util/dataformat/section_schema.py tests/test_section_schema.py
git commit -m "feat: add SectionSchema value object for network section metadata"
```

---

## Task 2: Registry + accessors on `Network` (additive)

Add the registry and accessors **without removing** any existing `df._metadata` write. The suite stays green because behavior is unchanged; we only add a parallel source of truth and read it in new tests.

**Files:**
- Modify: `src/psse_model_util/model.py` (`Network.__init__` ~355-403, `Network._create_dataframe` ~405-544)
- Test: `tests/test_model.py`

- [ ] **Step 1: Write the failing accessor tests**

Add to `tests/test_model.py` (near the other Network tests). The `model1_network` fixture already exists.

```python
from psse_model_util.dataformat.section_schema import SectionSchema


class TestSectionSchemaRegistry:
    def test_known_section_returns_populated_schema(self, model1_network):
        s = model1_network.section_schema("acline")
        assert s.bus_cols == ("ibus", "jbus")
        assert s.id_cols == ("ibus", "jbus", "ckt")
        assert "rpu" in s.data_type

    def test_unknown_section_returns_empty_schema(self, model1_network):
        s = model1_network.section_schema("does_not_exist")
        assert s == SectionSchema()
        assert s.bus_cols == ()

    def test_bus_cols_and_id_cols_conveniences(self, model1_network):
        assert model1_network.bus_cols("bus") == ("ibus",)
        assert model1_network.id_cols("load") == ("ibus", "loadid")
        assert model1_network.bus_cols("area") == ()  # section exists, no bus_cols
```

- [ ] **Step 2: Run to verify failure**

Run: `pdm run pytest tests/test_model.py::TestSectionSchemaRegistry -v`
Expected: FAIL — `AttributeError: 'Network' object has no attribute 'section_schema'`

- [ ] **Step 3: Initialize the registry in `Network.__init__`**

In `Network.__init__`, add the registry dict **before** the section loop. Locate (model.py ~388):

```python
        logger.info('Network.__init__ starting...')
        for subsection, data in section.items():
```

Change to:

```python
        logger.info('Network.__init__ starting...')
        self._section_schemas: dict[str, SectionSchema] = {}
        for subsection, data in section.items():
```

- [ ] **Step 4: Populate the registry in `Network._create_dataframe`**

In `Network._create_dataframe`, immediately after `fields`/`values`/`meta` are extracted (model.py ~463-466, just after `meta: dict = data`), build and store the schema:

```python
        fields: list = data.pop('fields')
        values: list = data.pop('data')
        meta: dict = data

        # Build and register the typed schema for this section (registry is the
        # new source of truth; the df._metadata writes below are legacy and are
        # removed in a later task).
        if self.subsection in rawx_json_template['network']:
            self._section_schemas[self.subsection] = SectionSchema.from_template(
                rawx_json_template['network'][self.subsection], fields)
        else:
            self._section_schemas[self.subsection] = SectionSchema()
```

Note: `_create_dataframe` runs inside the `__init__` loop where `self.subsection` is set and `self._section_schemas` already exists.

- [ ] **Step 5: Add the accessor methods on `Network`**

Add three methods to the `Network` class (place them right after `_create_dataframe`, before `section_with_bus` ~546):

```python
    def section_schema(self, section: str) -> SectionSchema:
        """Return the SectionSchema for a section, or an empty schema if unknown."""
        return self._section_schemas.get(section, SectionSchema())

    def bus_cols(self, section: str) -> tuple[str, ...]:
        """Bus-number columns for a section (empty tuple if none/unknown)."""
        return self.section_schema(section).bus_cols

    def id_cols(self, section: str) -> tuple[str, ...]:
        """Unique-equipment index columns for a section (empty tuple if none/unknown)."""
        return self.section_schema(section).id_cols
```

- [ ] **Step 6: Add the import**

At the top of `model.py`, add to the dataformat imports:

```python
from psse_model_util.dataformat.section_schema import SectionSchema
```

- [ ] **Step 7: Run the new tests + full suite**

Run: `pdm run pytest tests/test_model.py::TestSectionSchemaRegistry -v`
Expected: PASS

Run: `pdm run pytest`
Expected: PASS (no regressions — registry is additive)

- [ ] **Step 8: Commit**

```bash
git add src/psse_model_util/model.py tests/test_model.py
git commit -m "feat: add SectionSchema registry and accessors to Network"
```

---

## Task 3: Rewrite metadata-asserting tests/fixtures to the registry

The registry now exists and is populated, so rewrite the tests that assert on `df._metadata` to assert on the registry **before** we remove the legacy writes. After this task the legacy `df._metadata` is no longer read by any test.

**Files:**
- Modify: `tests/test_model.py` (lines 47-51, 132-144, 191-196, 512-521, 528-536, 701-715)

- [ ] **Step 1: Update the `empty_network` fixture (lines 45-51)**

```python
@pytest.fixture
def empty_network():
    network = Network.__new__(Network)
    network.bus = pd.DataFrame(columns=["ibus", "baskv"])
    network._section_schemas = {
        "bus": SectionSchema(bus_cols=["ibus"], id_cols=["ibus"], data_type={}),
    }
    network._graph = None
    return network
```

- [ ] **Step 2: Rewrite `test_metadata_preservation` (lines 132-144)**

The registry travels with the Network through `filter_by_kv`, so compare registries:

```python
    def test_metadata_preservation(self, model1_network):
        original = model1_network._section_schemas
        result = model1_network.filter_by_kv(230, 500)
        assert result._section_schemas == original
```

- [ ] **Step 3: Rewrite `test_append_bus_info_to_dfs` (lines 191-196)**

```python
def test_append_bus_info_to_dfs(filtered_model):
    net = filtered_model.network
    net.append_bus_info_to_dfs()
    for df_name, df in net.model_dfs().items():
        if df_name != "bus":
            for bus_col in net.bus_cols(df_name):
                assert f"{bus_col}_name" in df.columns
```

- [ ] **Step 4: Rewrite `test_filter_by_area_no_matching_bus_cols_warns` (lines 512-521)**

Register the phantom section's schema instead of stamping the frame:

```python
def test_filter_by_area_no_matching_bus_cols_warns(model1_network):
    """filter_by_area warns (and keeps all rows) when bus_cols are declared for a
    section but none of those columns appear in the DataFrame's index or columns."""
    import copy as copy_mod
    net = copy_mod.deepcopy(model1_network)
    net.phantom = pd.DataFrame({'col_a': [1, 2]})
    net._section_schemas['phantom'] = SectionSchema(bus_cols=['phantom_col'])
    with pytest.warns(UserWarning, match="no bus columns found"):
        net.filter_by_area({1: 'AREA'}, graph_effect='clear')
```

- [ ] **Step 5: Rewrite `test_network_copy_shallow` (lines 528-536)**

Metadata now lives on the Network registry; in shallow mode the dict is shallow-copied so the *schema values* are shared:

```python
def test_network_copy_shallow(model1_network):
    """copy(deep=False) produces a distinct Network whose DataFrames are new
    objects and whose section schemas are shared references (not deepcopied)."""
    shallow = model1_network.copy(deep=False)
    assert shallow is not model1_network
    assert shallow.bus is not model1_network.bus
    # Immutable schema objects are shared in shallow mode
    assert shallow.section_schema("bus") is model1_network.section_schema("bus")
```

- [ ] **Step 6: Rewrite `test_abstract_section_copy_shallow` (lines 701-715)**

`AbstractSection` has no registry (it's Network-specific) and its `copy` no longer special-cases metadata. Repurpose this test to cover the shallow scalar-attr branch that remains:

```python
def test_abstract_section_copy_shallow():
    """AbstractSection.copy(deep=False) deep-copies DataFrames and shallow-copies
    scalar attributes."""
    section_data = {
        'test_sec': {
            'fields': ['col_a', 'col_b'],
            'data': [[1, 'x'], [2, 'y']],
        }
    }
    obj = AbstractSection(section_data)
    obj.marker = "shared"  # an immutable non-DataFrame attribute
    shallow = obj.copy(deep=False)
    assert shallow is not obj
    assert shallow.test_sec is not obj.test_sec          # df always deep-copied
    assert shallow.marker is obj.marker                  # copy.copy() of an immutable returns the same object
```

- [ ] **Step 7: Run the affected tests**

Run: `pdm run pytest tests/test_model.py -v`
Expected: PASS (legacy `df._metadata` writes still present, so any non-rewritten path is unaffected; rewritten tests assert the registry)

- [ ] **Step 8: Commit**

```bash
git add tests/test_model.py
git commit -m "test: assert on SectionSchema registry instead of df._metadata"
```

---

## Task 4: Migrate `model.py` read sites + delete save/restore hacks

Switch every reader to the registry and delete the now-pointless save/restore lines. Behavior is preserved; the existing behavior tests (`filter_by_*`, `graph`, `neighborhood`, `section_with_bus`) act as characterization tests.

**Files:**
- Modify: `src/psse_model_util/model.py`

- [ ] **Step 1: `section_with_bus` (~575-685)**

Replace the metadata read/restore. Change (around 576-588):

```python
        df = getattr(self, section)
        metadata = df._metadata
        df = copy.deepcopy(df)

        if not isinstance(df, pd.DataFrame):
            raise ValueError(f"{section} is not a DataFrame attribute of Network.")

        # Get the bus columns from metadata
        bus_cols = metadata.setdefault('bus_cols', {})

        if not bus_cols:
            raise ValueError(f"No bus columns found in metadata for {section}.")
```

to:

```python
        df = getattr(self, section)
        if not isinstance(df, pd.DataFrame):
            raise ValueError(f"{section} is not a DataFrame attribute of Network.")
        df = copy.deepcopy(df)

        bus_cols = self.bus_cols(section)
        if not bus_cols:
            raise ValueError(f"No bus columns found in metadata for {section}.")
```

Update the `id_cols` read (around 637):

```python
        id_cols = metadata.get('id_cols', [])
```

to:

```python
        id_cols = self.id_cols(section)
```

Delete the restore line (around 676): remove `df._metadata = metadata`.

- [ ] **Step 2: `append_bus_info_to_dfs` (~702-709)**

```python
        for section, df in self.model_dfs().items():
            if section != 'bus' and self.bus_cols(section):
                self.section_with_bus(section, inplace=True)
```

- [ ] **Step 3: `filter_by_area` (~753-790)**

Remove the bus metadata save/restore:

```python
        # Filter bus DataFrame by area
        logger.info(f"Network.filter_by_area: filtering buses for areas: {areas}")
        network.bus = network.bus[network.bus['area'].isin(areas)]
```

(delete the `bus_meta = network.bus._metadata` and `network.bus._metadata = bus_meta` lines)

In the per-section loop, replace the metadata lookup (around 764-768):

```python
        for attr_name, df in network.__dict__.items():
            if isinstance(df, pd.DataFrame) and attr_name != 'bus':
                bus_cols = network.bus_cols(attr_name)
                if not bus_cols:
                    continue  # skip DataFrames without bus references
```

and delete the restore `df._metadata = meta` (around 789), keeping `setattr(network, attr_name, df)`.

- [ ] **Step 4: `filter_section` (~865-870)**

Delete the two metadata lines:

```python
        metadata = df._metadata if hasattr(df, '_metadata') else {}
```
and
```python
            filtered_df._metadata = metadata
```
so the body just does `filtered_df = df.query(where_clause)`.

- [ ] **Step 5: `filter_by_kv` (~960-996)**

Delete `network.bus._metadata = bus_df._metadata` (960). In the loop, replace (967-972):

```python
            bus_cols = network.bus_cols(section_name)
            if not bus_cols:
                continue
```

(removing `metadata = df._metadata` and the `if not metadata or 'bus_cols' not in metadata` guard). Delete the restore `filtered_df._metadata = metadata` (996).

- [ ] **Step 6: `graph()` (~1226-1236)**

```python
            schema = self.section_schema(section)
            logger.debug(f'{section} schema: {schema}')

            if not schema.bus_cols or not schema.id_cols:
                continue

            bus_cols, id_cols = schema.bus_cols, schema.id_cols
```

- [ ] **Step 7: `neighborhood` (~1412-1430)**

```python
            bus_cols = result.bus_cols(attr_name)
            if not bus_cols:
                continue
```

(replacing `meta = df._metadata` / `if 'bus_cols' not in meta`). Delete the restore `filtered._metadata = meta` (1430).

- [ ] **Step 8: `tie_line_neighborhood` empty path (~1485-1487)**

```python
            for attr_name, df in empty.__dict__.items():
                if isinstance(df, pd.DataFrame) and empty.bus_cols(attr_name):
                    empty_df = df.iloc[0:0].copy()
                    setattr(empty, attr_name, empty_df)
```

(removing the `_metadata` check and restore)

- [ ] **Step 9: `copy()` loops — drop `_metadata` lines**

`AbstractSection.copy` (~286-295), `Network.copy` (~1044-1051), `Model.copy` (~2383-2391): in each DataFrame branch, delete the `new_df._metadata = ...` lines (deep and shallow). The DataFrame is still deep-copied; the `_section_schemas` dict is copied by the existing non-DataFrame branch of the same loop. For `Model.copy` also drop the dead `new_df = getattr(new_model, attr_name)` line (it reassigns before setattr anyway).

Example for `Network.copy`:

```python
        for attr_name, attr_value in self.__dict__.items():
            if isinstance(attr_value, pd.DataFrame):
                new_df = copy.deepcopy(attr_value)
                setattr(new_network, attr_name, new_df)
            else:
                if deep:
                    setattr(new_network, attr_name, copy.deepcopy(attr_value))
                else:
                    setattr(new_network, attr_name, copy.copy(attr_value))
```

- [ ] **Step 10: Run full suite**

Run: `pdm run pytest`
Expected: PASS (behavior preserved; `_section_schemas` drives all reads)

- [ ] **Step 11: Lint and commit**

```bash
pdm run ruff check src/psse_model_util/model.py
git add src/psse_model_util/model.py
git commit -m "refactor: read section metadata from registry; delete save/restore hacks"
```

---

## Task 5: Remove legacy `df._metadata` writes from load path

No reader or test depends on `df._metadata` now. Remove the legacy writes so the frame carries nothing.

**Files:**
- Modify: `src/psse_model_util/model.py` (`Network.__init__` ~399, `Network._create_dataframe` ~508-526)

- [ ] **Step 1: Drop the `_orig_dfs_cache` metadata line (~399)**

```python
        self._orig_dfs_cache: dict[str, pd.DataFrame] = dict()
        self._orig_dfs_cache['bus'] = copy.deepcopy(self.bus)
```

(delete `self._orig_dfs_cache['bus']._metadata = self.bus._metadata`)

- [ ] **Step 2: Stop writing `df._metadata` in `_create_dataframe` (~508-526)**

The block currently rebuilds `metadata` from the template and does `df._metadata = metadata`, using `data_type` for coercion and `id_cols` for the index. Replace it to drive coercion/index off the registry schema built in Task 2:

```python
        # Coerce dtypes and set the index using the registry schema (no metadata
        # is written onto the frame).
        schema = self._section_schemas.get(self.subsection, SectionSchema())

        if schema.data_type:
            df = convert_df_column_dtypes(df_in=df,
                                          new_dtypes=dict(schema.data_type),
                                          convert_all_columns=True,
                                          default_types=(int, float, str))

        if schema.id_cols:
            id_cols = [c for c in schema.id_cols if c in df.columns]
            ommited_from_index = set(schema.id_cols) - set(df.columns)
            if ommited_from_index:
                warnings.warn(
                    f'Unable to move columns to index (may be okay for models older '
                    f'than v35): {str(ommited_from_index)}.')
            try:
                df.set_index(id_cols, inplace=True)
            except KeyError as e:
                warnings.warn(f'Error moving columns {str(id_cols)} to index. {str(e)}')

        return df
```

Also delete the now-dead legacy `metadata`/`template` rebuild block immediately above it (the `metadata = df._metadata or {}` block through the old `df._metadata = metadata`, ~508-542) — it is fully replaced by the schema-driven block. Keep the empty-`values` early return and the padding/`pd.DataFrame(...)` construction above it intact.

- [ ] **Step 3: Verify no `df._metadata` writes remain in model.py**

Run: `pdm run pytest && pdm run ruff check src/psse_model_util/model.py`
Expected: tests PASS, ruff clean.

Manually confirm: a grep for `_metadata` in `src/psse_model_util/model.py` should return **no** matches except possibly docstrings/comments (clean those too).

- [ ] **Step 4: Commit**

```bash
git add src/psse_model_util/model.py
git commit -m "refactor: drive dtype coercion and indexing from registry; drop df._metadata writes"
```

---

## Task 6: Purify `convert_df_column_dtypes` and retire `ModelDF`

**Files:**
- Modify: `src/psse_model_util/common/dataframe_util.py` (1-123)
- Modify: `src/psse_model_util/dataformat/classes.py` (delete class, 13-177)
- Check: `tests/test_classes_coverage.py` (stale comment only)

- [ ] **Step 1: Make `convert_df_column_dtypes` a pure transform**

In `dataframe_util.py`: remove the `ModelDF` import (line 14). Change the signature/return hints from `pd.DataFrame | ModelDF` to `pd.DataFrame` (lines 18, 23). Remove the `ModelDF` from the assert (line 46) → `assert isinstance(df_in, pd.DataFrame)`. Delete the metadata lines:

- lines 51-53:
```python
    metadata = df_in._metadata
    if isinstance(df_in, ModelDF):
        meta = df_in.meta
```
- lines 119-121:
```python
    if hasattr(df_in, 'meta'):
        df_out.meta = meta
    df_out._metadata = metadata
```

After removal the function builds `df_out`, converts columns, and `return df_out` with no metadata handling.

- [ ] **Step 2: Delete the `ModelDF` class**

In `dataformat/classes.py`, delete the entire `ModelDF` class (lines 13-177). Keep `import copy`, the `namedtuple` definitions, and everything from `get_builtin_base_type` onward. If `copy`/`pandas` become unused after deletion, remove those imports (ruff will flag unused imports).

- [ ] **Step 3: Fix the stale comment in `test_classes_coverage.py`**

Line 4 mentions "the ModelDF class is dead". Update it to drop the `ModelDF` reference (it no longer exists). Confirm the test file does not import or reference `ModelDF` anywhere (it should not).

- [ ] **Step 4: Run suite + lint**

Run: `pdm run pytest && pdm run ruff check src/psse_model_util/common/dataframe_util.py src/psse_model_util/dataformat/classes.py`
Expected: PASS, ruff clean (no unused `ModelDF` import remains anywhere).

- [ ] **Step 5: Commit**

```bash
git add src/psse_model_util/common/dataframe_util.py src/psse_model_util/dataformat/classes.py tests/test_classes_coverage.py
git commit -m "refactor: purify convert_df_column_dtypes and remove dead ModelDF class"
```

---

## Task 7: `compare.py` memoization → instance attribute

**Files:**
- Modify: `src/psse_model_util/compare.py` (~182-184, 230-231, 267-270)
- Modify: `tests/test_phase_2_2.py` (97, 222, 378)
- Modify: `tests/test_compare.py` (234)

- [ ] **Step 1: Replace the `_metadata` memoization in `__init__` (~182-184)**

```python
        if not hasattr(self, "_bus_num_changes"):
            self._bus_num_changes: pd.DataFrame = pd.DataFrame()
            self._bus_num_changes_join_cols: Optional[list] = None
```

- [ ] **Step 2: Replace the cache-hit check (~230-231)**

```python
        if not self._bus_num_changes.empty and \
                getattr(self, '_bus_num_changes_join_cols', None) == join_columns:
            return self._bus_num_changes
```

- [ ] **Step 3: Replace the cache write (~267-270)**

```python
        if not changes_df.empty:
            result_columns = ['ibus_model1', 'ibus_model2'] + join_columns
            self._bus_num_changes = changes_df[result_columns].copy()
            self._bus_num_changes_join_cols = join_columns
            return self._bus_num_changes
```

- [ ] **Step 4: Update `test_phase_2_2.py` (3 sites: 97, 222, 378)**

Replace each `comp._bus_num_changes._metadata = {'join_columns': []}` with:

```python
        comp._bus_num_changes_join_cols = None
```

- [ ] **Step 5: Update `test_compare.py` (line 234)**

The `large_model.network.bus._metadata = model1.network.bus._metadata` line is vestigial — the registry already travels with `large_model = model1.copy()` and reassigning `.bus` does not touch `_section_schemas`. Delete the line.

- [ ] **Step 6: Run the compare tests + full suite**

Run: `pdm run pytest tests/test_compare.py tests/test_phase_2_2.py -v && pdm run pytest`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/psse_model_util/compare.py tests/test_phase_2_2.py tests/test_compare.py
git commit -m "refactor: replace _bus_num_changes._metadata memoization with instance attribute"
```

---

## Task 8: Pickle cache schema version sentinel

Invalidate-and-rebuild stale `.model` caches (decision A). New caches carry a version; an unpickled Model lacking the current version is ignored and rebuilt from the RAW.

**Files:**
- Modify: `src/psse_model_util/model.py` (module constant, `Model.__init__` ~2139, `_read_json` ~2322/2337, `read_pickle` ~2703-2750)
- Test: `tests/test_pickle_cache_schema.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_pickle_cache_schema.py
from pathlib import Path

import pytest

from psse_model_util.model import MODEL_CACHE_SCHEMA_VERSION, Model

DATA_DIR = Path(__file__).resolve().parent / "data"


def test_fresh_model_has_current_cache_version():
    m = Model(DATA_DIR / "Model_1.raw", force_recalculate=True)
    assert m._cache_schema_version == MODEL_CACHE_SCHEMA_VERSION


def test_pickle_round_trip_preserves_registry(tmp_path):
    m = Model(DATA_DIR / "Model_1.raw", force_recalculate=True)
    pkl = tmp_path / "rt.model"
    m.pickle_path = pkl
    m.to_pickle()
    reloaded = Model(pkl)  # loads via the .model branch
    # registry survived the pickle and a registry-driven op still works
    assert reloaded.network.bus_cols("acline") == ("ibus", "jbus")
    filtered = reloaded.filter_by_area({1: "AREA"}, inplace=False)
    assert len(filtered.network.bus) <= len(reloaded.network.bus)


def test_stale_cache_is_ignored_and_rebuilt(tmp_path):
    # Build a model and corrupt its cache version to simulate a legacy pickle.
    raw = DATA_DIR / "Model_1.raw"
    m = Model(raw, force_recalculate=True)
    cache = m.pickle_path
    assert cache.exists()
    m._cache_schema_version = -1  # stale
    m.to_pickle()  # overwrite cache with a stale-version object
    # Re-open WITHOUT force_recalculate: stale cache must be ignored, model rebuilt.
    with pytest.warns(UserWarning, match="cache schema"):
        m2 = Model(raw)
    assert m2._cache_schema_version == MODEL_CACHE_SCHEMA_VERSION
    assert m2.network.bus_cols("bus") == ("ibus",)
```

- [ ] **Step 2: Run to verify failure**

Run: `pdm run pytest tests/test_pickle_cache_schema.py -v`
Expected: FAIL — `ImportError: cannot import name 'MODEL_CACHE_SCHEMA_VERSION'`

- [ ] **Step 3: Add the module constant**

Near the top of `model.py` (after imports, with other module constants):

```python
# Bump whenever the cached object layout changes (e.g. metadata representation).
# v2 = SectionSchema registry on Network (replaces df._metadata). Caches without
# a matching version are ignored and rebuilt from the RAW.
MODEL_CACHE_SCHEMA_VERSION = 2
```

- [ ] **Step 4: Stamp the version in `Model.__init__`**

Near the start of `Model.__init__` (model.py ~2139, beside `self.raw_file_path = None`):

```python
        self._cache_schema_version = MODEL_CACHE_SCHEMA_VERSION
```

- [ ] **Step 5: Gate `read_pickle` on the version (~2721-2730)**

After `obj = pickle.load(file)` and before copying attributes, add the staleness check:

```python
        obj = None
        try:
            with open(self.pickle_path, mode) as file:
                obj = pickle.load(file)
        except Exception as e:
            if resilient:
                warnings.warn(f'Could not load file {str(self.pickle_path)}. {str(e)}')
            else:
                raise

        # Reject stale caches (decision A: invalidate-and-rebuild, no migration).
        if obj is not None and getattr(obj, '_cache_schema_version', None) != MODEL_CACHE_SCHEMA_VERSION:
            warnings.warn(
                f'Ignoring stale cache schema (found '
                f'{getattr(obj, "_cache_schema_version", None)!r}, expected '
                f'{MODEL_CACHE_SCHEMA_VERSION}): {self.pickle_path}')
            return FpPickleType(None, None)
```

(The existing attribute-copy block and the final `return FpPickleType(...)` stay as-is for the current-version path.)

- [ ] **Step 6: Make the auto-cache caller fall through on miss (~2337-2340)**

```python
            # Check if we can use cached data
            if not force_recalculate and self.pickle_path.exists():
                result = self.read_pickle()
                if result.obj is not None:
                    return self.json_data
                # stale/failed cache -> fall through and rebuild from the RAW/RAWX
```

- [ ] **Step 7: Make the direct-`.model` caller rebuild on miss (~2322-2331)**

```python
        elif Path(file_path_or_json).suffix.lower() == '.model':
            self.raw_file_path = Path(file_path_or_json).with_suffix('.raw')
            if not self.name:
                self.name = self.raw_file_path.stem
            result = self.read_pickle()
            if result.obj is None and self.raw_file_path.exists():
                # stale/failed cache and source RAW available -> rebuild
                self.json_data = raw_file_to_rawx_dict(self.raw_file_path)
```

(If the cache loaded cleanly, `read_pickle` already populated `self`; the `if` simply rebuilds when it didn't and a RAW exists.)

- [ ] **Step 8: Run the new tests + full suite**

Run: `pdm run pytest tests/test_pickle_cache_schema.py -v`
Expected: PASS (3 tests)

Run: `pdm run pytest`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add src/psse_model_util/model.py tests/test_pickle_cache_schema.py
git commit -m "feat: version-gate the .model pickle cache; rebuild stale caches"
```

---

## Task 9: Documentation

**Files:**
- Modify: `CLAUDE.md` (DataFrame metadata convention section)
- Modify: `ARCHITECTURE.md` (lines ~174, 206-208, 279)
- Modify: `docs/RAW_TO_RAWX.md` (lines ~234, 282)

- [ ] **Step 1: Update `CLAUDE.md`**

Replace the "DataFrame metadata convention" section (the table describing `df._metadata` with `id_cols`/`bus_cols`/`data_type`) with a description of the registry:

```markdown
### Section-schema registry

Schema metadata is **not** stored on the DataFrames. Each `Network` holds a
`_section_schemas: dict[str, SectionSchema]` keyed by section name, built from
`dataformat/rawx_json_template.py` at load. Look it up via the Network-level
accessors:

| Accessor | Returns |
|----------|---------|
| `network.section_schema(name)` | `SectionSchema(id_cols, bus_cols, data_type)` (empty if unknown) |
| `network.bus_cols(name)` | tuple of bus-number columns |
| `network.id_cols(name)` | tuple of index columns |

`SectionSchema` (`dataformat/section_schema.py`) is a frozen dataclass. Because
the metadata lives on `Network`, not the frame, no pandas operation can drop it,
and it pickles with the model. Any new network section must have an entry in
`rawx_json_template.py`.
```

- [ ] **Step 2: Update `ARCHITECTURE.md`**

Replace the `## DataFrame Metadata (`df._metadata`)` section and the load-step "Attach metadata to df._metadata" line with the registry description (same substance as Step 1). Update the design-rationale row (~279) to read e.g. "Section schema in `Network._section_schemas` | Per-section schema awareness off the frame; survives all pandas ops and pickling; used by `filter_by_area()`, `graph()`, etc."

- [ ] **Step 3: Update `docs/RAW_TO_RAWX.md`**

Replace the "Attach metadata: `df._metadata = {...}`" step (~234) and the diagram annotation (~282) with the registry equivalent: the parsed frame is stored on `Network`, and its `SectionSchema` is registered in `Network._section_schemas[section]`.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md ARCHITECTURE.md docs/RAW_TO_RAWX.md
git commit -m "docs: describe the SectionSchema registry; drop df._metadata references"
```

---

## Task 10: Final verification

- [ ] **Step 1: Full suite with coverage**

Run: `pdm run pytest --cov=psse_model_util --cov-report=term-missing`
Expected: PASS, coverage ≥ 90% (CI gate `fail_under=90`).

- [ ] **Step 2: Lint**

Run: `pdm run ruff check .`
Expected: clean (no errors).

- [ ] **Step 3: Confirm no stray `_metadata` / `ModelDF` references in `src/`**

Grep `src/psse_model_util` for `_metadata` and `ModelDF`. Expected: zero matches (docstrings/comments included). The only surviving `ModelDF` reference may be in `tests/legacy_tests/example_model.py`, which is **not** on the pytest path and is intentionally left alone.

- [ ] **Step 4: Build sanity (optional)**

Run: `pdm run hatch build`
Expected: builds without error.

- [ ] **Step 5: Push and open the PR (after user approval)**

```bash
git push -u origin worktree-section-schema-registry
gh pr create --base main --title "Replace df._metadata with a typed SectionSchema registry on Network" --body "<summary + link to spec/plan>"
```

Do **not** merge without explicit approval.

---

## Self-review notes (coverage of spec)

- Spec §1 SectionSchema → Task 1. §2 registry/accessors → Task 2. §3 read sites → Task 4. §4 hack deletion → Tasks 4-5. §5 convert_df_column_dtypes → Task 6. §6 ModelDF → Task 6. §7 compare memoization → Task 7. §8 pickle version → Task 8. §9 docs → Task 9. Testing strategy → Tasks 1,2,3,8,10.
- Type consistency: `SectionSchema(id_cols, bus_cols, data_type)`, `from_template(template, fields)`, `section_schema(name)`, `bus_cols(name)`, `id_cols(name)`, `MODEL_CACHE_SCHEMA_VERSION`, `_cache_schema_version`, `_section_schemas`, `_bus_num_changes_join_cols` — used identically across all tasks.
- Coverage gate: the deleted `ModelDF` (dead, uncovered) and deleted save/restore branches remove uncovered/branchy lines; new code (SectionSchema, accessors, version gate) is directly tested. Net effect on the ≥90% gate is verified in Task 10.
```
