# Flowgate Key-Element Extraction — Design

**Date:** 2026-05-29
**Status:** Approved (brainstorming phase)
**Author:** Chris (Orion Cognition Labs)

## 1. Purpose

Given a PSS/E `.mon` flowgate-definitions file and a PSS/E `.raw` network model, produce three pandas DataFrames listing the "key facilities" near each flowgate's monitored and contingency elements:

1. AC branches and 2-winding transformers within 4 bus-hops of any seed element, filtered to 160 kV ≤ kV ≤ 765 kV (loose: either end in range).
2. Generators within 4 bus-hops of any seed element, filtered to `PT ≥ 15 MW`.
3. 3-winding transformers within 4 bus-hops of any seed element, with at least one winding bus in range.

A fourth `unresolved` DataFrame reports `.mon` elements that could not be mapped to the `.raw` model.

The reusable parsing and neighborhood logic lives inside the `psse_model_util` package; a separate standalone CLI script in a sibling repo orchestrates the pipeline and writes CSV output.

## 2. Inputs and Outputs

### Input: `.mon` flowgate-definitions file

PSS/E `.mon` format. Sample fragment:

```
BUSNAMES
MONITOR FLOWGATE 1600  'Tanners Creek - Dearborn 345kV l/o L765.Marysville-Sorenson'
         BRANCH FROM BUS '05TANNER    345.00' TO BUS '06DEARB1    345.00' CKT Z1
 CONTINGENCY 1600
    OPEN BRANCH FROM BUS '05MARYSVL_RS765.00' TO BUS '05SORENSN_RM765.00' CKT 1
 END
    CA AEP OVEC
    SC PJM
    TP PJM PJM
END
```

Key fields:
- `MONITOR FLOWGATE <id> '<description>'` — opens a flowgate; `<id>` is an integer.
- `BRANCH FROM BUS '<name+kv>' TO BUS '<name+kv>' CKT <id>` — a monitored branch.
- `CONTINGENCY <id>` — opens the contingency block.
- `OPEN BRANCH …`, `OPEN GEN …`, `OPEN LINE …` — contingency actions.
- `SC <name>` — Security Coordinator (the file is filtered by this).
- `END` — closes the contingency block or the flowgate.

Bus tokens are 18 characters wide: 12-char left-padded name + 6-char right-padded kV string (e.g. `'05TANNER    345.00'`, `'05MARYSVL_RS765.00'`). kV may have up to 3 decimal places.

### Input: `.raw` PSS/E model file

Loaded via `psse_model_util.Model(raw_path)`.

### Output: dict of four DataFrames

Returned from `collect_key_facilities()`; CLI also writes each as a CSV.

**`branches`** — AC lines and 2-winding transformers:

| Column | Type | Notes |
|---|---|---|
| `flowgate_id` | int | Flowgate this row belongs to |
| `role` | str | `"monitor"` or `"contingency"` |
| `equipment_type` | str | `"line"` or `"transformer_2w"` |
| `from_name` | str | |
| `from_volt` | float | base kV (preserves up to 3 dp) |
| `from_area` | int | |
| `to_name` | str | |
| `to_volt` | float | |
| `to_area` | int | |
| `ckt_id` | str | |

**`generators`** — machines with `PT ≥ gen_min_mw`:

| Column | Type |
|---|---|
| `flowgate_id` | int |
| `role` | str |
| `bus_name` | str |
| `volt` | float |
| `area` | int |
| `ckt_id` | str (machine id) |

**`transformers_3w`** — 3-winding transformers:

| Column | Type |
|---|---|
| `flowgate_id` | int |
| `role` | str |
| `transformer_name` | str |
| `w1_bus_name` | str |
| `w1_volt` | float |
| `w2_bus_name` | str |
| `w2_volt` | float |
| `w3_bus_name` | str |
| `w3_volt` | float |
| `ckt_id` | str |

**`unresolved`** — `.mon` elements that could not be mapped:

| Column | Type |
|---|---|
| `flowgate_id` | int |
| `role` | str |
| `element_type` | str |
| `raw_tokens` | str (joined repr of the raw `.mon` tokens) |
| `reason` | str (`bus_not_found`, `branch_not_found`, `generator_not_found`) |

### Row granularity

- One row per `(flowgate_id, equipment)` pair. Equipment that appears in N flowgates produces N rows, one per FG.
- If a piece of equipment is reached by both a monitor seed and a contingency seed within the same FG, emit two rows (one per `role`).

## 3. Architecture

### 3.1 New submodule: `psse_model_util/flowgate.py`

Top-of-module constants:

```python
# Path defaults are intentionally empty — callers (or the CLI) must supply real paths.
# They exist as named constants so callers can `from psse_model_util.flowgate import
# DEFAULT_RAW_FILEPATH` and override in one place if a project ever wants a fixed default.
DEFAULT_RAW_FILEPATH: pathlib.Path | str = ""
DEFAULT_MON_FILEPATH: pathlib.Path | str = ""

DEFAULT_HOPS: int = 4
DEFAULT_KV_MIN: float = 160.0
DEFAULT_KV_MAX: float = 765.0
DEFAULT_GEN_MIN_MW: float = 15.0
DEFAULT_SC: str = "PJM"            # SC = Security Coordinator
KV_KEY_DECIMALS: int = 3           # rounding precision for bus-lookup key
```

### 3.2 Data classes

```python
@dataclass(frozen=True)
class FlowgateElement:
    flowgate_id: int
    role: Literal["monitor", "contingency"]
    element_type: Literal["branch", "generator"]   # transformers parsed as branches
    raw_tokens: tuple                              # original .mon tokens, for reporting

@dataclass(frozen=True)
class Flowgate:
    flowgate_id: int
    description: str
    sc: str                                        # Security Coordinator
    monitor: list[FlowgateElement]
    contingency: list[FlowgateElement]

@dataclass(frozen=True)
class ResolvedSeed:
    flowgate_id: int
    role: Literal["monitor", "contingency"]
    element_type: Literal["branch", "generator"]
    seed_buses: frozenset[int]                     # the ibus values for neighborhood seeding
    raw_tokens: tuple
```

### 3.3 Stage functions

```python
def parse_mon_file(path: pathlib.Path | str = DEFAULT_MON_FILEPATH) -> list[Flowgate]: ...

def filter_by_sc(fgs: list[Flowgate], sc: str = DEFAULT_SC) -> list[Flowgate]: ...

def resolve_elements(
    fgs: list[Flowgate], model: Model
) -> tuple[list[ResolvedSeed], pd.DataFrame]:
    # second return = unresolved DataFrame
    ...

def neighborhood_buses(
    model: Model, seed_buses: set[int], hops: int = DEFAULT_HOPS
) -> set[int]:
    # bus-only graph traversal; returns the union of all buses within `hops`
    ...

def collect_key_facilities(
    model: Model,
    seeds: list[ResolvedSeed],
    *,
    hops: int = DEFAULT_HOPS,
    kv_min: float = DEFAULT_KV_MIN,
    kv_max: float = DEFAULT_KV_MAX,
    gen_min_mw: float = DEFAULT_GEN_MIN_MW,
) -> dict[str, pd.DataFrame]:
    # returns {"branches", "generators", "transformers_3w", "unresolved"}
    ...
```

### 3.4 Standalone CLI script

Lives in sibling repo `C:\Users\Chris\PycharmProjects\key_facilities\`:

```
key_facilities/
├── key_facilities.py       # CLI orchestrator
├── pyproject.toml          # depends on psse-model-util (editable in dev)
├── README.md
└── tests/
    └── test_cli_smoke.py
```

CLI invocation:

```
python key_facilities.py \
  --mon path/to/flowgates.mon \
  --raw path/to/Model_1.raw \
  --out-dir outputs/ \
  [--hops 4] [--kv-min 160] [--kv-max 765] [--gen-min-mw 15] [--sc PJM]
```

CLI behavior:
1. Parse `.mon` → `list[Flowgate]`.
2. Filter by SC.
3. Load `Model(raw_path)` (uses the package's pickle cache automatically).
4. Resolve elements → `(seeds, unresolved_df)`.
5. `collect_key_facilities` → dict of 4 DataFrames.
6. Create `--out-dir` if missing; write `branches.csv`, `generators.csv`, `transformers_3w.csv`, `unresolved.csv`.
7. Print one-line summary: parsed/filtered/resolved counts + per-CSV row counts.

## 4. Data Flow

```
flowgates.mon  ──parse_mon_file──►  list[Flowgate]
                                      │
                                      ▼
                              filter_by_sc("PJM")
                                      │
                                      ▼
Model(.raw) ──►  resolve_elements  ──► list[ResolvedSeed]  +  unresolved_df
                                      │
                                      ▼
                            collect_key_facilities
                ┌───────────────────┼───────────────────┐
                ▼                   ▼                   ▼
       neighborhood_buses     filter by kV/MW     assemble rows
       (nx.ego_graph on       (160≤kV≤765,         (flowgate_id, role,
        bus-only subgraph,     PT ≥ 15 MW)          equipment attrs)
        radius=4)
                                      │
                                      ▼
            dict{branches, generators, transformers_3w, unresolved}
                                      │
                                      ▼
                        CLI writes 4 CSVs to --out-dir
```

## 5. Implementation Details

### 5.1 Parser

Small line-by-line state machine. States: `TOP`, `IN_MONITOR`, `IN_CONTINGENCY`. Transitions on keywords `MONITOR FLOWGATE`, `BRANCH`, `CONTINGENCY`, `OPEN`, `SC`, `CA`, `TP`, `END`.

Bus-token splitter: a token like `'05TANNER    345.00'` is unquoted, then split as `name = token[:12].strip()`, `kv = float(token[12:].strip())`. The original token is preserved in `raw_tokens` for the unresolved report.

`END` semantics: the first `END` after `CONTINGENCY` closes the contingency block; the next `END` closes the flowgate. The `SC`/`CA`/`TP` lines sit between those two `END`s.

### 5.2 Bus-name resolution

Build one lookup at the start of `resolve_elements`:

```python
bus_df = model.network.bus
lookup = {
    (str(name).strip(), round(float(basekv), KV_KEY_DECIMALS)): ibus
    for ibus, name, basekv in zip(bus_df.index, bus_df["name"], bus_df["basekv"])
}
```

For each `.mon` seed:
- Resolve from/to bus tokens via `lookup.get((name, round(kv, KV_KEY_DECIMALS)))`.
- For a branch seed, additionally confirm `(ibus, jbus, ckt)` exists in `acline` (any order) or in 2W rows of `transformer`. On miss: `unresolved` with `reason="branch_not_found"`.
- For a generator seed (see §9 — only `OPEN BRANCH` is implemented in v1; generator-seed parsing is deferred until a real `.mon` sample with `OPEN GEN` is in hand), confirm `(ibus, id)` exists in `generator`. On miss: `reason="generator_not_found"`.

Element seed buses recorded in `ResolvedSeed.seed_buses`:
- Branch: `{from_ibus, to_ibus}`.
- Generator: `{gen_ibus}`.

### 5.3 Bus-only graph

Build once per call to `collect_key_facilities`:

```python
G = nx.Graph()
G.add_nodes_from(model.network.bus.index)            # bus ibus values

# AC lines: each row contributes an edge (ibus, jbus)
ac = model.network.acline
G.add_edges_from(zip(ac["ibus"], ac["jbus"]))

# 2W transformers: same shape
xf2 = model.network.transformer.query("nwind == 2")  # or however 2W is tagged
G.add_edges_from(zip(xf2["ibus"], xf2["jbus"]))

# 3W transformers: each contributes a triangle among (ibus, jbus, kbus)
xf3 = model.network.transformer.query("nwind == 3")
for i, j, k in zip(xf3["ibus"], xf3["jbus"], xf3["kbus"]):
    G.add_edges_from([(i, j), (j, k), (i, k)])
```

Then per seed: `nx.ego_graph(G, seed_bus, radius=hops, undirected=True).nodes`.

Union across all seed buses inside a single FG to get that FG's neighborhood set.

### 5.4 Equipment selection and filtering

Given an FG's neighborhood `N` (a set of `ibus` values):

- **Branches DataFrame** = rows of `acline` ∪ 2W `transformer` where `ibus ∈ N OR jbus ∈ N`, then keep rows where `kv_min ≤ from_kv ≤ kv_max OR kv_min ≤ to_kv ≤ kv_max`. Attach `equipment_type` accordingly. Left-join `bus` table to populate `*_name`, `*_volt`, `*_area`.
- **Generators DataFrame** = rows of `generator` where `ibus ∈ N AND pt ≥ gen_min_mw`. Left-join `bus`.
- **3W transformers DataFrame** = 3W rows of `transformer` where `ibus ∈ N OR jbus ∈ N OR kbus ∈ N`, then keep rows where any of the three winding base kVs fall in `[kv_min, kv_max]`. Left-join `bus` three times for w1/w2/w3 attrs. `transformer_name` from the 3W row's name column.

Per-FG and per-role processing produces one row per `(flowgate_id, role, equipment)`. Concatenate across FGs and roles to build the final DataFrames.

### 5.5 kV precision

- Parser: `float(kv_str)` — no rounding on the stored value.
- Lookup key: `round(kv, KV_KEY_DECIMALS)` (3 dp by default). Both sides of the lookup apply the same rounding.
- Range filter (`kv_min ≤ kv ≤ kv_max`): uses the unrounded float.

## 6. Error Handling

| Failure mode | Behavior | Where |
|---|---|---|
| Bus name + kV not in model | Append to `unresolved_df` with `reason="bus_not_found"`. Continue. | `resolve_elements` |
| Both buses resolve but branch (ckt) doesn't exist | `reason="branch_not_found"`. Continue. | `resolve_elements` |
| Generator seed bus exists but no machine with that id | `reason="generator_not_found"`. Continue. | `resolve_elements` |
| `.mon` syntax error (unbalanced `MONITOR`/`END`, malformed BRANCH line) | Raise `ValueError` with line number. **Fail loud.** | `parse_mon_file` |
| `.raw` file missing or fails to load | Let `Model.__init__` raise — no swallowing. | CLI |
| `--out-dir` doesn't exist | Create it via `Path.mkdir(parents=True, exist_ok=True)`. | CLI |
| Unknown contingency action (not `OPEN BRANCH`/`OPEN GEN`/`OPEN LINE`) | Log warning, skip action, continue. Matches `RESILIENT=True`. | `parse_mon_file` |

CLI end-of-run summary:

```
Parsed 12 flowgates → 11 PJM → resolved 27/28 seeds (1 unresolved).
Wrote branches.csv (143 rows), generators.csv (22 rows),
      transformers_3w.csv (4 rows), unresolved.csv (1 row).
```

## 7. Synthetic Test Fixture

`Model_1.raw` contains no `PJM` data, so a synthetic `.mon` aligned with it is needed.

**One-shot generator script:** `tests/build_synthetic_mon.py` (not run by pytest; the output is committed).

```python
MODEL_1_PJM_AREAS = {1, 2, 3}   # CENTRAL, EAST, CENTRAL_DC in Model_1.raw
                                # hardcoded so the fixture is stable regardless of
                                # what psse_model_util.common.constants.NATIVE_AREAS
                                # is set to at any given time.
```

Procedure:
1. Load `tests/data/Model_1.raw`.
2. From `model.network.acline`, pick ~3 branches whose from-bus area ∈ `MODEL_1_PJM_AREAS` and whose base kV ≥ 160 (so the kV filter doesn't drop everything).
3. For each pick, pair it with a contingency branch in the same area (different ckt where possible).
4. Add one flowgate whose seeds are in areas **outside** `{1, 2, 3}` and tag it `SC OTHER` — used by `test_filter_by_sc` to verify the SC filter drops it.
5. Write `tests/data/synthetic_pjm.mon` in the exact `.mon` format from the production sample.

## 8. Testing Strategy

Active tests in `tests/test_flowgate.py` (on the pytest path):

1. **`test_parse_mon_file_basic`** — `synthetic_pjm.mon` parses; ≥ 3 flowgates; each has `flowgate_id`, `sc`, ≥ 1 monitor element, ≥ 1 contingency element.
2. **`test_parse_handles_quoted_bus_tokens`** — inline `.mon` string with `'05TANNER    345.00'`; assert `name == "05TANNER"`, `kv == 345.00`.
3. **`test_parse_preserves_kv_decimal_precision`** — token with `69.125`; stored kV is `69.125`, not `69` or `69.13`.
4. **`test_filter_by_sc`** — the `SC OTHER` flowgate is dropped when `sc="PJM"`.
5. **`test_resolve_elements_happy_path`** — all synthetic FGs resolve against `Model_1.raw`; `unresolved_df` is empty.
6. **`test_resolve_elements_unresolved`** — hand-crafted `.mon` with a bogus bus name; bogus element lands in `unresolved_df` with a reason; the rest still resolve.
7. **`test_neighborhood_buses_hop_count`** — small known subgraph from `Model_1.raw`; `hops=1` returns seed + direct neighbors, `hops=2` extends one more layer, `hops=4` matches a hand-counted expected set.
8. **`test_collect_branches_kv_filter`** — low-voltage branch (< 160 kV) on a neighborhood bus is excluded; high-voltage one is kept; branch with one end ≥ 160 and the other < 160 is kept (loose rule).
9. **`test_collect_generators_mw_filter`** — gen with `PT=10` excluded; `PT=15` and `PT=200` included.
10. **`test_collect_transformers_3w`** — 3W transformer with any winding bus in neighborhood is included; all three `(w*_bus_name, w*_volt)` populated.
11. **`test_collect_rows_one_per_fg_equipment_pair`** — equipment reached by 2 FGs appears in 2 rows.
12. **`test_collect_role_column`** — `role` column carries `"monitor"` / `"contingency"` correctly.
13. **`test_cli_writes_csvs`** — `subprocess.run` the CLI script against `Model_1.raw` + `synthetic_pjm.mon`; assert four CSVs land in tmp out-dir with the right columns.

**Coverage target:** ≥ 80% on `psse_model_util/flowgate.py` (well above the repo's 40% gate).

**Out of scope:**
- v33 RAW parsing (covered by the package's own tests).
- Pickle cache hit/miss behavior.
- CSV write atomicity or large-file performance.

## 9. Out of Scope

- **3W transformers as monitored or contingency elements.** The sample `.mon` only shows `BRANCH` monitors and `OPEN BRANCH` contingencies. If 3W monitors/contingencies appear in real files later, extend `FlowgateElement.element_type` and `resolve_elements`.
- **Generator contingencies (`OPEN GEN`) in v1.** The provided sample doesn't include this syntax, so the exact token layout is unverified. The data model and `generator_not_found` reason are in place; the parser will raise `ValueError` on an `OPEN GEN` line until a real sample is supplied and the parser branch is implemented.
- **Combined contingency actions** (e.g., open multiple branches in one statement). Each `OPEN …` line becomes its own seed; multi-line atomic contingencies are not modeled.
- **Re-emitting a cleaned `.mon` file.** Output is CSV only.
- **Owner-based filtering of neighborhood equipment.** Only the SC field on the flowgate is used.

## 10. Open Questions / Future Work

- Should the unresolved report include the line number from the original `.mon`? (Trivial to add later; not required for the first pass.)
- Should branches with `STAT=0` (out of service) be excluded from neighborhood expansion? Currently included — matches how PSS/E itself walks the topology.
- Eventually, expose `flowgate` as a CLI subcommand on the package itself? Not now — the user explicitly wants a standalone script.
