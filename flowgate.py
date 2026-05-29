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
import re
from dataclasses import dataclass
from typing import Literal

import networkx as nx
import pandas as pd

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
    raw_tokens: tuple[str, ...]


@dataclass(frozen=True)
class Flowgate:
    flowgate_id: int
    description: str
    sc: str  # Security Coordinator (e.g. "PJM"). Empty string means no SC declared.
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
    raw_tokens: tuple[str, ...]


# ---------- parsing primitives ----------
_BUS_TOKEN_LEN = 18  # 12-char name + 6-char kV


def _split_bus_token(token: str) -> tuple[str, float]:
    """Split a PSS/E .mon bus token into (name, base_kv).

    The token is 18 chars wide: 12-char left/right-padded name + 6-char
    kV string. Surrounding single quotes are stripped if present.

    >>> _split_bus_token("'05TANNER    345.00'")
    ('05TANNER', 345.0)
    """
    # Strip only surrounding quotes — do NOT .strip() the whole token, because
    # the 6-char kV field can legitimately have a trailing space (e.g. '21.60 ').
    stripped = token
    if stripped.startswith("'") and stripped.endswith("'"):
        stripped = stripped[1:-1]
    if len(stripped) != _BUS_TOKEN_LEN:
        raise ValueError(
            f"bus token must be {_BUS_TOKEN_LEN} chars (got {len(stripped)}): {token!r}"
        )
    name = stripped[:12].strip()
    kv = float(stripped[12:].strip())
    return name, kv


# Regex for the quoted bus token inside a BRANCH or OPEN BRANCH line.
_BUS_TOKEN_RE = re.compile(r"'([^']{18})'")
_FLOWGATE_HEADER_RE = re.compile(
    r"^\s*MONITOR\s+FLOWGATE\s+(\d+)\s+'([^']*)'", re.IGNORECASE
)
_CONTINGENCY_HEADER_RE = re.compile(r"^\s*CONTINGENCY\s+(\d+)", re.IGNORECASE)
_SC_LINE_RE = re.compile(r"^\s*SC\s+(\S+)", re.IGNORECASE)
_END_RE = re.compile(r"^\s*END\s*$", re.IGNORECASE)
_CKT_RE = re.compile(r"CKT\s+(\S+)", re.IGNORECASE)
_REMOVE_MACHINE_RE = re.compile(
    r"REMOVE\s+MACHINE\s+(\S+)\s+FROM\s+BUS\s+'([^']{18})'", re.IGNORECASE
)


def _parse_branch_line(line: str, flowgate_id: int, role: str) -> FlowgateElement:
    """Parse a 'BRANCH FROM BUS '...' TO BUS '...' CKT <ckt>' line."""
    tokens = _BUS_TOKEN_RE.findall(line)
    if len(tokens) != 2:
        raise ValueError(
            f"branch line must have exactly 2 quoted bus tokens, got {len(tokens)}: {line!r}"
        )
    # CKT id comes after "CKT" keyword
    m = _CKT_RE.search(line)
    if not m:
        raise ValueError(f"branch line missing CKT id: {line!r}")
    ckt = m.group(1).strip().strip("'")
    return FlowgateElement(
        flowgate_id=flowgate_id,
        role=role,
        element_type="branch",
        raw_tokens=(tokens[0], tokens[1], ckt),
    )


def _parse_remove_machine_line(line: str, flowgate_id: int) -> FlowgateElement:
    """Parse 'REMOVE MACHINE <machine_id> FROM BUS '<token>''.

    machine_id is the whitespace-separated token between MACHINE and FROM,
    preserved as a string (PSS/E ids can be alphanumeric, e.g. 'H1').
    """
    m = _REMOVE_MACHINE_RE.search(line)
    if not m:
        raise ValueError(f"malformed REMOVE MACHINE line: {line!r}")
    machine_id = m.group(1).strip("'")
    bus_token = m.group(2)
    return FlowgateElement(
        flowgate_id=flowgate_id,
        role="contingency",
        element_type="generator",
        raw_tokens=(bus_token, machine_id),
    )


def parse_mon_file(path: pathlib.Path | str = DEFAULT_MON_FILEPATH) -> list[Flowgate]:
    """Parse a PSS/E .mon flowgate-definitions file into a list of Flowgate objects.

    Recognized constructs:
      MONITOR FLOWGATE <id> '<description>'
        BRANCH FROM BUS '<token>' TO BUS '<token>' CKT <id>     -- monitored branch
      CONTINGENCY <id>
        OPEN BRANCH FROM BUS '...' TO BUS '...' CKT <id>        -- branch outage
        REMOVE MACHINE <id> FROM BUS '<token>'                  -- generator outage
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

            # Detect a malformed MONITOR FLOWGATE line that the strict regex missed.
            if stripped.upper().startswith("MONITOR FLOWGATE"):
                raise ValueError(
                    f"line {lineno}: malformed MONITOR FLOWGATE header "
                    f"(expected: MONITOR FLOWGATE <id> '<description>'): {line!r}"
                )

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

            # REMOVE MACHINE line (must appear inside a CONTINGENCY block)
            if stripped.upper().startswith("REMOVE MACHINE "):
                if state != "IN_CONTINGENCY":
                    raise ValueError(
                        f"line {lineno}: REMOVE MACHINE outside CONTINGENCY block "
                        f"(state={state}): {line!r}"
                    )
                current_contingency.append(
                    _parse_remove_machine_line(line, current_fg_id)
                )
                continue

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


def filter_by_sc(fgs: list[Flowgate], sc: str = DEFAULT_SC) -> list[Flowgate]:
    """Keep only flowgates whose Security Coordinator matches `sc` (case-sensitive)."""
    return [fg for fg in fgs if fg.sc == sc]


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
    # Build a set of (ibus, machid_stripped) for robust generator lookup.
    # Real PSS/E generator indices often have machid with trailing whitespace
    # (e.g. '1 ' for single-digit ids), but .mon files always use the stripped
    # form — pre-stripping the index side makes the comparison symmetric.
    gen_keys = {
        (int(ibus), str(machid).strip())
        for ibus, machid in model.network.generator.index
    }
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
                # Use the pre-normalized gen_keys set so whitespace differences
                # between the .mon file and the model index don't cause false misses.
                if (gen_ibus, str(machine_id).strip()) not in gen_keys:
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

    unresolved_df = pd.DataFrame(unresolved_rows, columns=_UNRESOLVED_COLUMNS)
    return seeds, unresolved_df


def _build_bus_only_graph(model: Model) -> nx.Graph:
    """Build a graph whose nodes are bus ibus values and edges are
    AC lines plus transformer windings.

    2W transformers (kbus == 0) contribute one edge (ibus, jbus).
    3W transformers contribute a triangle among (ibus, jbus, kbus) -- this
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
