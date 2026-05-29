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
