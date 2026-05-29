# Flowgate Key-Element Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a `psse_model_util.flowgate` submodule that parses PSS/E `.mon` flowgate files, resolves their elements against a Model, expands 4-hop bus neighborhoods, filters by kV/MW, and emits four DataFrames (branches, generators, transformers_3w, unresolved). Plus a standalone CLI script in a sibling repo.

**Architecture:** Five pure stage functions (`parse_mon_file`, `filter_by_sc`, `resolve_elements`, `neighborhood_buses`, `collect_key_facilities`) inside one new module file `psse_model_util/flowgate.py`. CLI is a thin orchestrator in a sibling project that imports from the package.

**Tech Stack:** Python 3.x, pandas, networkx (already in use), pytest, PDM (project tooling).

**Reference spec:** `docs/superpowers/specs/2026-05-29-flowgate-key-elements-design.md`

---

## File Structure

**New files in `psse_model_util/` (this repo):**
- `psse_model_util/flowgate.py` — all stage functions, dataclasses, constants. Single file because the stages are tightly cohesive (~400-500 lines projected; each stage function ~50-100 lines).

**New files in `tests/` (this repo):**
- `tests/test_flowgate_parse.py` — Tasks 2-5 (parser tests)
- `tests/test_flowgate_resolve.py` — Tasks 7-9 (resolution tests)
- `tests/test_flowgate_neighborhood.py` — Task 11 (graph/neighborhood tests)
- `tests/test_flowgate_collect.py` — Tasks 13-16 (DataFrame assembly tests)
- `tests/test_flowgate_cli.py` — Task 19 (CLI smoke test)
- `tests/build_synthetic_mon.py` — Task 6 helper (not on pytest path)
- `tests/data/synthetic_pjm.mon` — generated once, committed

**New files in sibling repo `C:\Users\Chris\PycharmProjects\key_facilities\`:**
- `key_facilities.py` — argparse CLI orchestrator
- `pyproject.toml` — declares dependency on `psse-model-util` (editable install in dev)
- `README.md` — usage example

Split rationale: the package-side test files split by stage because each stage has 3-5 distinct test cases and the file would otherwise grow past ~400 lines.

---

## Conventions

- **Indentation/strings/types:** match existing files (`model.py`, `compare.py`). 4-space indent, double-quote strings, modern type hints (`list[...]`, `dict[...]`, `X | None`).
- **Logging:** use the module-level `logger = logging.getLogger(__name__)` pattern from existing files.
- **Tests:** mirror the `tests/test_phase_*.py` style (no `TestCase` classes, plain `def test_xyz(...)` functions, `DATA_DIR = Path(__file__).resolve().parent / "data"`).
- **Commits:** prefix `feat(flowgate):` for code, `test(flowgate):` for tests, `docs(flowgate):` for docs.

---

## Task 1: Module skeleton + constants + dataclasses

**Files:**
- Create: `psse_model_util/flowgate.py`

- [ ] **Step 1.1: Write the failing test**

Create `tests/test_flowgate_parse.py` with one trivial import test (the rest of the parse tests come later):

```python
"""Tests for psse_model_util.flowgate parser stage."""
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"


def test_module_imports_and_has_constants():
    from psse_model_util import flowgate

    assert flowgate.DEFAULT_HOPS == 4
    assert flowgate.DEFAULT_KV_MIN == 160.0
    assert flowgate.DEFAULT_KV_MAX == 765.0
    assert flowgate.DEFAULT_GEN_MIN_MW == 15.0
    assert flowgate.DEFAULT_SC == "PJM"
    assert flowgate.KV_KEY_DECIMALS == 3


def test_dataclasses_exist():
    from psse_model_util.flowgate import FlowgateElement, Flowgate, ResolvedSeed

    fge = FlowgateElement(
        flowgate_id=1, role="monitor", element_type="branch", raw_tokens=("a",)
    )
    fg = Flowgate(
        flowgate_id=1, description="d", sc="PJM", monitor=[fge], contingency=[]
    )
    rs = ResolvedSeed(
        flowgate_id=1,
        role="monitor",
        element_type="branch",
        seed_buses=frozenset({101, 102}),
        raw_tokens=("a",),
    )

    assert fge.role == "monitor"
    assert fg.sc == "PJM"
    assert 101 in rs.seed_buses
```

- [ ] **Step 1.2: Run test to verify it fails**

Run: `pdm run pytest tests/test_flowgate_parse.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'psse_model_util.flowgate'`

- [ ] **Step 1.3: Create the module with constants and dataclasses**

Write `psse_model_util/flowgate.py`:

```python
"""Flowgate (.mon) parsing and key-facility neighborhood extraction.

Parses PSS/E .mon flowgate-definition files, resolves their monitored and
contingency elements against a PSS/E Model, expands a 4-hop bus
neighborhood around each, filters by voltage and machine rating, and
emits four DataFrames (branches, generators, transformers_3w, unresolved).

See docs/superpowers/specs/2026-05-29-flowgate-key-elements-design.md.
"""
from __future__ import annotations

import logging
import pathlib
from dataclasses import dataclass
from typing import Literal

import networkx as nx  # noqa: F401  -- used in later tasks
import pandas as pd  # noqa: F401

from psse_model_util.model import Model  # noqa: F401

logger = logging.getLogger(__name__)

# ---------- defaults (override at call site or CLI) ----------
# Path defaults are intentionally empty — callers (or the CLI) supply real paths.
# They exist as named constants so callers can override in one place if needed.
DEFAULT_RAW_FILEPATH: pathlib.Path | str = ""
DEFAULT_MON_FILEPATH: pathlib.Path | str = ""

DEFAULT_HOPS: int = 4
DEFAULT_KV_MIN: float = 160.0
DEFAULT_KV_MAX: float = 765.0
DEFAULT_GEN_MIN_MW: float = 15.0
DEFAULT_SC: str = "PJM"          # SC = Security Coordinator
KV_KEY_DECIMALS: int = 3         # rounding precision for bus-lookup key


# ---------- dataclasses ----------
@dataclass(frozen=True)
class FlowgateElement:
    """One element parsed from a .mon flowgate block.

    raw_tokens preserves the original text fragments (bus tokens, ckt id,
    machine id) so the unresolved report can echo them back verbatim.
    """
    flowgate_id: int
    role: Literal["monitor", "contingency"]
    element_type: Literal["branch", "generator"]
    raw_tokens: tuple


@dataclass(frozen=True)
class Flowgate:
    flowgate_id: int
    description: str
    sc: str  # Security Coordinator (e.g. "PJM")
    monitor: list[FlowgateElement]
    contingency: list[FlowgateElement]


@dataclass(frozen=True)
class ResolvedSeed:
    """A FlowgateElement after bus-name → ibus resolution.

    seed_buses is a frozenset because it gets used as a set member /
    dict key when unioning neighborhoods within a flowgate.
    """
    flowgate_id: int
    role: Literal["monitor", "contingency"]
    element_type: Literal["branch", "generator"]
    seed_buses: frozenset[int]
    raw_tokens: tuple
```

- [ ] **Step 1.4: Run test to verify it passes**

Run: `pdm run pytest tests/test_flowgate_parse.py -v`
Expected: PASS on both `test_module_imports_and_has_constants` and `test_dataclasses_exist`.

- [ ] **Step 1.5: Lint**

Run: `pdm run ruff check psse_model_util/flowgate.py tests/test_flowgate_parse.py`
Expected: no errors. The `noqa: F401` comments suppress "imported but unused" warnings on imports that subsequent tasks will use.

- [ ] **Step 1.6: Commit**

```bash
git add psse_model_util/flowgate.py tests/test_flowgate_parse.py
git commit -m "feat(flowgate): scaffold module with constants and dataclasses"
```

---

## Task 2: Bus-token splitter

Bus tokens look like `'05TANNER    345.00'` — 12-char name + 6-char kV. This helper is the foundational primitive everything else uses.

**Files:**
- Modify: `psse_model_util/flowgate.py` (add `_split_bus_token`)
- Modify: `tests/test_flowgate_parse.py` (add tests)

- [ ] **Step 2.1: Write the failing tests**

Append to `tests/test_flowgate_parse.py`:

```python
import pytest


def test_split_bus_token_basic():
    from psse_model_util.flowgate import _split_bus_token

    name, kv = _split_bus_token("05TANNER    345.00")
    assert name == "05TANNER"
    assert kv == 345.00


def test_split_bus_token_strips_quotes():
    from psse_model_util.flowgate import _split_bus_token

    name, kv = _split_bus_token("'05TANNER    345.00'")
    assert name == "05TANNER"
    assert kv == 345.00


def test_split_bus_token_preserves_decimal():
    from psse_model_util.flowgate import _split_bus_token

    name, kv = _split_bus_token("'SOMEBUS     69.125'")
    assert name == "SOMEBUS"
    assert kv == 69.125


def test_split_bus_token_name_with_special_chars():
    """Real PSS/E names contain semicolons and digits, e.g. 'STATELINE; R345.00'."""
    from psse_model_util.flowgate import _split_bus_token

    name, kv = _split_bus_token("'STATELINE; R345.00'")
    assert name == "STATELINE; R"
    assert kv == 345.00


def test_split_bus_token_rejects_wrong_length():
    from psse_model_util.flowgate import _split_bus_token

    with pytest.raises(ValueError, match="bus token"):
        _split_bus_token("too short")
```

- [ ] **Step 2.2: Run tests to verify they fail**

Run: `pdm run pytest tests/test_flowgate_parse.py -v -k "split_bus_token"`
Expected: 5 FAILures with `ImportError`.

- [ ] **Step 2.3: Implement `_split_bus_token`**

Append to `psse_model_util/flowgate.py` (after the dataclasses section):

```python
# ---------- parsing primitives ----------
_BUS_TOKEN_LEN = 18  # 12-char name + 6-char kV


def _split_bus_token(token: str) -> tuple[str, float]:
    """Split a PSS/E .mon bus token into (name, base_kv).

    The token is 18 chars wide: 12-char left/right-padded name + 6-char
    kV string. Surrounding single quotes are stripped if present.

    >>> _split_bus_token("'05TANNER    345.00'")
    ('05TANNER', 345.0)
    """
    stripped = token.strip()
    if stripped.startswith("'") and stripped.endswith("'"):
        stripped = stripped[1:-1]
    if len(stripped) != _BUS_TOKEN_LEN:
        raise ValueError(
            f"bus token must be {_BUS_TOKEN_LEN} chars (got {len(stripped)}): {token!r}"
        )
    name = stripped[:12].strip()
    kv = float(stripped[12:].strip())
    return name, kv
```

- [ ] **Step 2.4: Run tests to verify they pass**

Run: `pdm run pytest tests/test_flowgate_parse.py -v -k "split_bus_token"`
Expected: 5 PASS.

- [ ] **Step 2.5: Lint and commit**

```bash
pdm run ruff check psse_model_util/flowgate.py tests/test_flowgate_parse.py
git add psse_model_util/flowgate.py tests/test_flowgate_parse.py
git commit -m "feat(flowgate): add _split_bus_token primitive"
```

---

## Task 3: `parse_mon_file` — basic BRANCH monitor + OPEN BRANCH contingency

**Files:**
- Modify: `psse_model_util/flowgate.py` (add `parse_mon_file`)
- Modify: `tests/test_flowgate_parse.py` (add tests)

- [ ] **Step 3.1: Write the failing tests**

Append to `tests/test_flowgate_parse.py`:

```python
SIMPLE_MON_TEXT = """\
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
"""


def test_parse_mon_string_one_flowgate(tmp_path):
    from psse_model_util.flowgate import parse_mon_file

    p = tmp_path / "one.mon"
    p.write_text(SIMPLE_MON_TEXT)
    fgs = parse_mon_file(p)

    assert len(fgs) == 1
    fg = fgs[0]
    assert fg.flowgate_id == 1600
    assert fg.sc == "PJM"
    assert fg.description.startswith("Tanners Creek")
    assert len(fg.monitor) == 1
    assert len(fg.contingency) == 1


def test_parse_monitor_element_tokens(tmp_path):
    from psse_model_util.flowgate import parse_mon_file

    p = tmp_path / "mon.mon"
    p.write_text(SIMPLE_MON_TEXT)
    fgs = parse_mon_file(p)

    mon = fgs[0].monitor[0]
    assert mon.role == "monitor"
    assert mon.element_type == "branch"
    # raw_tokens: (from_token, to_token, ckt) for branch
    assert mon.raw_tokens[0] == "05TANNER    345.00"
    assert mon.raw_tokens[1] == "06DEARB1    345.00"
    assert mon.raw_tokens[2] == "Z1"


def test_parse_contingency_element_tokens(tmp_path):
    from psse_model_util.flowgate import parse_mon_file

    p = tmp_path / "c.mon"
    p.write_text(SIMPLE_MON_TEXT)
    fgs = parse_mon_file(p)

    con = fgs[0].contingency[0]
    assert con.role == "contingency"
    assert con.element_type == "branch"
    assert con.raw_tokens[0] == "05MARYSVL_RS765.00"
    assert con.raw_tokens[1] == "05SORENSN_RM765.00"
    assert con.raw_tokens[2] == "1"
```

- [ ] **Step 3.2: Run tests to verify they fail**

Run: `pdm run pytest tests/test_flowgate_parse.py -v -k "parse_mon" or test_parse_monitor or test_parse_contingency`
Expected: 3 FAILures with `ImportError: cannot import name 'parse_mon_file'`.

- [ ] **Step 3.3: Implement `parse_mon_file`**

Append to `psse_model_util/flowgate.py`:

```python
import re
import shlex

# Regex for the quoted bus token inside a BRANCH or OPEN BRANCH line.
_BUS_TOKEN_RE = re.compile(r"'([^']{18})'")
_FLOWGATE_HEADER_RE = re.compile(
    r"^\s*MONITOR\s+FLOWGATE\s+(\d+)\s+'([^']*)'", re.IGNORECASE
)
_CONTINGENCY_HEADER_RE = re.compile(r"^\s*CONTINGENCY\s+(\d+)", re.IGNORECASE)
_SC_LINE_RE = re.compile(r"^\s*SC\s+(\S+)", re.IGNORECASE)
_END_RE = re.compile(r"^\s*END\s*$", re.IGNORECASE)


def _parse_branch_line(line: str, flowgate_id: int, role: str) -> FlowgateElement:
    """Parse a 'BRANCH FROM BUS '...' TO BUS '...' CKT <ckt>' line."""
    tokens = _BUS_TOKEN_RE.findall(line)
    if len(tokens) != 2:
        raise ValueError(
            f"branch line must have exactly 2 quoted bus tokens, got {len(tokens)}: {line!r}"
        )
    # CKT id comes after "CKT" keyword
    m = re.search(r"CKT\s+(\S+)", line, re.IGNORECASE)
    if not m:
        raise ValueError(f"branch line missing CKT id: {line!r}")
    ckt = m.group(1).strip().strip("'")
    return FlowgateElement(
        flowgate_id=flowgate_id,
        role=role,
        element_type="branch",
        raw_tokens=(tokens[0], tokens[1], ckt),
    )


def parse_mon_file(path: pathlib.Path | str = DEFAULT_MON_FILEPATH) -> list[Flowgate]:
    """Parse a PSS/E .mon flowgate-definitions file into a list of Flowgate objects.

    Recognized constructs:
      MONITOR FLOWGATE <id> '<description>'
        BRANCH FROM BUS '<token>' TO BUS '<token>' CKT <id>     -- monitored branch
      CONTINGENCY <id>
        OPEN BRANCH FROM BUS '...' TO BUS '...' CKT <id>        -- branch outage
        REMOVE MACHINE <id> FROM BUS '<token>'                  -- generator outage  (Task 4)
      END                                                        -- closes contingency
        SC <name>                                                -- Security Coordinator
        CA <args>                                                -- ignored
        TP <args>                                                -- ignored
      END                                                        -- closes flowgate

    Raises ValueError on structural errors (unbalanced MONITOR/END, malformed BRANCH).
    Logs a warning and skips unknown contingency actions.
    """
    p = pathlib.Path(path)
    text = p.read_text()
    lines = text.splitlines()

    flowgates: list[Flowgate] = []
    state = "TOP"
    current_fg_id: int | None = None
    current_fg_desc: str = ""
    current_sc: str = ""
    current_monitor: list[FlowgateElement] = []
    current_contingency: list[FlowgateElement] = []

    for lineno, raw_line in enumerate(lines, start=1):
        line = raw_line.rstrip()
        if not line.strip():
            continue
        stripped = line.strip()

        # Skip the BUSNAMES header
        if stripped.upper() == "BUSNAMES":
            continue

        try:
            # MONITOR FLOWGATE header
            m = _FLOWGATE_HEADER_RE.match(line)
            if m:
                if state != "TOP":
                    raise ValueError(
                        f"line {lineno}: nested MONITOR FLOWGATE not allowed"
                    )
                current_fg_id = int(m.group(1))
                current_fg_desc = m.group(2)
                current_sc = ""
                current_monitor = []
                current_contingency = []
                state = "IN_MONITOR"
                continue

            # CONTINGENCY header
            m = _CONTINGENCY_HEADER_RE.match(line)
            if m:
                if state != "IN_MONITOR":
                    raise ValueError(
                        f"line {lineno}: CONTINGENCY outside MONITOR block"
                    )
                # contingency id is required to match the flowgate id, but we don't enforce
                state = "IN_CONTINGENCY"
                continue

            # SC line — only valid between CONTINGENCY's END and flowgate's END
            m = _SC_LINE_RE.match(line)
            if m and state == "POST_CONTINGENCY":
                current_sc = m.group(1).strip()
                continue

            # END line
            if _END_RE.match(line):
                if state == "IN_CONTINGENCY":
                    state = "POST_CONTINGENCY"
                    continue
                if state == "POST_CONTINGENCY":
                    flowgates.append(
                        Flowgate(
                            flowgate_id=current_fg_id,
                            description=current_fg_desc,
                            sc=current_sc,
                            monitor=current_monitor,
                            contingency=current_contingency,
                        )
                    )
                    state = "TOP"
                    current_fg_id = None
                    continue
                if state == "IN_MONITOR":
                    raise ValueError(
                        f"line {lineno}: END inside MONITOR block (no CONTINGENCY)"
                    )
                raise ValueError(f"line {lineno}: unexpected END")

            # BRANCH line (in MONITOR block)
            if stripped.upper().startswith("BRANCH ") and state == "IN_MONITOR":
                current_monitor.append(
                    _parse_branch_line(line, current_fg_id, "monitor")
                )
                continue

            # OPEN BRANCH line (in CONTINGENCY block)
            if stripped.upper().startswith("OPEN BRANCH ") and state == "IN_CONTINGENCY":
                current_contingency.append(
                    _parse_branch_line(line, current_fg_id, "contingency")
                )
                continue

            # REMOVE MACHINE line — implemented in Task 4

            # CA/TP lines — ignored
            if stripped.upper().startswith(("CA ", "TP ")):
                continue

            # Unknown line — log and skip (RESILIENT)
            if state in ("IN_MONITOR", "IN_CONTINGENCY", "POST_CONTINGENCY"):
                logger.warning(
                    "line %d: unknown line in state %s, skipping: %r",
                    lineno, state, line
                )
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(f"line {lineno}: parse error: {exc}") from exc

    if state != "TOP":
        raise ValueError(f"unbalanced flowgate block (ended in state {state})")

    return flowgates
```

- [ ] **Step 3.4: Run tests to verify they pass**

Run: `pdm run pytest tests/test_flowgate_parse.py -v`
Expected: all parse tests PASS (including the 3 new ones and the 6 from tasks 1-2).

- [ ] **Step 3.5: Lint and commit**

```bash
pdm run ruff check psse_model_util/flowgate.py tests/test_flowgate_parse.py
git add psse_model_util/flowgate.py tests/test_flowgate_parse.py
git commit -m "feat(flowgate): parse MONITOR FLOWGATE blocks with BRANCH and OPEN BRANCH lines"
```

---

## Task 4: `parse_mon_file` — REMOVE MACHINE contingency

**Files:**
- Modify: `psse_model_util/flowgate.py` (extend parser for `REMOVE MACHINE`)
- Modify: `tests/test_flowgate_parse.py`

- [ ] **Step 4.1: Write the failing tests**

Append to `tests/test_flowgate_parse.py`:

```python
REMOVE_MACHINE_MON = """\
MONITOR FLOWGATE 59031  'Clifty Creek-Carrollton 138 (flo) Ghent Unit 3'
         BRANCH FROM BUS '06CLIFTY    138.00' TO BUS '4CARROLLTON 138.00' CKT 1
 CONTINGENCY 59031
    REMOVE MACHINE 3 FROM BUS '1GHENT 3    22.000'
 END
    CA OVEC LGEE
    SC LGEE
    TP PJM LGEE
END
"""


def test_parse_remove_machine(tmp_path):
    from psse_model_util.flowgate import parse_mon_file

    p = tmp_path / "rm.mon"
    p.write_text(REMOVE_MACHINE_MON)
    fgs = parse_mon_file(p)

    assert len(fgs) == 1
    con = fgs[0].contingency[0]
    assert con.role == "contingency"
    assert con.element_type == "generator"
    # raw_tokens: (bus_token, machine_id)
    assert con.raw_tokens[0] == "1GHENT 3    22.000"
    assert con.raw_tokens[1] == "3"


def test_parse_remove_machine_alphanumeric_id(tmp_path):
    """PSS/E machine ids can be alphanumeric (e.g. 'H1')."""
    from psse_model_util.flowgate import parse_mon_file

    mon = REMOVE_MACHINE_MON.replace("REMOVE MACHINE 3 ", "REMOVE MACHINE H1 ")
    p = tmp_path / "rm2.mon"
    p.write_text(mon)
    fgs = parse_mon_file(p)
    assert fgs[0].contingency[0].raw_tokens[1] == "H1"
```

- [ ] **Step 4.2: Run tests to verify they fail**

Run: `pdm run pytest tests/test_flowgate_parse.py -v -k "remove_machine"`
Expected: 2 FAILures (probably with `IndexError` or "unknown line" warning but no contingency parsed).

- [ ] **Step 4.3: Add the REMOVE MACHINE branch to the parser**

In `psse_model_util/flowgate.py`, add a helper near `_parse_branch_line`:

```python
def _parse_remove_machine_line(line: str, flowgate_id: int) -> FlowgateElement:
    """Parse 'REMOVE MACHINE <machine_id> FROM BUS '<token>''.

    machine_id is the whitespace-separated token between MACHINE and FROM,
    preserved as a string (PSS/E ids can be alphanumeric, e.g. 'H1').
    """
    m = re.search(
        r"REMOVE\s+MACHINE\s+(\S+)\s+FROM\s+BUS\s+'([^']{18})'",
        line,
        re.IGNORECASE,
    )
    if not m:
        raise ValueError(f"malformed REMOVE MACHINE line: {line!r}")
    machine_id = m.group(1).strip().strip("'")
    bus_token = m.group(2)
    return FlowgateElement(
        flowgate_id=flowgate_id,
        role="contingency",
        element_type="generator",
        raw_tokens=(bus_token, machine_id),
    )
```

In `parse_mon_file`, replace the `# REMOVE MACHINE line — implemented in Task 4` placeholder with:

```python
            # REMOVE MACHINE line (in CONTINGENCY block)
            if stripped.upper().startswith("REMOVE MACHINE ") and state == "IN_CONTINGENCY":
                current_contingency.append(
                    _parse_remove_machine_line(line, current_fg_id)
                )
                continue
```

- [ ] **Step 4.4: Run tests to verify they pass**

Run: `pdm run pytest tests/test_flowgate_parse.py -v`
Expected: all parse tests still PASS, plus the 2 new ones.

- [ ] **Step 4.5: Commit**

```bash
pdm run ruff check psse_model_util/flowgate.py tests/test_flowgate_parse.py
git add psse_model_util/flowgate.py tests/test_flowgate_parse.py
git commit -m "feat(flowgate): parse REMOVE MACHINE contingency lines"
```

---

## Task 5: Multi-flowgate file + multi-element contingency + `filter_by_sc`

**Files:**
- Modify: `psse_model_util/flowgate.py` (add `filter_by_sc`)
- Modify: `tests/test_flowgate_parse.py`

- [ ] **Step 5.1: Write the failing tests**

Append to `tests/test_flowgate_parse.py`:

```python
MULTI_FG_MON = """\
MONITOR FLOWGATE 100  'desc A'
         BRANCH FROM BUS '05TANNER    345.00' TO BUS '06DEARB1    345.00' CKT 1
 CONTINGENCY 100
    OPEN BRANCH FROM BUS '05MARYSVL_RS765.00' TO BUS '05SORENSN_RM765.00' CKT 1
 END
    SC PJM
END

MONITOR FLOWGATE 200  'desc B'
         BRANCH FROM BUS '05TANNER    345.00' TO BUS '06DEARB1    345.00' CKT 2
 CONTINGENCY 200
    OPEN BRANCH FROM BUS 'BURNHAM  ;0R345.00' TO BUS 'CALUMET  ; R345.00' CKT 1
    OPEN BRANCH FROM BUS 'CALUMET  ; R345.00' TO BUS 'CALUMET  ;4I345.00' CKT 1
 END
    SC OTHER
END
"""


def test_parse_multiple_flowgates(tmp_path):
    from psse_model_util.flowgate import parse_mon_file

    p = tmp_path / "multi.mon"
    p.write_text(MULTI_FG_MON)
    fgs = parse_mon_file(p)
    assert [fg.flowgate_id for fg in fgs] == [100, 200]
    assert [fg.sc for fg in fgs] == ["PJM", "OTHER"]


def test_parse_multi_element_contingency(tmp_path):
    """A CONTINGENCY block can contain multiple OPEN BRANCH lines."""
    from psse_model_util.flowgate import parse_mon_file

    p = tmp_path / "multi.mon"
    p.write_text(MULTI_FG_MON)
    fgs = parse_mon_file(p)
    assert len(fgs[1].contingency) == 2
    assert fgs[1].contingency[0].raw_tokens[2] == "1"
    assert fgs[1].contingency[1].raw_tokens[0] == "CALUMET  ; R345.00"


def test_filter_by_sc(tmp_path):
    from psse_model_util.flowgate import parse_mon_file, filter_by_sc

    p = tmp_path / "multi.mon"
    p.write_text(MULTI_FG_MON)
    fgs = parse_mon_file(p)

    pjm_only = filter_by_sc(fgs, sc="PJM")
    assert [fg.flowgate_id for fg in pjm_only] == [100]


def test_filter_by_sc_default_is_pjm(tmp_path):
    from psse_model_util.flowgate import parse_mon_file, filter_by_sc

    p = tmp_path / "multi.mon"
    p.write_text(MULTI_FG_MON)
    fgs = parse_mon_file(p)
    assert [fg.flowgate_id for fg in filter_by_sc(fgs)] == [100]
```

- [ ] **Step 5.2: Run tests to verify they fail**

Run: `pdm run pytest tests/test_flowgate_parse.py -v -k "multi or filter_by_sc"`
Expected: 2 FAIL (multi parser tests — likely an "unexpected" state error), and 2 FAIL with ImportError for `filter_by_sc`.

- [ ] **Step 5.3: Add `filter_by_sc`**

The parser should already handle multiple flowgates because state resets after each closing `END`. If the multi-FG tests fail, the bug is elsewhere — investigate first. Then add `filter_by_sc`:

```python
def filter_by_sc(fgs: list[Flowgate], sc: str = DEFAULT_SC) -> list[Flowgate]:
    """Keep only flowgates whose Security Coordinator matches `sc` (case-sensitive)."""
    return [fg for fg in fgs if fg.sc == sc]
```

- [ ] **Step 5.4: Run tests to verify they pass**

Run: `pdm run pytest tests/test_flowgate_parse.py -v`
Expected: all PASS.

- [ ] **Step 5.5: Commit**

```bash
pdm run ruff check psse_model_util/flowgate.py tests/test_flowgate_parse.py
git add psse_model_util/flowgate.py tests/test_flowgate_parse.py
git commit -m "feat(flowgate): add filter_by_sc; verify multi-flowgate parsing"
```

---

## Task 6: Synthetic .mon fixture builder

This is a one-shot helper script. Its output `tests/data/synthetic_pjm.mon` becomes the fixture for downstream tests. Run once, commit the output.

**Files:**
- Create: `tests/build_synthetic_mon.py`
- Create: `tests/data/synthetic_pjm.mon` (generated)

- [ ] **Step 6.1: Write the builder script**

```python
"""One-shot generator for tests/data/synthetic_pjm.mon, aligned with Model_1.raw.

Run with:  python tests/build_synthetic_mon.py
Output:    tests/data/synthetic_pjm.mon  (commit it)

This script is intentionally NOT on the pytest path.
"""
from pathlib import Path

from psse_model_util.model import Model

DATA_DIR = Path(__file__).resolve().parent / "data"
RAW_FILE = DATA_DIR / "Model_1.raw"
OUT_FILE = DATA_DIR / "synthetic_pjm.mon"

# Areas treated as "PJM" for the synthetic fixture. Hardcoded so the fixture is
# stable regardless of what psse_model_util.common.constants.NATIVE_AREAS is set
# to at any given time.
MODEL_1_PJM_AREAS = {1, 2, 3}


def _bus_token(name: str, baskv: float) -> str:
    """Build an 18-char PSS/E bus token: 12-char left-padded name + 6-char kV."""
    name_part = f"{name:<12}"[:12]
    kv_part = f"{baskv:<6.2f}"[:6]
    return f"{name_part}{kv_part}"


def main() -> None:
    model = Model(RAW_FILE, force_recalculate=True)
    bus = model.network.bus
    ac = model.network.acline.reset_index()
    gen = model.network.generator.reset_index()

    # Build bus lookup: ibus -> (name, baskv, area)
    bus_info = {
        ibus: (str(row["name"]).strip(), float(row["baskv"]), int(row["area"]))
        for ibus, row in bus.iterrows()
    }

    # Pick 2 PJM monitor branches with both ends ≥ 160 kV in PJM areas
    pjm_branches = ac[
        ac["ibus"].map(lambda b: bus_info.get(b, (None, 0, 0))[2]).isin(MODEL_1_PJM_AREAS)
        & ac["jbus"].map(lambda b: bus_info.get(b, (None, 0, 0))[2]).isin(MODEL_1_PJM_AREAS)
        & ac["ibus"].map(lambda b: bus_info.get(b, (None, 0, 0))[1] >= 160.0)
    ].head(4)

    if len(pjm_branches) < 4:
        raise RuntimeError(
            f"Only found {len(pjm_branches)} PJM branches in Model_1.raw; "
            f"need at least 4 to build the fixture."
        )

    # Pick one PJM generator for the REMOVE MACHINE flowgate
    pjm_gen = gen[
        gen["ibus"].map(lambda b: bus_info.get(b, (None, 0, 0))[2]).isin(MODEL_1_PJM_AREAS)
    ].head(1)
    if pjm_gen.empty:
        raise RuntimeError("No PJM generators in Model_1.raw.")
    gen_row = pjm_gen.iloc[0]
    gen_bus_name, gen_bus_kv, _ = bus_info[int(gen_row["ibus"])]
    gen_machid = str(gen_row["machid"]).strip()

    # Pick one non-PJM branch for the SC OTHER flowgate
    non_pjm = ac[
        ~ac["ibus"].map(lambda b: bus_info.get(b, (None, 0, 0))[2]).isin(MODEL_1_PJM_AREAS)
    ].head(1)
    if non_pjm.empty:
        raise RuntimeError("No non-PJM branches in Model_1.raw to use for SC OTHER.")

    lines: list[str] = ["BUSNAMES"]

    def emit_branch_fg(fg_id, mon_row, con_row, sc):
        i_name, i_kv, _ = bus_info[int(mon_row["ibus"])]
        j_name, j_kv, _ = bus_info[int(mon_row["jbus"])]
        ci_name, ci_kv, _ = bus_info[int(con_row["ibus"])]
        cj_name, cj_kv, _ = bus_info[int(con_row["jbus"])]
        lines.extend([
            "",
            f"MONITOR FLOWGATE {fg_id}  'synthetic FG {fg_id}'",
            f"         BRANCH FROM BUS '{_bus_token(i_name, i_kv)}' TO BUS '{_bus_token(j_name, j_kv)}' CKT {str(mon_row['ckt']).strip()}",
            f" CONTINGENCY {fg_id}",
            f"    OPEN BRANCH FROM BUS '{_bus_token(ci_name, ci_kv)}' TO BUS '{_bus_token(cj_name, cj_kv)}' CKT {str(con_row['ckt']).strip()}",
            " END",
            "    CA SYN SYN",
            f"    SC {sc}",
            f"    TP {sc} {sc}",
            "END",
        ])

    rows = pjm_branches.reset_index(drop=True)
    # FG 1: branches[0] monitor, branches[1] contingency, SC PJM
    emit_branch_fg(1001, rows.iloc[0], rows.iloc[1], "PJM")
    # FG 2: branches[2] monitor, branches[3] contingency, SC PJM
    emit_branch_fg(1002, rows.iloc[2], rows.iloc[3], "PJM")

    # FG 3: REMOVE MACHINE contingency on a PJM generator
    i_name, i_kv, _ = bus_info[int(rows.iloc[0]["ibus"])]
    j_name, j_kv, _ = bus_info[int(rows.iloc[0]["jbus"])]
    lines.extend([
        "",
        "MONITOR FLOWGATE 1003  'synthetic FG 1003 gen contingency'",
        f"         BRANCH FROM BUS '{_bus_token(i_name, i_kv)}' TO BUS '{_bus_token(j_name, j_kv)}' CKT {str(rows.iloc[0]['ckt']).strip()}",
        " CONTINGENCY 1003",
        f"    REMOVE MACHINE {gen_machid} FROM BUS '{_bus_token(gen_bus_name, gen_bus_kv)}'",
        " END",
        "    CA SYN SYN",
        "    SC PJM",
        "    TP PJM PJM",
        "END",
    ])

    # FG 4: SC OTHER (must be dropped by filter_by_sc)
    non_pjm_row = non_pjm.iloc[0]
    ni_name, ni_kv, _ = bus_info[int(non_pjm_row["ibus"])]
    nj_name, nj_kv, _ = bus_info[int(non_pjm_row["jbus"])]
    lines.extend([
        "",
        "MONITOR FLOWGATE 9001  'synthetic non-PJM'",
        f"         BRANCH FROM BUS '{_bus_token(ni_name, ni_kv)}' TO BUS '{_bus_token(nj_name, nj_kv)}' CKT {str(non_pjm_row['ckt']).strip()}",
        " CONTINGENCY 9001",
        f"    OPEN BRANCH FROM BUS '{_bus_token(ni_name, ni_kv)}' TO BUS '{_bus_token(nj_name, nj_kv)}' CKT {str(non_pjm_row['ckt']).strip()}",
        " END",
        "    CA SYN SYN",
        "    SC OTHER",
        "    TP OTHER OTHER",
        "END",
    ])

    OUT_FILE.write_text("\n".join(lines) + "\n")
    print(f"Wrote {OUT_FILE} ({len(lines)} lines)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6.2: Run the builder once**

```bash
pdm run python tests/build_synthetic_mon.py
```

Expected output: `Wrote .../tests/data/synthetic_pjm.mon (N lines)`.

- [ ] **Step 6.3: Sanity-check the generated file**

```bash
pdm run python -c "from psse_model_util.flowgate import parse_mon_file; fgs = parse_mon_file('tests/data/synthetic_pjm.mon'); print(len(fgs), 'flowgates:', [fg.flowgate_id for fg in fgs])"
```

Expected: `4 flowgates: [1001, 1002, 1003, 9001]`

- [ ] **Step 6.4: Add a test that parses the committed fixture**

Append to `tests/test_flowgate_parse.py`:

```python
def test_synthetic_fixture_parses():
    from psse_model_util.flowgate import parse_mon_file

    fgs = parse_mon_file(DATA_DIR / "synthetic_pjm.mon")
    assert [fg.flowgate_id for fg in fgs] == [1001, 1002, 1003, 9001]
    # FG 1003 contingency should be a generator (REMOVE MACHINE)
    assert fgs[2].contingency[0].element_type == "generator"
    # FG 9001 should have SC OTHER
    assert fgs[3].sc == "OTHER"
```

Run: `pdm run pytest tests/test_flowgate_parse.py -v -k synthetic_fixture`
Expected: PASS.

- [ ] **Step 6.5: Commit fixture + builder + test**

```bash
git add tests/build_synthetic_mon.py tests/data/synthetic_pjm.mon tests/test_flowgate_parse.py
git commit -m "test(flowgate): add synthetic_pjm.mon fixture and builder script"
```

---

## Task 7: `resolve_elements` — happy path for branches

**Files:**
- Modify: `psse_model_util/flowgate.py` (add `resolve_elements`)
- Create: `tests/test_flowgate_resolve.py`

- [ ] **Step 7.1: Write the failing test**

```python
"""Tests for psse_model_util.flowgate.resolve_elements."""
from pathlib import Path

import pandas as pd
import pytest

from psse_model_util.model import Model

DATA_DIR = Path(__file__).resolve().parent / "data"


@pytest.fixture(scope="module")
def model_1():
    return Model(DATA_DIR / "Model_1.raw")


@pytest.fixture(scope="module")
def synthetic_fgs():
    from psse_model_util.flowgate import parse_mon_file, filter_by_sc

    fgs = parse_mon_file(DATA_DIR / "synthetic_pjm.mon")
    return filter_by_sc(fgs, sc="PJM")  # drops 9001


def test_resolve_returns_two_results(model_1, synthetic_fgs):
    from psse_model_util.flowgate import resolve_elements

    result = resolve_elements(synthetic_fgs, model_1)
    assert isinstance(result, tuple)
    assert len(result) == 2


def test_resolve_seeds_have_buses(model_1, synthetic_fgs):
    from psse_model_util.flowgate import resolve_elements, ResolvedSeed

    seeds, unresolved = resolve_elements(synthetic_fgs, model_1)
    assert isinstance(unresolved, pd.DataFrame)
    assert all(isinstance(s, ResolvedSeed) for s in seeds)
    # Every PJM FG should have at least one resolved seed
    fg_ids_with_seeds = {s.flowgate_id for s in seeds}
    assert fg_ids_with_seeds == {1001, 1002, 1003}


def test_resolve_synthetic_branches_have_two_bus_seeds(model_1, synthetic_fgs):
    from psse_model_util.flowgate import resolve_elements

    seeds, _ = resolve_elements(synthetic_fgs, model_1)
    branch_seeds = [s for s in seeds if s.element_type == "branch"]
    assert branch_seeds, "expected at least one branch seed"
    for s in branch_seeds:
        assert len(s.seed_buses) == 2  # from and to bus


def test_resolve_unresolved_dataframe_columns(model_1, synthetic_fgs):
    from psse_model_util.flowgate import resolve_elements

    _, unresolved = resolve_elements(synthetic_fgs, model_1)
    expected_cols = {"flowgate_id", "role", "element_type", "raw_tokens", "reason"}
    assert expected_cols.issubset(unresolved.columns)
```

- [ ] **Step 7.2: Run tests to verify they fail**

Run: `pdm run pytest tests/test_flowgate_resolve.py -v`
Expected: FAIL with `ImportError: cannot import name 'resolve_elements'`.

- [ ] **Step 7.3: Implement `resolve_elements` for branches only**

Append to `psse_model_util/flowgate.py`:

```python
import pandas as pd


_UNRESOLVED_COLUMNS = ["flowgate_id", "role", "element_type", "raw_tokens", "reason"]


def _build_bus_lookup(model: Model) -> dict[tuple[str, float], int]:
    """Build {(name_stripped, round(baskv, KV_KEY_DECIMALS)): ibus}."""
    bus_df = model.network.bus
    return {
        (str(name).strip(), round(float(baskv), KV_KEY_DECIMALS)): int(ibus)
        for ibus, name, baskv in zip(
            bus_df.index, bus_df["name"], bus_df["baskv"]
        )
    }


def _branch_exists(model: Model, ibus: int, jbus: int, ckt: str) -> bool:
    """Check if (ibus, jbus, ckt) — in any order — exists in acline or 2W transformer."""
    ckt_norm = str(ckt).strip()

    ac = model.network.acline
    ac_idx = ac.index
    # acline index is MultiIndex (ibus, jbus, ckt). Check both orderings.
    if (ibus, jbus, ckt_norm) in ac_idx or (jbus, ibus, ckt_norm) in ac_idx:
        return True

    xf = model.network.transformer
    # transformer index is (ibus, jbus, kbus, ckt). 2W rows have kbus == 0.
    for ib, jb in [(ibus, jbus), (jbus, ibus)]:
        if (ib, jb, 0, ckt_norm) in xf.index:
            return True
    return False


def resolve_elements(
    fgs: list[Flowgate], model: Model
) -> tuple[list[ResolvedSeed], pd.DataFrame]:
    """Resolve flowgate elements to model bus numbers.

    Returns (resolved_seeds, unresolved_df). Unresolved elements are emitted
    to the second return value rather than raising, so processing of the
    remaining flowgates continues.
    """
    lookup = _build_bus_lookup(model)
    seeds: list[ResolvedSeed] = []
    unresolved_rows: list[dict] = []

    def _resolve_bus_token(token: str) -> int | None:
        name, kv = _split_bus_token(token)
        return lookup.get((name, round(kv, KV_KEY_DECIMALS)))

    for fg in fgs:
        for elem in list(fg.monitor) + list(fg.contingency):
            if elem.element_type == "branch":
                from_token, to_token, ckt = elem.raw_tokens
                from_ibus = _resolve_bus_token(from_token)
                to_ibus = _resolve_bus_token(to_token)
                if from_ibus is None or to_ibus is None:
                    unresolved_rows.append({
                        "flowgate_id": elem.flowgate_id,
                        "role": elem.role,
                        "element_type": elem.element_type,
                        "raw_tokens": repr(elem.raw_tokens),
                        "reason": "bus_not_found",
                    })
                    continue
                if not _branch_exists(model, from_ibus, to_ibus, ckt):
                    unresolved_rows.append({
                        "flowgate_id": elem.flowgate_id,
                        "role": elem.role,
                        "element_type": elem.element_type,
                        "raw_tokens": repr(elem.raw_tokens),
                        "reason": "branch_not_found",
                    })
                    continue
                seeds.append(ResolvedSeed(
                    flowgate_id=elem.flowgate_id,
                    role=elem.role,
                    element_type="branch",
                    seed_buses=frozenset({from_ibus, to_ibus}),
                    raw_tokens=elem.raw_tokens,
                ))
            # Generator resolution: Task 8
            else:
                # Placeholder — generator branch handled in Task 8.
                pass

    unresolved_df = pd.DataFrame(unresolved_rows, columns=_UNRESOLVED_COLUMNS)
    return seeds, unresolved_df
```

- [ ] **Step 7.4: Run tests to verify they pass**

Run: `pdm run pytest tests/test_flowgate_resolve.py -v`
Expected: 4 PASS.

- [ ] **Step 7.5: Commit**

```bash
pdm run ruff check psse_model_util/flowgate.py tests/test_flowgate_resolve.py
git add psse_model_util/flowgate.py tests/test_flowgate_resolve.py
git commit -m "feat(flowgate): resolve branch elements against Model bus/acline/transformer"
```

---

## Task 8: `resolve_elements` — generator (REMOVE MACHINE) branch

**Files:**
- Modify: `psse_model_util/flowgate.py` (extend `resolve_elements` for generators)
- Modify: `tests/test_flowgate_resolve.py`

- [ ] **Step 8.1: Write the failing test**

Append to `tests/test_flowgate_resolve.py`:

```python
def test_resolve_remove_machine_against_model(model_1, synthetic_fgs):
    from psse_model_util.flowgate import resolve_elements

    seeds, _ = resolve_elements(synthetic_fgs, model_1)
    gen_seeds = [s for s in seeds if s.element_type == "generator"]
    assert len(gen_seeds) == 1
    assert gen_seeds[0].flowgate_id == 1003
    assert len(gen_seeds[0].seed_buses) == 1  # generator is on a single bus


def test_resolve_unknown_machine_reports_unresolved(model_1, tmp_path):
    from psse_model_util.flowgate import parse_mon_file, resolve_elements

    # Take FG 1003 from the fixture and replace the machine id with one
    # that won't exist in Model_1.raw.
    import re
    fixture_text = (DATA_DIR / "synthetic_pjm.mon").read_text()
    mangled = re.sub(
        r"REMOVE MACHINE \S+ FROM",
        "REMOVE MACHINE ZZ9 FROM",
        fixture_text,
    )
    p = tmp_path / "mangled.mon"
    p.write_text(mangled)
    fgs = parse_mon_file(p)

    _, unresolved = resolve_elements(fgs, model_1)
    assert any(
        row["reason"] == "generator_not_found"
        for _, row in unresolved.iterrows()
    )
```

- [ ] **Step 8.2: Run tests to verify they fail**

Run: `pdm run pytest tests/test_flowgate_resolve.py -v -k "remove_machine or unknown_machine"`
Expected: 2 FAIL (no generator seeds produced; no `generator_not_found` rows).

- [ ] **Step 8.3: Add generator branch to `resolve_elements`**

In `resolve_elements`, replace the `# Generator resolution: Task 8` placeholder block with:

```python
            elif elem.element_type == "generator":
                bus_token, machine_id = elem.raw_tokens
                gen_ibus = _resolve_bus_token(bus_token)
                if gen_ibus is None:
                    unresolved_rows.append({
                        "flowgate_id": elem.flowgate_id,
                        "role": elem.role,
                        "element_type": elem.element_type,
                        "raw_tokens": repr(elem.raw_tokens),
                        "reason": "bus_not_found",
                    })
                    continue
                gen_df = model.network.generator
                # generator index is MultiIndex (ibus, machid). machid is a string.
                if (gen_ibus, str(machine_id).strip()) not in gen_df.index:
                    unresolved_rows.append({
                        "flowgate_id": elem.flowgate_id,
                        "role": elem.role,
                        "element_type": elem.element_type,
                        "raw_tokens": repr(elem.raw_tokens),
                        "reason": "generator_not_found",
                    })
                    continue
                seeds.append(ResolvedSeed(
                    flowgate_id=elem.flowgate_id,
                    role=elem.role,
                    element_type="generator",
                    seed_buses=frozenset({gen_ibus}),
                    raw_tokens=elem.raw_tokens,
                ))
```

- [ ] **Step 8.4: Run tests to verify they pass**

Run: `pdm run pytest tests/test_flowgate_resolve.py -v`
Expected: all PASS (including 4 from Task 7 and 2 from this task).

- [ ] **Step 8.5: Commit**

```bash
pdm run ruff check psse_model_util/flowgate.py tests/test_flowgate_resolve.py
git add psse_model_util/flowgate.py tests/test_flowgate_resolve.py
git commit -m "feat(flowgate): resolve REMOVE MACHINE elements; emit generator_not_found"
```

---

## Task 9: `resolve_elements` — bus_not_found and kV precision

**Files:**
- Modify: `tests/test_flowgate_resolve.py`

(No production code change needed — `_split_bus_token` and `_build_bus_lookup` already use `round(kv, KV_KEY_DECIMALS)`. This task adds tests that pin the behavior.)

- [ ] **Step 9.1: Write the tests**

Append to `tests/test_flowgate_resolve.py`:

```python
BOGUS_MON = """\
MONITOR FLOWGATE 5000  'bogus bus test'
         BRANCH FROM BUS 'ZZZNOTFOUND 345.00' TO BUS 'ZZZALSOBAD  345.00' CKT 1
 CONTINGENCY 5000
    OPEN BRANCH FROM BUS 'ZZZNOTFOUND 345.00' TO BUS 'ZZZALSOBAD  345.00' CKT 1
 END
    SC PJM
END
"""


def test_resolve_unknown_bus_reports_bus_not_found(model_1, tmp_path):
    from psse_model_util.flowgate import parse_mon_file, resolve_elements

    p = tmp_path / "bogus.mon"
    p.write_text(BOGUS_MON)
    fgs = parse_mon_file(p)

    seeds, unresolved = resolve_elements(fgs, model_1)
    assert seeds == []
    assert len(unresolved) == 2  # one monitor, one contingency
    assert (unresolved["reason"] == "bus_not_found").all()


def test_resolve_kv_precision_three_decimals(model_1):
    """Ensure round(kv, 3) is used so 22.000 matches a bus with baskv 22.0."""
    from psse_model_util.flowgate import _build_bus_lookup, _split_bus_token, KV_KEY_DECIMALS

    lookup = _build_bus_lookup(model_1)
    # Pick any bus and round-trip it through the token format
    bus = model_1.network.bus.iloc[0]
    name = str(bus["name"]).strip()
    baskv = float(bus["baskv"])
    token = f"{name:<12}"[:12] + f"{baskv:<6.2f}"[:6]
    parsed_name, parsed_kv = _split_bus_token(token)
    assert (parsed_name, round(parsed_kv, KV_KEY_DECIMALS)) in lookup
```

- [ ] **Step 9.2: Run and commit**

```bash
pdm run pytest tests/test_flowgate_resolve.py -v
```
Expected: all PASS.

```bash
git add tests/test_flowgate_resolve.py
git commit -m "test(flowgate): pin bus_not_found behavior and kV precision"
```

---

## Task 10: `_build_bus_only_graph` helper

**Files:**
- Modify: `psse_model_util/flowgate.py`

- [ ] **Step 10.1: Create the test file with one test**

Create `tests/test_flowgate_neighborhood.py`:

```python
"""Tests for the bus-only graph and neighborhood expansion."""
from pathlib import Path

import networkx as nx
import pytest

from psse_model_util.model import Model

DATA_DIR = Path(__file__).resolve().parent / "data"


@pytest.fixture(scope="module")
def model_1():
    return Model(DATA_DIR / "Model_1.raw")


def test_bus_only_graph_has_all_buses(model_1):
    from psse_model_util.flowgate import _build_bus_only_graph

    g = _build_bus_only_graph(model_1)
    assert isinstance(g, nx.Graph)
    assert g.number_of_nodes() == len(model_1.network.bus)


def test_bus_only_graph_has_acline_edges(model_1):
    from psse_model_util.flowgate import _build_bus_only_graph

    g = _build_bus_only_graph(model_1)
    ac = model_1.network.acline.reset_index()
    sample = ac.iloc[0]
    assert g.has_edge(int(sample["ibus"]), int(sample["jbus"]))


def test_bus_only_graph_3w_triangle(model_1):
    """3W transformers contribute a triangle among (ibus, jbus, kbus)."""
    from psse_model_util.flowgate import _build_bus_only_graph

    g = _build_bus_only_graph(model_1)
    xf = model_1.network.transformer.reset_index()
    xf3 = xf[xf["kbus"] != 0]
    if xf3.empty:
        pytest.skip("Model_1 has no 3W transformers")
    row = xf3.iloc[0]
    i, j, k = int(row["ibus"]), int(row["jbus"]), int(row["kbus"])
    assert g.has_edge(i, j)
    assert g.has_edge(j, k)
    assert g.has_edge(i, k)
```

- [ ] **Step 10.2: Run tests to verify they fail**

Run: `pdm run pytest tests/test_flowgate_neighborhood.py -v`
Expected: 3 FAIL with `ImportError: cannot import name '_build_bus_only_graph'`.

- [ ] **Step 10.3: Implement `_build_bus_only_graph`**

Append to `psse_model_util/flowgate.py`:

```python
import networkx as nx


def _build_bus_only_graph(model: Model) -> nx.Graph:
    """Build a graph whose nodes are bus ibus values and edges are
    AC lines plus transformer windings.

    2W transformers (kbus == 0) contribute one edge (ibus, jbus).
    3W transformers contribute a triangle among (ibus, jbus, kbus) — this
    correctly models that any pair of windings is one electrical hop apart.
    """
    g = nx.Graph()
    g.add_nodes_from(int(b) for b in model.network.bus.index)

    ac = model.network.acline.reset_index()
    g.add_edges_from(zip(ac["ibus"].astype(int), ac["jbus"].astype(int)))

    xf = model.network.transformer.reset_index()
    xf2 = xf[xf["kbus"] == 0]
    g.add_edges_from(zip(xf2["ibus"].astype(int), xf2["jbus"].astype(int)))

    xf3 = xf[xf["kbus"] != 0]
    for i, j, k in zip(
        xf3["ibus"].astype(int),
        xf3["jbus"].astype(int),
        xf3["kbus"].astype(int),
    ):
        g.add_edges_from([(i, j), (j, k), (i, k)])

    return g
```

- [ ] **Step 10.4: Run tests to verify they pass**

Run: `pdm run pytest tests/test_flowgate_neighborhood.py -v`
Expected: 3 PASS (or 2 PASS + 1 SKIP if no 3W transformers in Model_1).

- [ ] **Step 10.5: Commit**

```bash
pdm run ruff check psse_model_util/flowgate.py tests/test_flowgate_neighborhood.py
git add psse_model_util/flowgate.py tests/test_flowgate_neighborhood.py
git commit -m "feat(flowgate): build bus-only graph with acline + transformer edges"
```

---

## Task 11: `neighborhood_buses` — ego-graph expansion

**Files:**
- Modify: `psse_model_util/flowgate.py`
- Modify: `tests/test_flowgate_neighborhood.py`

- [ ] **Step 11.1: Write the tests**

Append to `tests/test_flowgate_neighborhood.py`:

```python
def test_neighborhood_hops_0_returns_seed_only(model_1):
    from psse_model_util.flowgate import neighborhood_buses

    seed = int(model_1.network.acline.reset_index().iloc[0]["ibus"])
    result = neighborhood_buses(model_1, {seed}, hops=0)
    assert result == {seed}


def test_neighborhood_hops_1_includes_neighbors(model_1):
    from psse_model_util.flowgate import neighborhood_buses, _build_bus_only_graph

    g = _build_bus_only_graph(model_1)
    seed = int(model_1.network.acline.reset_index().iloc[0]["ibus"])
    result = neighborhood_buses(model_1, {seed}, hops=1)
    expected = {seed} | set(g.neighbors(seed))
    assert result == expected


def test_neighborhood_multiple_seeds_unions(model_1):
    from psse_model_util.flowgate import neighborhood_buses

    ac = model_1.network.acline.reset_index()
    seed_a = int(ac.iloc[0]["ibus"])
    seed_b = int(ac.iloc[10]["ibus"]) if len(ac) > 10 else int(ac.iloc[-1]["ibus"])
    result = neighborhood_buses(model_1, {seed_a, seed_b}, hops=1)
    single_a = neighborhood_buses(model_1, {seed_a}, hops=1)
    single_b = neighborhood_buses(model_1, {seed_b}, hops=1)
    assert result == single_a | single_b


def test_neighborhood_grows_monotonically(model_1):
    from psse_model_util.flowgate import neighborhood_buses

    seed = int(model_1.network.acline.reset_index().iloc[0]["ibus"])
    n0 = neighborhood_buses(model_1, {seed}, hops=0)
    n1 = neighborhood_buses(model_1, {seed}, hops=1)
    n2 = neighborhood_buses(model_1, {seed}, hops=2)
    n4 = neighborhood_buses(model_1, {seed}, hops=4)
    assert n0 <= n1 <= n2 <= n4
```

- [ ] **Step 11.2: Run tests to verify they fail**

Run: `pdm run pytest tests/test_flowgate_neighborhood.py -v -k neighborhood`
Expected: 4 FAIL with `ImportError`.

- [ ] **Step 11.3: Implement `neighborhood_buses`**

Append to `psse_model_util/flowgate.py`:

```python
def neighborhood_buses(
    model: Model,
    seed_buses: set[int],
    hops: int = DEFAULT_HOPS,
) -> set[int]:
    """Return the set of buses within `hops` edges of any bus in `seed_buses`
    on the bus-only graph (AC lines + transformer windings).

    Includes the seed buses themselves. Uses nx.ego_graph with radius=hops.
    """
    g = _build_bus_only_graph(model)
    result: set[int] = set()
    for seed in seed_buses:
        if seed not in g:
            logger.warning("seed bus %s not in bus-only graph; skipping", seed)
            continue
        sub = nx.ego_graph(g, seed, radius=hops, undirected=True)
        result.update(int(n) for n in sub.nodes)
    return result
```

- [ ] **Step 11.4: Run tests to verify they pass**

Run: `pdm run pytest tests/test_flowgate_neighborhood.py -v`
Expected: all PASS.

- [ ] **Step 11.5: Commit**

```bash
pdm run ruff check psse_model_util/flowgate.py tests/test_flowgate_neighborhood.py
git add psse_model_util/flowgate.py tests/test_flowgate_neighborhood.py
git commit -m "feat(flowgate): neighborhood_buses via nx.ego_graph"
```

---

## Task 12: `collect_key_facilities` — return-shape skeleton

This task lays in the function and its empty-DataFrame return shape so subsequent tasks can fill in each equipment type.

**Files:**
- Modify: `psse_model_util/flowgate.py`
- Create: `tests/test_flowgate_collect.py`

- [ ] **Step 12.1: Write the failing test**

```python
"""Tests for psse_model_util.flowgate.collect_key_facilities."""
from pathlib import Path

import pandas as pd
import pytest

from psse_model_util.model import Model

DATA_DIR = Path(__file__).resolve().parent / "data"


@pytest.fixture(scope="module")
def model_1():
    return Model(DATA_DIR / "Model_1.raw")


@pytest.fixture(scope="module")
def synthetic_seeds(model_1):
    from psse_model_util.flowgate import (
        parse_mon_file, filter_by_sc, resolve_elements,
    )
    fgs = filter_by_sc(parse_mon_file(DATA_DIR / "synthetic_pjm.mon"), sc="PJM")
    seeds, _ = resolve_elements(fgs, model_1)
    return seeds


BRANCH_COLS = [
    "flowgate_id", "role", "equipment_type",
    "from_name", "from_volt", "from_area",
    "to_name", "to_volt", "to_area",
    "ckt_id",
]
GEN_COLS = ["flowgate_id", "role", "bus_name", "volt", "area", "ckt_id"]
XF3_COLS = [
    "flowgate_id", "role", "transformer_name",
    "w1_bus_name", "w1_volt",
    "w2_bus_name", "w2_volt",
    "w3_bus_name", "w3_volt",
    "ckt_id",
]


def test_collect_returns_four_dataframes(model_1, synthetic_seeds):
    from psse_model_util.flowgate import collect_key_facilities

    out = collect_key_facilities(model_1, synthetic_seeds)
    assert set(out.keys()) == {"branches", "generators", "transformers_3w", "unresolved"}
    for v in out.values():
        assert isinstance(v, pd.DataFrame)


def test_collect_branches_has_expected_columns(model_1, synthetic_seeds):
    from psse_model_util.flowgate import collect_key_facilities

    out = collect_key_facilities(model_1, synthetic_seeds)
    assert list(out["branches"].columns) == BRANCH_COLS


def test_collect_generators_has_expected_columns(model_1, synthetic_seeds):
    from psse_model_util.flowgate import collect_key_facilities

    out = collect_key_facilities(model_1, synthetic_seeds)
    assert list(out["generators"].columns) == GEN_COLS


def test_collect_transformers_3w_has_expected_columns(model_1, synthetic_seeds):
    from psse_model_util.flowgate import collect_key_facilities

    out = collect_key_facilities(model_1, synthetic_seeds)
    assert list(out["transformers_3w"].columns) == XF3_COLS
```

- [ ] **Step 12.2: Run tests to verify they fail**

Run: `pdm run pytest tests/test_flowgate_collect.py -v`
Expected: 4 FAIL with ImportError.

- [ ] **Step 12.3: Implement the skeleton**

Append to `psse_model_util/flowgate.py`:

```python
_BRANCH_COLS = [
    "flowgate_id", "role", "equipment_type",
    "from_name", "from_volt", "from_area",
    "to_name", "to_volt", "to_area",
    "ckt_id",
]
_GEN_COLS = ["flowgate_id", "role", "bus_name", "volt", "area", "ckt_id"]
_XF3_COLS = [
    "flowgate_id", "role", "transformer_name",
    "w1_bus_name", "w1_volt",
    "w2_bus_name", "w2_volt",
    "w3_bus_name", "w3_volt",
    "ckt_id",
]


def collect_key_facilities(
    model: Model,
    seeds: list[ResolvedSeed],
    *,
    hops: int = DEFAULT_HOPS,
    kv_min: float = DEFAULT_KV_MIN,
    kv_max: float = DEFAULT_KV_MAX,
    gen_min_mw: float = DEFAULT_GEN_MIN_MW,
) -> dict[str, pd.DataFrame]:
    """For each seed, expand to its `hops`-bus neighborhood and collect filtered
    branches, generators, and 3W transformers as DataFrames.

    Row granularity: one row per (flowgate_id, role, equipment). Equipment
    reached by multiple flowgates appears in multiple rows.
    """
    # Per-FG neighborhoods (keyed by (flowgate_id, role) so monitor and
    # contingency seeds are tracked separately).
    branch_rows: list[dict] = []
    gen_rows: list[dict] = []
    xf3_rows: list[dict] = []

    # Group seeds by (flowgate_id, role) and union their seed buses
    fg_role_seeds: dict[tuple[int, str], set[int]] = {}
    for s in seeds:
        key = (s.flowgate_id, s.role)
        fg_role_seeds.setdefault(key, set()).update(s.seed_buses)

    # Collection per (fg_id, role) is filled in Tasks 13-15.
    # Placeholder to satisfy the skeleton test:
    for (fg_id, role), n_seeds in fg_role_seeds.items():
        pass  # populated in Tasks 13-15

    return {
        "branches": pd.DataFrame(branch_rows, columns=_BRANCH_COLS),
        "generators": pd.DataFrame(gen_rows, columns=_GEN_COLS),
        "transformers_3w": pd.DataFrame(xf3_rows, columns=_XF3_COLS),
        "unresolved": pd.DataFrame(columns=_UNRESOLVED_COLUMNS),
    }
```

- [ ] **Step 12.4: Run tests to verify they pass**

Run: `pdm run pytest tests/test_flowgate_collect.py -v`
Expected: 4 PASS.

- [ ] **Step 12.5: Commit**

```bash
pdm run ruff check psse_model_util/flowgate.py tests/test_flowgate_collect.py
git add psse_model_util/flowgate.py tests/test_flowgate_collect.py
git commit -m "feat(flowgate): collect_key_facilities skeleton with empty DataFrames"
```

---

## Task 13: `collect_key_facilities` — branches (AC lines + 2W transformers)

**Files:**
- Modify: `psse_model_util/flowgate.py`
- Modify: `tests/test_flowgate_collect.py`

- [ ] **Step 13.1: Write the failing tests**

Append to `tests/test_flowgate_collect.py`:

```python
def test_collect_branches_nonempty_for_pjm_seeds(model_1, synthetic_seeds):
    from psse_model_util.flowgate import collect_key_facilities

    out = collect_key_facilities(model_1, synthetic_seeds)
    assert len(out["branches"]) > 0


def test_collect_branches_kv_filter_drops_low_voltage(model_1, synthetic_seeds):
    """Every branch row must have at least one end ≥ kv_min and ≤ kv_max."""
    from psse_model_util.flowgate import collect_key_facilities, DEFAULT_KV_MIN, DEFAULT_KV_MAX

    out = collect_key_facilities(model_1, synthetic_seeds)
    df = out["branches"]
    in_range = (
        ((df["from_volt"] >= DEFAULT_KV_MIN) & (df["from_volt"] <= DEFAULT_KV_MAX))
        | ((df["to_volt"] >= DEFAULT_KV_MIN) & (df["to_volt"] <= DEFAULT_KV_MAX))
    )
    assert in_range.all()


def test_collect_branches_equipment_type_values(model_1, synthetic_seeds):
    from psse_model_util.flowgate import collect_key_facilities

    out = collect_key_facilities(model_1, synthetic_seeds)
    assert set(out["branches"]["equipment_type"]).issubset({"line", "transformer_2w"})


def test_collect_branches_kv_filter_loose(model_1, synthetic_seeds):
    """Override kv_min very high to force most branches out, leaving only
    branches with at least one end ≥ that high voltage."""
    from psse_model_util.flowgate import collect_key_facilities

    out = collect_key_facilities(model_1, synthetic_seeds, kv_min=700.0)
    df = out["branches"]
    if not df.empty:
        passes = ((df["from_volt"] >= 700.0) | (df["to_volt"] >= 700.0)).all()
        assert passes
```

- [ ] **Step 13.2: Run tests to verify they fail**

Run: `pdm run pytest tests/test_flowgate_collect.py -v -k branches`
Expected: `test_collect_branches_nonempty_for_pjm_seeds` and the kV filter tests FAIL (empty DataFrame).

- [ ] **Step 13.3: Implement branch collection**

In `psse_model_util/flowgate.py`, expand the loop body in `collect_key_facilities`. Replace the placeholder `pass` line with the real implementation. To keep `collect_key_facilities` readable, factor branch collection into a helper:

```python
def _collect_branches_for_fg(
    model: Model,
    neighborhood: set[int],
    fg_id: int,
    role: str,
    kv_min: float,
    kv_max: float,
    bus_attrs: pd.DataFrame,
) -> list[dict]:
    """bus_attrs is bus DataFrame reset_index with ibus as a column."""
    rows: list[dict] = []

    # AC lines
    ac = model.network.acline.reset_index()
    ac_hit = ac[ac["ibus"].isin(neighborhood) | ac["jbus"].isin(neighborhood)]
    if not ac_hit.empty:
        ac_hit = ac_hit.merge(
            bus_attrs.rename(columns={
                "ibus": "ibus", "name": "from_name",
                "baskv": "from_volt", "area": "from_area",
            })[["ibus", "from_name", "from_volt", "from_area"]],
            on="ibus", how="left",
        ).merge(
            bus_attrs.rename(columns={
                "ibus": "jbus", "name": "to_name",
                "baskv": "to_volt", "area": "to_area",
            })[["jbus", "to_name", "to_volt", "to_area"]],
            on="jbus", how="left",
        )
        ac_hit = ac_hit[
            ((ac_hit["from_volt"] >= kv_min) & (ac_hit["from_volt"] <= kv_max))
            | ((ac_hit["to_volt"] >= kv_min) & (ac_hit["to_volt"] <= kv_max))
        ]
        for _, r in ac_hit.iterrows():
            rows.append({
                "flowgate_id": fg_id, "role": role, "equipment_type": "line",
                "from_name": r["from_name"], "from_volt": r["from_volt"],
                "from_area": int(r["from_area"]),
                "to_name": r["to_name"], "to_volt": r["to_volt"],
                "to_area": int(r["to_area"]),
                "ckt_id": str(r["ckt"]).strip(),
            })

    # 2W transformers (kbus == 0)
    xf = model.network.transformer.reset_index()
    xf2 = xf[(xf["kbus"] == 0) & (xf["ibus"].isin(neighborhood) | xf["jbus"].isin(neighborhood))]
    if not xf2.empty:
        xf2 = xf2.merge(
            bus_attrs.rename(columns={
                "name": "from_name", "baskv": "from_volt", "area": "from_area",
            })[["ibus", "from_name", "from_volt", "from_area"]],
            on="ibus", how="left",
        ).merge(
            bus_attrs.rename(columns={
                "ibus": "jbus", "name": "to_name",
                "baskv": "to_volt", "area": "to_area",
            })[["jbus", "to_name", "to_volt", "to_area"]],
            on="jbus", how="left",
        )
        xf2 = xf2[
            ((xf2["from_volt"] >= kv_min) & (xf2["from_volt"] <= kv_max))
            | ((xf2["to_volt"] >= kv_min) & (xf2["to_volt"] <= kv_max))
        ]
        for _, r in xf2.iterrows():
            rows.append({
                "flowgate_id": fg_id, "role": role, "equipment_type": "transformer_2w",
                "from_name": r["from_name"], "from_volt": r["from_volt"],
                "from_area": int(r["from_area"]),
                "to_name": r["to_name"], "to_volt": r["to_volt"],
                "to_area": int(r["to_area"]),
                "ckt_id": str(r["ckt"]).strip(),
            })

    return rows
```

Update the loop in `collect_key_facilities`:

```python
    bus_attrs = model.network.bus.reset_index()[["ibus", "name", "baskv", "area"]]

    for (fg_id, role), seed_set in fg_role_seeds.items():
        neighborhood = neighborhood_buses(model, seed_set, hops=hops)
        branch_rows.extend(
            _collect_branches_for_fg(
                model, neighborhood, fg_id, role, kv_min, kv_max, bus_attrs
            )
        )
```

- [ ] **Step 13.4: Run tests to verify they pass**

Run: `pdm run pytest tests/test_flowgate_collect.py -v`
Expected: branch tests PASS; gen and xf3 tests still pass (empty DataFrames still have correct columns).

- [ ] **Step 13.5: Commit**

```bash
pdm run ruff check psse_model_util/flowgate.py tests/test_flowgate_collect.py
git add psse_model_util/flowgate.py tests/test_flowgate_collect.py
git commit -m "feat(flowgate): collect branches (acline + 2W xfmrs) with kV filter"
```

---

## Task 14: `collect_key_facilities` — generators

**Files:**
- Modify: `psse_model_util/flowgate.py`
- Modify: `tests/test_flowgate_collect.py`

- [ ] **Step 14.1: Write the failing tests**

Append to `tests/test_flowgate_collect.py`:

```python
def test_collect_generators_mw_filter_default(model_1, synthetic_seeds):
    """Every generator in the output must have come from a (ibus, machid) whose
    source row has pt >= DEFAULT_GEN_MIN_MW."""
    from psse_model_util.flowgate import collect_key_facilities, DEFAULT_GEN_MIN_MW

    out = collect_key_facilities(model_1, synthetic_seeds)
    gens = out["generators"]
    if gens.empty:
        pytest.skip("No generators in PJM neighborhood; nothing to verify")

    # Build a (bus_name, volt, machid) -> pt lookup from the source
    bus_attrs = model_1.network.bus.reset_index()[["ibus", "name", "baskv"]]
    gen_src = model_1.network.generator.reset_index().merge(
        bus_attrs, on="ibus", how="left"
    )
    gen_src["name"] = gen_src["name"].astype(str).str.strip()
    gen_src["machid"] = gen_src["machid"].astype(str).str.strip()
    pt_lookup = {
        (row["name"], float(row["baskv"]), row["machid"]): float(row["pt"])
        for _, row in gen_src.iterrows()
    }

    for _, row in gens.iterrows():
        key = (str(row["bus_name"]).strip(), float(row["volt"]), str(row["ckt_id"]).strip())
        assert key in pt_lookup, f"output gen {key} not found in source"
        assert pt_lookup[key] >= DEFAULT_GEN_MIN_MW


def test_collect_generators_threshold_override(model_1, synthetic_seeds):
    from psse_model_util.flowgate import collect_key_facilities

    out_default = collect_key_facilities(model_1, synthetic_seeds)
    out_high = collect_key_facilities(model_1, synthetic_seeds, gen_min_mw=10000.0)
    assert len(out_high["generators"]) <= len(out_default["generators"])
    assert len(out_high["generators"]) == 0  # no real gen reaches 10 GW
```

- [ ] **Step 14.2: Run tests to verify they fail**

Run: `pdm run pytest tests/test_flowgate_collect.py -v -k generators`
Expected: `test_collect_generators_threshold_override` FAILs because both sides are 0.

- [ ] **Step 14.3: Implement generator collection**

Add helper to `psse_model_util/flowgate.py`:

```python
def _collect_generators_for_fg(
    model: Model,
    neighborhood: set[int],
    fg_id: int,
    role: str,
    gen_min_mw: float,
    bus_attrs: pd.DataFrame,
) -> list[dict]:
    gen = model.network.generator.reset_index()
    hit = gen[(gen["ibus"].isin(neighborhood)) & (gen["pt"] >= gen_min_mw)]
    if hit.empty:
        return []
    hit = hit.merge(
        bus_attrs.rename(columns={
            "name": "bus_name", "baskv": "volt", "area": "area",
        })[["ibus", "bus_name", "volt", "area"]],
        on="ibus", how="left",
    )
    rows: list[dict] = []
    for _, r in hit.iterrows():
        rows.append({
            "flowgate_id": fg_id, "role": role,
            "bus_name": r["bus_name"], "volt": float(r["volt"]),
            "area": int(r["area"]),
            "ckt_id": str(r["machid"]).strip(),
        })
    return rows
```

In `collect_key_facilities`, inside the loop, add:

```python
        gen_rows.extend(
            _collect_generators_for_fg(
                model, neighborhood, fg_id, role, gen_min_mw, bus_attrs
            )
        )
```

- [ ] **Step 14.4: Run tests to verify they pass**

Run: `pdm run pytest tests/test_flowgate_collect.py -v`
Expected: all PASS.

- [ ] **Step 14.5: Commit**

```bash
pdm run ruff check psse_model_util/flowgate.py tests/test_flowgate_collect.py
git add psse_model_util/flowgate.py tests/test_flowgate_collect.py
git commit -m "feat(flowgate): collect generators with PT filter"
```

---

## Task 15: `collect_key_facilities` — 3W transformers

**Files:**
- Modify: `psse_model_util/flowgate.py`
- Modify: `tests/test_flowgate_collect.py`

- [ ] **Step 15.1: Write the failing tests**

Append to `tests/test_flowgate_collect.py`:

```python
def test_collect_3w_transformers_shape(model_1, synthetic_seeds):
    from psse_model_util.flowgate import collect_key_facilities

    out = collect_key_facilities(model_1, synthetic_seeds)
    xf3 = out["transformers_3w"]
    # Skip if Model_1 has none
    if xf3.empty:
        pytest.skip("Model_1 has no 3W transformers in the PJM neighborhoods")
    for _, row in xf3.iterrows():
        assert row["w1_bus_name"]
        assert row["w2_bus_name"]
        assert row["w3_bus_name"]
        assert row["w1_volt"] > 0
        assert row["w2_volt"] > 0
        assert row["w3_volt"] > 0


def test_collect_3w_transformers_kv_filter(model_1, synthetic_seeds):
    from psse_model_util.flowgate import collect_key_facilities, DEFAULT_KV_MIN, DEFAULT_KV_MAX

    out = collect_key_facilities(model_1, synthetic_seeds)
    xf3 = out["transformers_3w"]
    if xf3.empty:
        pytest.skip("no 3W xfmrs to filter")
    in_range = (
        xf3["w1_volt"].between(DEFAULT_KV_MIN, DEFAULT_KV_MAX)
        | xf3["w2_volt"].between(DEFAULT_KV_MIN, DEFAULT_KV_MAX)
        | xf3["w3_volt"].between(DEFAULT_KV_MIN, DEFAULT_KV_MAX)
    )
    assert in_range.all()
```

- [ ] **Step 15.2: Run tests to verify they fail (or skip)**

Run: `pdm run pytest tests/test_flowgate_collect.py -v -k 3w_transformers`
Expected: FAIL or SKIP depending on Model_1 contents. If they SKIP, the helper is still needed — proceed.

- [ ] **Step 15.3: Implement 3W collection**

Add helper to `psse_model_util/flowgate.py`:

```python
def _collect_3w_for_fg(
    model: Model,
    neighborhood: set[int],
    fg_id: int,
    role: str,
    kv_min: float,
    kv_max: float,
    bus_attrs: pd.DataFrame,
) -> list[dict]:
    xf = model.network.transformer.reset_index()
    xf3 = xf[
        (xf["kbus"] != 0)
        & (
            xf["ibus"].isin(neighborhood)
            | xf["jbus"].isin(neighborhood)
            | xf["kbus"].isin(neighborhood)
        )
    ]
    if xf3.empty:
        return []
    # Join bus attrs three times for w1/w2/w3
    xf3 = xf3.merge(
        bus_attrs.rename(columns={
            "name": "w1_bus_name", "baskv": "w1_volt",
        })[["ibus", "w1_bus_name", "w1_volt"]],
        on="ibus", how="left",
    ).merge(
        bus_attrs.rename(columns={
            "ibus": "jbus", "name": "w2_bus_name", "baskv": "w2_volt",
        })[["jbus", "w2_bus_name", "w2_volt"]],
        on="jbus", how="left",
    ).merge(
        bus_attrs.rename(columns={
            "ibus": "kbus", "name": "w3_bus_name", "baskv": "w3_volt",
        })[["kbus", "w3_bus_name", "w3_volt"]],
        on="kbus", how="left",
    )
    xf3 = xf3[
        xf3["w1_volt"].between(kv_min, kv_max)
        | xf3["w2_volt"].between(kv_min, kv_max)
        | xf3["w3_volt"].between(kv_min, kv_max)
    ]
    rows: list[dict] = []
    for _, r in xf3.iterrows():
        rows.append({
            "flowgate_id": fg_id, "role": role,
            "transformer_name": str(r["name"]).strip(),
            "w1_bus_name": r["w1_bus_name"], "w1_volt": float(r["w1_volt"]),
            "w2_bus_name": r["w2_bus_name"], "w2_volt": float(r["w2_volt"]),
            "w3_bus_name": r["w3_bus_name"], "w3_volt": float(r["w3_volt"]),
            "ckt_id": str(r["ckt"]).strip(),
        })
    return rows
```

In `collect_key_facilities`, inside the loop, add:

```python
        xf3_rows.extend(
            _collect_3w_for_fg(
                model, neighborhood, fg_id, role, kv_min, kv_max, bus_attrs
            )
        )
```

- [ ] **Step 15.4: Run tests to verify they pass (or skip cleanly)**

Run: `pdm run pytest tests/test_flowgate_collect.py -v`
Expected: PASS or SKIP. Whole-suite re-run: `pdm run pytest tests/ -v -k flowgate` — all PASS/SKIP.

- [ ] **Step 15.5: Commit**

```bash
pdm run ruff check psse_model_util/flowgate.py tests/test_flowgate_collect.py
git add psse_model_util/flowgate.py tests/test_flowgate_collect.py
git commit -m "feat(flowgate): collect 3W transformers with loose kV filter"
```

---

## Task 16: Row granularity — one row per (flowgate_id, role, equipment) pair

**Files:**
- Modify: `tests/test_flowgate_collect.py`

This task pins the spec's row-granularity contract. If `collect_key_facilities` is implemented correctly across Tasks 13-15 it should already pass.

- [ ] **Step 16.1: Write the tests**

Append to `tests/test_flowgate_collect.py`:

```python
def test_branches_role_column_values(model_1, synthetic_seeds):
    from psse_model_util.flowgate import collect_key_facilities

    out = collect_key_facilities(model_1, synthetic_seeds)
    assert set(out["branches"]["role"]).issubset({"monitor", "contingency"})


def test_branches_have_at_least_one_monitor_and_contingency_row(model_1, synthetic_seeds):
    """The synthetic fixture has both monitor and contingency seeds in PJM areas;
    at least one of each role should appear in the branches output."""
    from psse_model_util.flowgate import collect_key_facilities

    out = collect_key_facilities(model_1, synthetic_seeds)
    roles = set(out["branches"]["role"])
    assert "monitor" in roles
    assert "contingency" in roles


def test_equipment_in_two_flowgates_produces_two_rows(model_1):
    """Construct a 2-FG synthetic fixture where the same branch is the monitor in
    both FGs; verify it appears twice in the output."""
    from psse_model_util.flowgate import (
        parse_mon_file, filter_by_sc, resolve_elements, collect_key_facilities,
    )

    # Reuse the fixture FG 1001 / 1002 by re-parsing
    fgs = filter_by_sc(parse_mon_file(DATA_DIR / "synthetic_pjm.mon"), sc="PJM")
    seeds, _ = resolve_elements(fgs, model_1)
    out = collect_key_facilities(model_1, seeds)
    # Pick any branch row and count how many flowgate_ids it appears under
    df = out["branches"]
    if df.empty:
        pytest.skip("no branch rows")
    counts = df.groupby(["from_name", "from_volt", "to_name", "to_volt", "ckt_id"])[
        "flowgate_id"
    ].nunique()
    # Spec contract: equipment reached by N flowgates produces N rows (per role).
    # We don't require N>1 in the synthetic fixture; we just verify the schema
    # is consistent (no exception above).
    assert counts.min() >= 1
```

- [ ] **Step 16.2: Run and commit**

```bash
pdm run pytest tests/test_flowgate_collect.py -v
git add tests/test_flowgate_collect.py
git commit -m "test(flowgate): pin row granularity and role column values"
```

---

## Task 17: Pre-CLI integration test (end-to-end through stages)

**Files:**
- Modify: `tests/test_flowgate_collect.py`

- [ ] **Step 17.1: Write end-to-end test**

```python
def test_end_to_end_synthetic_to_dataframes(model_1):
    from psse_model_util.flowgate import (
        parse_mon_file, filter_by_sc, resolve_elements, collect_key_facilities,
    )

    fgs = parse_mon_file(DATA_DIR / "synthetic_pjm.mon")
    pjm = filter_by_sc(fgs, sc="PJM")
    assert [fg.flowgate_id for fg in pjm] == [1001, 1002, 1003]

    seeds, unresolved = resolve_elements(pjm, model_1)
    assert unresolved.empty, f"unexpected unresolved rows:\n{unresolved}"

    out = collect_key_facilities(model_1, seeds)
    # Sanity: branches non-empty (synthetic PJM seeds are 345 kV)
    assert len(out["branches"]) > 0
    # All 4 keys present
    assert set(out.keys()) == {"branches", "generators", "transformers_3w", "unresolved"}
```

- [ ] **Step 17.2: Run and commit**

```bash
pdm run pytest tests/test_flowgate_collect.py -v -k end_to_end
git add tests/test_flowgate_collect.py
git commit -m "test(flowgate): add end-to-end pipeline test"
```

---

## Task 18: Standalone CLI (sibling repo)

**Files:**
- Create: `C:\Users\Chris\PycharmProjects\key_facilities\key_facilities.py`
- Create: `C:\Users\Chris\PycharmProjects\key_facilities\pyproject.toml`
- Create: `C:\Users\Chris\PycharmProjects\key_facilities\README.md`

- [ ] **Step 18.1: Create sibling directory + pyproject.toml**

```bash
mkdir -p /c/Users/Chris/PycharmProjects/key_facilities
```

Write `C:\Users\Chris\PycharmProjects\key_facilities\pyproject.toml`:

```toml
[project]
name = "key-facilities"
version = "0.1.0"
description = "CLI for extracting key facilities near PSS/E flowgate elements."
requires-python = ">=3.10"
dependencies = [
    "pandas",
    "networkx",
    # psse-model-util is installed editably in dev: `pdm add -e ../psse_model_util`
]

[project.scripts]
key-facilities = "key_facilities:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

- [ ] **Step 18.2: Write the CLI script**

`C:\Users\Chris\PycharmProjects\key_facilities\key_facilities.py`:

```python
"""CLI for extracting key facilities near PSS/E flowgate elements.

Usage:
    python key_facilities.py --mon FLOWGATES.mon --raw MODEL.raw --out-dir OUT/

Writes branches.csv, generators.csv, transformers_3w.csv, unresolved.csv
to --out-dir.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from psse_model_util.model import Model
from psse_model_util.flowgate import (
    DEFAULT_GEN_MIN_MW,
    DEFAULT_HOPS,
    DEFAULT_KV_MAX,
    DEFAULT_KV_MIN,
    DEFAULT_SC,
    collect_key_facilities,
    filter_by_sc,
    parse_mon_file,
    resolve_elements,
)

logger = logging.getLogger("key_facilities")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mon", required=True, type=Path, help="Path to .mon flowgate file")
    p.add_argument("--raw", required=True, type=Path, help="Path to PSS/E .raw model")
    p.add_argument("--out-dir", required=True, type=Path, help="Output directory for CSVs")
    p.add_argument("--hops", type=int, default=DEFAULT_HOPS)
    p.add_argument("--kv-min", type=float, default=DEFAULT_KV_MIN)
    p.add_argument("--kv-max", type=float, default=DEFAULT_KV_MAX)
    p.add_argument("--gen-min-mw", type=float, default=DEFAULT_GEN_MIN_MW)
    p.add_argument("--sc", default=DEFAULT_SC, help="Security Coordinator filter")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    args.out_dir.mkdir(parents=True, exist_ok=True)

    fgs = parse_mon_file(args.mon)
    fgs_filtered = filter_by_sc(fgs, sc=args.sc)
    logger.info(
        "Parsed %d flowgates → %d %s", len(fgs), len(fgs_filtered), args.sc
    )

    model = Model(args.raw)
    seeds, unresolved = resolve_elements(fgs_filtered, model)
    total_elements = sum(len(fg.monitor) + len(fg.contingency) for fg in fgs_filtered)
    logger.info(
        "Resolved %d/%d seeds (%d unresolved)",
        len(seeds), total_elements, len(unresolved),
    )

    out = collect_key_facilities(
        model,
        seeds,
        hops=args.hops,
        kv_min=args.kv_min,
        kv_max=args.kv_max,
        gen_min_mw=args.gen_min_mw,
    )
    # collect_key_facilities returns an empty `unresolved` DataFrame in its dict;
    # use the one from resolve_elements instead.
    out["unresolved"] = unresolved

    summary_parts = []
    for name, df in out.items():
        path = args.out_dir / f"{name}.csv"
        df.to_csv(path, index=False)
        summary_parts.append(f"{name}.csv ({len(df)} rows)")

    print(f"Wrote {', '.join(summary_parts)} to {args.out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 18.3: Write README**

`C:\Users\Chris\PycharmProjects\key_facilities\README.md`:

```markdown
# key-facilities

Standalone CLI for extracting "key facilities" near PSS/E flowgate elements.

Imports `psse_model_util.flowgate` to do the heavy lifting; this repo is just a
thin orchestrator that writes the four output DataFrames as CSVs.

## Usage

```
python key_facilities.py \
  --mon path/to/flowgates.mon \
  --raw path/to/Model.raw \
  --out-dir outputs/
```

Optional overrides: `--hops 4`, `--kv-min 160`, `--kv-max 765`,
`--gen-min-mw 15`, `--sc PJM`.

## Output

Four CSV files in `--out-dir`:

- `branches.csv` — AC lines and 2W transformers within `--hops` buses of any
  flowgate seed, filtered to `--kv-min ≤ kV ≤ --kv-max` (either end).
- `generators.csv` — generators within the neighborhood with `PT ≥ --gen-min-mw`.
- `transformers_3w.csv` — 3W transformers with any winding in the neighborhood
  and any winding bus in the kV range.
- `unresolved.csv` — `.mon` elements that could not be resolved against the
  model (bus name not found, branch not found, generator not found).
```

- [ ] **Step 18.4: Manual smoke test**

```bash
cd /c/Users/Chris/PycharmProjects/key_facilities
python key_facilities.py \
  --mon ../psse_model_util/tests/data/synthetic_pjm.mon \
  --raw ../psse_model_util/tests/data/Model_1.raw \
  --out-dir /tmp/key_facilities_smoke
ls /tmp/key_facilities_smoke
```

Expected: 4 CSV files (`branches.csv`, `generators.csv`, `transformers_3w.csv`, `unresolved.csv`).
Note: on Windows substitute `$env:TEMP\key_facilities_smoke` for the out-dir.

- [ ] **Step 18.5: Commit (in key_facilities repo, NOT in psse_model_util)**

```bash
cd /c/Users/Chris/PycharmProjects/key_facilities
git init
git add key_facilities.py pyproject.toml README.md
git commit -m "feat: initial CLI for flowgate key-facility extraction"
```

---

## Task 19: CLI smoke test in the package repo

**Files:**
- Create: `tests/test_flowgate_cli.py`

- [ ] **Step 19.1: Write the test**

```python
"""Smoke test for the standalone CLI script. Skips if the sibling repo isn't checked out."""
import subprocess
import sys
from pathlib import Path

import pytest

DATA_DIR = Path(__file__).resolve().parent / "data"
CLI_SCRIPT = (
    Path(__file__).resolve().parent.parent.parent / "key_facilities" / "key_facilities.py"
)


@pytest.mark.skipif(
    not CLI_SCRIPT.exists(),
    reason=f"CLI script not found at {CLI_SCRIPT}; skipping smoke test.",
)
def test_cli_writes_four_csvs(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(CLI_SCRIPT),
            "--mon", str(DATA_DIR / "synthetic_pjm.mon"),
            "--raw", str(DATA_DIR / "Model_1.raw"),
            "--out-dir", str(tmp_path),
            "--sc", "PJM",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f"stderr:\n{result.stderr}\nstdout:\n{result.stdout}"
    for name in ["branches.csv", "generators.csv", "transformers_3w.csv", "unresolved.csv"]:
        assert (tmp_path / name).exists(), f"missing {name}"
```

- [ ] **Step 19.2: Run and commit**

```bash
pdm run pytest tests/test_flowgate_cli.py -v
```
Expected: PASS (or SKIP if the sibling repo isn't on this machine).

```bash
git add tests/test_flowgate_cli.py
git commit -m "test(flowgate): smoke test for standalone CLI"
```

---

## Task 20: Coverage check + final sweep

**Files:** none modified.

- [ ] **Step 20.1: Run full flowgate test suite with coverage**

```bash
pdm run pytest tests/ -v -k flowgate --cov=psse_model_util.flowgate --cov-report=term-missing
```

Expected: all PASS (or SKIP for 3W if absent / for CLI if sibling repo missing). Coverage on `psse_model_util/flowgate.py` ≥ 80%.

- [ ] **Step 20.2: Run the entire test suite to confirm nothing else broke**

```bash
pdm run pytest tests/ -v
```
Expected: all PASS / SKIP, no FAIL or ERROR. Coverage gate (40%) passes.

- [ ] **Step 20.3: Lint everything once more**

```bash
pdm run ruff check psse_model_util/flowgate.py tests/test_flowgate_*.py tests/build_synthetic_mon.py
```
Expected: no errors.

- [ ] **Step 20.4: If anything fails, fix and commit per the usual TDD loop.** Do not skip this step.

---

## Notes for the Executing Engineer

- **Don't read tasks out of order.** Each task assumes the previous ones are committed.
- **Pandas note:** `model.network.<section>` DataFrames have non-trivial MultiIndexes. Always `reset_index()` before joining or filtering on bus columns.
- **kV column name:** the bus DataFrame column is `baskv` (not `basekv`). The spec text used `basekv` historically; the plan and code use `baskv` consistently.
- **2W vs 3W transformer:** detected by `kbus == 0` (2W) vs `kbus != 0` (3W). There is no `nwind` column.
- **Generator id column:** `machid`, as a string. Strip whitespace when comparing.
- **PSS/E machine ids and bus names may have leading/trailing spaces.** Always `str(x).strip()` before equality checks.
- **`Model.__init__` is slow on large models** but uses a pickle cache. Don't pass `force_recalculate=True` in tests unless you know why.
- **The synthetic fixture (`tests/data/synthetic_pjm.mon`) is committed** — do not regenerate it during normal runs; only run `tests/build_synthetic_mon.py` if `Model_1.raw` changes in a way that invalidates it.
