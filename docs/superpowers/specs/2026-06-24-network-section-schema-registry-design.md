# Network Section-Schema Registry — Design

**Date:** 2026-06-24
**Status:** Approved (brainstorm) → pending spec review
**Scope:** Replace the per-DataFrame `df._metadata` dict with a typed schema registry held on `Network`.

## Problem

Each network-section DataFrame (`model.network.bus`, `.acline`, `.generator`, …) needs three
pieces of schema metadata that pandas does not model natively:

- `id_cols: list[str]` — columns forming the unique-equipment index
- `bus_cols: list[str]` — columns holding bus numbers
- `data_type: dict[str, type]` — per-column dtype hints used for coercion at load

Today these live in `df._metadata` as a **dict instance attribute** on a plain `pd.DataFrame`
(`model.py` `_create_dataframe`, ~508-526). This misuses pandas' `_metadata`, which is a
*class-level list of attribute names* propagated through `__finalize__`. By assigning a dict, the
code shadows that mechanism, so pandas treats the metadata as an inert, invisible attribute. **Any**
operation that returns a new frame (`df[mask]`, `.query()`, `.merge()`, `.copy()`,
`.reset_index()`, …) constructs a fresh object without it, dropping the metadata.

Consequently the codebase is littered with manual save-before / restore-after hacks at every site
that transforms a section DataFrame (the three `copy()` loops, `section_with_bus`, `filter_by_area`,
`filter_by_kv`, `filter_section`, `neighborhood`, `tie_line_neighborhood`, and
`convert_df_column_dtypes`). The fragility is silent: a missed restore yields an empty `bus_cols`
rather than an error.

An earlier fix attempt, the `ModelDF(pd.DataFrame)` subclass
(`dataformat/classes.py:13-177`), is abandoned dead code — its `__init__` raises
`NotImplementedError`, so it is never instantiated. It survives only because `dataframe_util.py`
imports it for `isinstance` checks and a return-type hint.

## Decision drivers (confirmed during brainstorm)

1. **Metadata is private/internal.** Nothing outside `Network`/`Model`/`ModelComparison` reads
   `df._metadata`, `.id_cols`, or `.bus_cols`. The sibling `key_facilities` repo does **not** touch
   it.
2. **Pickle must preserve the complete model** so work resumes without re-parsing the RAW. The
   metadata must survive pickling — but it need not be *on the frame* to do so.
3. **Stale on-disk `.model` caches may be rebuilt** (decision A). A one-time cache invalidation is
   acceptable; no transparent migration of legacy pickles is required.
4. **Layering rule:** Network methods must not be surfaced on `Model`. The registry and its
   accessors live on `Network`.

## Chosen approach: external schema registry on `Network`

Move the `{id_cols, bus_cols, data_type}` triple **off** the DataFrame and onto `Network`, keyed by
section name. Because the source of truth (`rawx_json_template['network'][<section>]`) is already a
per-section, name-keyed registry, and because every consumer iterates sections via `model_dfs()` /
`__dict__` (so the section name is always in hand), reads can look the schema up by name. No
metadata rides on the frame, so no pandas operation can drop it, and every save/restore hack is
**deleted** rather than ported.

Rejected alternatives:

- **Proper `pd.DataFrame` subclass** (correct `_metadata` names + `_constructor` + custom
  `__finalize__`): would propagate through most ops, but `pd.merge` (used in `section_with_bus`) and
  any future `pd.concat`/`groupby` still drop custom metadata (pandas #29442, #34177), so the
  save/restore discipline could not be retired — only reduced. It also reintroduces a custom type
  that leaks into return types, `isinstance` checks, and — critically — **pickle path-coupling**
  (every `.model` cache hard-binds to the class staying importable at the same path). This is the
  `ModelDF` path that already failed.
- **`df.attrs`**: smallest diff, but `attrs` is *also* dropped by merge/concat/mask, so every
  save/restore hack stays. Fixes the cosmetic "misuses `_metadata`" complaint without fixing the
  fragility.

## Components

### 1. `SectionSchema` — typed value object

New module `dataformat/section_schema.py`:

```python
from dataclasses import dataclass, field
from typing import Mapping

@dataclass(frozen=True)
class SectionSchema:
    id_cols:  tuple[str, ...] = ()
    bus_cols: tuple[str, ...] = ()
    data_type: Mapping[str, type] = field(default_factory=dict)

    @classmethod
    def from_template(cls, section_template: dict, fields: list[str]) -> "SectionSchema":
        ...  # centralizes the list-of-types -> {field: type} conversion currently inline
```

- Frozen and immutable; tuples for the column lists. `data_type` is a read-only mapping.
- `from_template` centralizes the `dict(zip(fields, data_type))` conversion that
  `_create_dataframe` does inline today.
- An empty `SectionSchema()` (all defaults) represents "section has no schema metadata" — returned
  for unknown sections so callers keep their existing "no bus_cols → skip" control flow without
  `KeyError` / `hasattr` guards.

### 2. The registry on `Network`

- `self._section_schemas: dict[str, SectionSchema]` — keyed by section/attr name, built in
  `_create_dataframe` from `rawx_json_template['network'][<section>]`.
- Accessors (Network-level only — not surfaced on `Model`):
  - `section_schema(section: str) -> SectionSchema` — returns the schema, or an empty
    `SectionSchema()` for unknown sections.
  - `bus_cols(section: str) -> tuple[str, ...]` — convenience for `section_schema(section).bus_cols`.
  - `id_cols(section: str) -> tuple[str, ...]` — convenience for `section_schema(section).id_cols`.

### 3. Read sites rewired (8)

Each already has the section name available. `df._metadata['bus_cols']` →
`self.section_schema(section).bus_cols`:

| Site | Reads |
|------|-------|
| `section_with_bus` | `bus_cols`, `id_cols` |
| `append_bus_info_to_dfs` | `bus_cols` |
| `filter_by_area` | `bus_cols` |
| `filter_by_kv` | `bus_cols` |
| `graph()` | `bus_cols`, `id_cols` |
| `neighborhood` | `bus_cols` |
| `tie_line_neighborhood` (empty path) | `bus_cols` |
| `convert_df_column_dtypes` (dtype read) | becomes a pure transform; see §5 |

Behavior is preserved exactly, including the `ValueError` `section_with_bus` raises when a section
has no `bus_cols`.

### 4. Save/restore hacks deleted

- The three `copy()` loops (`AbstractSection.copy`, `Network.copy`, `Model.copy`) drop their
  `_metadata` lines. `_section_schemas` is a plain dict in `__dict__`, handled by the existing copy
  machinery; `SectionSchema` is immutable, so sharing on shallow copy is safe.
- `_create_dataframe` stops writing to the frame; it builds the `SectionSchema`, still uses
  `data_type` for dtype coercion and `id_cols` to set the index.
- Every `df._metadata = ...` restore line in `filter_*`, `section_with_bus`, `neighborhood`, and the
  `tie_line` empty path is removed.

### 5. `convert_df_column_dtypes` becomes a pure transform

`dataframe_util.convert_df_column_dtypes` drops all `_metadata` / `meta` / `ModelDF` handling and
becomes a plain DataFrame dtype-coercion utility. Callers (only `_create_dataframe` and tests) do
not depend on it preserving metadata.

### 6. Retire `ModelDF`

- Delete the dead `ModelDF` class from `dataformat/classes.py`.
- `dataframe_util.py`: drop the import, the `isinstance(..., ModelDF)` branches, and change
  return-type hints to `pd.DataFrame`.
- `legacy_tests/example_model.py` keeps a stale `ModelDF` reference but is **not** on the pytest
  path, so CI is unaffected. Left as-is.

### 7. `compare.py` memoization (separate `_metadata` misuse)

`ModelComparison._bus_num_changes._metadata['join_columns']` is a memoization *cache key*, not
section schema. Convert it to a plain instance attribute on `ModelComparison` (e.g.
`self._bus_num_changes_join_cols`). This removes the last `_metadata` misuse and is small and
contained. It does **not** use the `SectionSchema` registry (different concern).

### 8. Pickle cache invalidation (decision A)

Add a cache schema-version sentinel. On load, a version mismatch — or an unpickled `Network`
lacking the `_section_schemas` attribute — marks the cache stale and triggers a rebuild from the
RAW. No transparent migration of legacy pickles.

*Open item for the plan (code-peek #1):* confirm the exact cache load/validate path in
`Model.__init__` / the pickle-load helper, and where the version sentinel is best placed.

### 9. Docs

Update `CLAUDE.md`, `ARCHITECTURE.md`, and `docs/RAW_TO_RAWX.md` to describe the registry instead of
`df._metadata`.

## Data flow (after)

```
.raw  → raw_to_rawx.raw_file_to_rawx_dict() → rawx dict ┐
.rawx → json_util.load_and_clean_json()      → rawx dict ┤
                                                          ↓
                       Network.__init__ → _create_dataframe(data, section)
                                                          ↓
              ┌─────────────────────────────────────────────────────────┐
              │ plain pd.DataFrame (typed, indexed)   → setattr(self, …) │
              │ SectionSchema.from_template(...)      → self._section_schemas[section] │
              └─────────────────────────────────────────────────────────┘
                                                          ↓
        consumers look up schema by section name: self.section_schema(section)
```

## Error handling

- Unknown section → `section_schema` returns an empty `SectionSchema()`; callers skip as today.
- `section_with_bus` on a section with no `bus_cols` → `ValueError` (unchanged).
- Stale/incompatible pickle → detected on load, rebuilt from RAW (no crash, no silent partial load).

## Testing strategy (TDD)

1. `SectionSchema` unit tests — construction, `from_template` (list-of-types conversion), empty
   defaults, immutability.
2. `Network.section_schema` / `bus_cols` / `id_cols` accessor tests — known section returns
   populated schema; unknown section returns empty `SectionSchema()`.
3. Behavior-preservation — adapt existing tests that assert on `_metadata` to assert on
   schema/behavior: `filter_by_area`, `filter_by_kv`, `section_with_bus`, `graph`, `neighborhood`,
   `copy`.
4. Pickle round-trip — build → pickle → reload → schemas intact + a filter still works.
5. Stale-cache rebuild — a pickle without `_section_schemas` triggers re-parse.
6. `compare` memoization — `bus_num_changes` still caches correctly with the new attribute.
7. Full suite green, coverage ≥ 90 (CI gate), ruff clean.

*Open item for the plan (code-peek #2):* enumerate the exact existing tests touching `_metadata`
(`tests/test_model.py:49,517,536,710,715`, `tests/test_compare.py:234`,
`tests/test_phase_2_2.py:97,222,378`) so the rewrite list in step 3/6 is precise.

## Out of scope

- No transparent migration of legacy `.model` pickles (decision A).
- No change to the `rawx_json_template` source-of-truth format.
- No refactor of `legacy_tests/` (not on the pytest path).
- No new public API beyond the Network-level accessors.
