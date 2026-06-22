"""PSS/E .mon file parser: tokens, regex constants, line parsers, and the
state-machine `parse_mon_file` plus the `filter_by_sc` post-filter.
"""
from __future__ import annotations

import logging
import pathlib
import re

from psse_model_util.flowgate._types import Flowgate, FlowgateElement

logger = logging.getLogger(__name__)


# ---------- parsing primitives ----------
_BUS_TOKEN_LEN = 18  # 12-char name + 6-char kV


def _split_bus_token(token: str) -> tuple[str, float]:
    """Split a PSS/E .mon bus token into (name, base_kv).

    The token is 18 chars wide: 12-char left/right-padded name + 6-char
    kV string. Surrounding single quotes are stripped if present.

    >>> _split_bus_token("'NUCPLNT     500.00'")
    ('NUCPLNT', 500.0)
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


def parse_mon_file(path: pathlib.Path | str) -> list[Flowgate]:
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


def filter_by_sc(fgs: list[Flowgate], sc: str) -> list[Flowgate]:
    """Keep only flowgates whose Security Coordinator matches `sc` (case-sensitive)."""
    return [fg for fg in fgs if fg.sc == sc]
