# RAW to RAWX Pipeline

> How `psse_model_util` converts a PSS/E RAW file into its internal RAWX-compatible data model.

---

## Background

PSS/E uses two file formats for power system models:

- **RAW** (`.raw`) — The legacy text-based format. Fixed-section, line-oriented, comma-delimited. Version-specific field layouts (v33, v34, v35).
- **RAWX** (`.rawx`) — The modern JSON format introduced in PSS/E v35. Self-describing: each section carries its own field names and data arrays.

`psse_model_util` uses RAWX as its **canonical internal format**. RAW files are converted to a RAWX-compatible Python dict at load time via `raw_to_rawx.py`. RAWX files are loaded directly via `common/json_util.py`. Both paths produce the same internal structure, so all downstream code (Model, Network, compare) works identically regardless of source format.

---

## Files Involved

| File | Role |
|------|------|
| `raw_to_rawx.py` | RAW parser — produces the rawx-compatible dict |
| `dataformat/rawx_raw_map.csv` | Field mapping table: RAW column names → RAWX field names (per version) |
| `dataformat/rawx_json_template.py` | RAWX section schema: field names, dtypes, index columns, bus columns |
| `common/json_util.py` | RAWX loader (JSON → dict) |
| `model.py` → `Network._create_dataframe()` | Converts rawx dict sections → typed, indexed pd.DataFrames |

---

## The rawx_raw_map.csv

This CSV is the heart of the RAW-to-RAWX translation. It maps every RAW field to its RAWX equivalent, with version-specific columns for v34 and v35.

### Schema

```
dataformat_pdf_section   — PSS/E documentation section reference
field_idx_raw_34         — Field position in RAW v34 data row
row_raw_34               — Row number within record (for multi-row records like TRANSFORMER)
section_raw_34           — RAW section name (e.g., "BUS DATA")
subsection_raw_34        — RAW subsection name
field_raw_34             — RAW field name (e.g., "I", "NAME", "BASKV")
field_idx_raw_35         — Field position in RAW v35
row_raw_35               — Row number in RAW v35
section_raw_35           — RAW v35 section name
subsection_raw_35        — RAW v35 subsection name
field_raw_35             — RAW v35 field name
field_id_rawx            — Numeric RAWX field ID
section_rawx             — RAWX section name (e.g., "bus", "acline")
field_rawx               — RAWX field name (e.g., "ibus", "name", "baskv")
inch_section             — INCH section (for future IDEV export)
inch_field               — INCH field name
notes                    — Human-readable description
```

### How version selection works

At parse time, `_get_raw_rawx_columns()` reads the full CSV and drops the columns for the version that does *not* match the file being parsed:

```python
suffix_to_drop = '34' if version >= 35 else '35'
df.drop(columns=[col for col in df.columns if col.endswith(suffix_to_drop)], inplace=True)
df.rename(columns=lambda col: col.rstrip('_34').rstrip('_35'), inplace=True)
```

After this, the working DataFrame has generic names (`section_raw`, `subsection_raw`, `field_raw`, `field_rawx`, `field_idx_raw`) regardless of whether the source was v34 or v35.

### Section name mapping

`_get_section_map()` extracts a deduplicated 3-column view for section-level routing:

```
section_raw      | subsection_raw           | section_rawx
-----------------|--------------------------|-------------
BUS DATA         | BUS DATA                 | bus
BRANCH DATA      | BRANCH DATA              | acline
TRANSFORMER DATA | TRANSFORMER DATA         | transformer
LOAD DATA        | LOAD DATA                | load
GENERATOR DATA   | GENERATOR DATA           | generator
SUBSTATION       | SUBSTATION DATA BLOCK    | substation
...
```

`_raw_to_rawx_section_name(section_raw, subsection_raw)` does the lookup.

---

## Parsing Flow: Step by Step

### 1. File open and version detection

```python
with io.open(str(raw_filepath), encoding="latin-1") as file:
    f = file.readlines()
```

- Encoding: `latin-1` (RAW files use extended ASCII)
- Line 1: `@!IC, SBASE, REV, ...` — column headers for case identification
- Line 2: `<values> / PSS(R)E-34 <title>` — version number extracted here
- Line 5+: `GENERAL, THRSHZ=..., ...` — system-wide settings begin

Version extracted:
```python
version = float(f[1].split('/ PSS(R)E-', 1)[1].strip().split(' ', 1)[0])
```

### 2. Load field mapping for this version

```python
raw_rawx_columns = _get_raw_rawx_columns(filepath=RAW_RAWX_MAP_CSV, version=version)
```

Returns a DataFrame with columns: `section_raw`, `subsection_raw`, `field_raw`, `field_rawx`, `field_idx_raw`, `row_raw` — filtered and renamed for the detected version.

### 3. Case identification (lines 1–2)

```python
result['network']['caseid'] = _read_caseid(f[1])
```

Fields: `ic, sbase, rev, xfrrat, nxfrat, basfrq, title1, title2`

Output format: `{'fields': [...], 'data': [...]}` — same structure as all other RAWX sections.

### 4. System-wide data

```python
syswide = _read_syswide(f[syswide_line_num: end_syswide_line_num])
result['network'].update(syswide)
```

Handles: `GENERAL`, `GAUSS`, `NEWTON`, `ADJUST`, `TYSL`, `SOLVER`, `RATING` records.

Each becomes a subsection in `result['network']` with RAWX-compatible `{'fields': [...], 'data': [...]}` structure.

### 5. Network section parsing (main loop)

The parser reads line by line from the end of system-wide data to `Q` (end of file).

**Line type classification** (`_PATTERNS` dict — regex):

| Pattern name | Matches |
|---|---|
| `section_divider` | `0 / END OF BUS DATA` etc. |
| `column_names` | `@! I, NAME, BASKV, ...` |
| `data` | Any comma-delimited data row |
| `substation_subsection` | `@! BEGIN SUBSTATION ...` |
| `gne` / `gne_special` | GNE section |
| `eof` | `Q` |

**On `section_divider`:**
1. Flush accumulated data for the previous section into `result['network']`
2. Extract new section name from the line
3. Map to RAWX section name via `_raw_to_rawx_section_name()`
4. Call `_get_column_names()` to build the RAW→RAWX column mapping for this section

**On `data`:** parse with `split_csv_line()`, pad to column count, append to `data` list (or accumulate for multi-row records).

**On `eof`:** break.

### 6. Column name resolution: `_get_column_names()`

```python
raw_rawx_column_names, raw_column_names = _get_column_names(
    subsection_raw_value=section,
    raw_rawx_columns_df=raw_rawx_columns
)
rawx_column_names = [pair[1] for pair in raw_rawx_column_names]
```

Returns ordered `(field_raw, field_rawx)` tuples for the section, sorted by `field_idx_raw`. For multi-row sections, returns a `list[list[str]]` — one list per row within the record.

### 7. Multi-row records

Some PSS/E sections have multiple lines per logical record:

| Section | Lines per record |
|---------|-----------------|
| TRANSFORMER DATA | 4 (2-winding) or 5 (3-winding) |
| TWO-TERMINAL DC DATA | 3 |
| VSC DC LINE DATA | 2 |
| MULTI-TERMINAL DC DATA | 4 |
| GNE DATA | 5 |

For TRANSFORMER DATA, winding count is detected from field `k` in row 1: `k == '0'` → 2-winding (4 rows); otherwise → 3-winding (5 rows).

All rows for a record are accumulated into `record_data`, then appended to `data` as a single flat list when the last row is reached.

### 8. Substation section

Substations have a unique nested structure parsed by `_parse_substation_section()`. Returns a dict with three keys (`substations`, `nodes`, `switching_devices`) instead of the standard `{'fields': ..., 'data': ...}` format. Substations are excluded from the NetworkX graph.

### 9. CSV line parsing: `split_csv_line()`

All data rows are parsed by `split_csv_line()`, which handles quoted strings, ignores commas inside quotes, and strips whitespace/quotes from each value.

---

## Output Structure

After parsing, `raw_file_to_rawx_dict()` returns:

```python
{
  'general': {
    'version': 34.0
  },
  'network': {
    'caseid':    {'fields': ['ic', 'sbase', 'rev', ...], 'data': ['0', '100.0', '34', ...]},
    'general':   {'fields': ['thrshz', 'pqbrak', 'blowup'], 'data': ['0.0001', '0.7', '1000.0']},
    'bus':       {'fields': ['ibus', 'name', 'baskv', 'ide', 'area', ...], 'data': [[1, 'BUS1', 345.0, ...], ...]},
    'acline':    {'fields': ['ibus', 'jbus', 'ckt', 'r', 'x', 'b', ...], 'data': [[...], ...]},
    'generator': {'fields': ['ibus', 'id', 'pg', 'qg', ...], 'data': [[...], ...]},
    'transformer': {...},
    ...
  }
}
```

This dict is consumed by `Model.__init__()` → `Network.__init__()` → `_create_dataframe()` to build typed, indexed DataFrames with metadata.

---

## From Dict to DataFrame: `Network._create_dataframe()`

For each subsection:

1. Pop `fields` and `data` from the dict
2. Look up the subsection in `rawx_json_template` to get `data_type`, `id_cols`, `bus_cols`
3. Pad short rows: `row + [None] * (len(fields) - len(row))`
4. Build `pd.DataFrame(data, columns=fields)`
5. Coerce dtypes: `convert_df_column_dtypes(df, new_dtypes, default_types=(int, float, str))`
6. Set index: `df.set_index(id_cols)` (e.g., `ibus` for bus; `ibus, jbus, ckt` for acline)
7. Attach metadata: `df._metadata = {'data_type': ..., 'id_cols': ..., 'bus_cols': ...}`

---

## Caching

Parsing large RAW files (MMWG/IDC scale — tens of thousands of buses) takes time. `Model` automatically caches to/from pickle:

- Cache path: `site_cache_dir / "<raw_stem>.model"`
- On load: if cache exists and `force_recalculate=False` → skip parsing, load pickle
- On first parse: write pickle after building all DataFrames

---

## RAWX Export (Known Bug)

`save_rawx_dict_to_json()` in `raw_to_rawx.py` writes the internal dict back to JSON. The output does not currently reload correctly in PSS/E — there is a small format difference. Known low-priority bug tracked for Phase 2.1.

---

## Sequence Diagram

```
caller
  │
  ├─ Model("file.raw")
  │     │
  │     ├─ _read_json()
  │     │     │
  │     │     └─ raw_file_to_rawx_dict("file.raw")
  │     │           │
  │     │           ├─ open(file, "latin-1")
  │     │           ├─ detect version from line 2
  │     │           ├─ _get_raw_rawx_columns(CSV, version)   ← rawx_raw_map.csv
  │     │           ├─ _read_caseid(line 2)
  │     │           ├─ _read_syswide(lines 5..N)
  │     │           └─ main loop (section_divider / data / eof)
  │     │                 ├─ _raw_to_rawx_section_name()     ← rawx_raw_map.csv
  │     │                 ├─ _get_column_names()             ← rawx_raw_map.csv
  │     │                 └─ split_csv_line()
  │     │
  │     └─ Network.__init__(result['network'])
  │           └─ for each subsection:
  │                 _create_dataframe(data)
  │                       ├─ rawx_json_template lookup
  │                       ├─ pd.DataFrame(data, columns=fields)
  │                       ├─ convert_df_column_dtypes()
  │                       ├─ df.set_index(id_cols)
  │                       └─ df._metadata = {...}
  │
  └─ model.network.bus  →  typed pd.DataFrame
```
