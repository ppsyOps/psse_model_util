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
    """Split a PSS/E .mon bus token into ``(name, base_kv)``.

    The token is 18 chars wide: a 12-char left/right-padded name followed by
    a 6-char kV string. Surrounding single quotes are stripped if present.

    Args:
        token: The 18-char bus token, optionally wrapped in single quotes.

    Returns:
        A ``(name, base_kv)`` tuple: the stripped bus name and its base kV
        as a float.

    Raises:
        ValueError: If the token (after quote-stripping) is not exactly 18
            characters wide.

    Examples:
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
    """Parse a ``BRANCH FROM BUS '...' TO BUS '...' CKT <ckt>`` line.

    Also used for ``OPEN BRANCH`` contingency lines, which share the same
    token layout.

    Args:
        line: The raw .mon line to parse.
        flowgate_id: Id of the owning flowgate, stamped onto the result.
        role: ``"monitor"`` or ``"contingency"``.

    Returns:
        A branch :class:`FlowgateElement` with
        ``raw_tokens == (from_token, to_token, ckt)``.

    Raises:
        ValueError: If the line does not contain exactly two quoted bus
            tokens, or is missing the ``CKT`` id.
    """
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
    """Parse a ``REMOVE MACHINE <machine_id> FROM BUS '<token>'`` line.

    ``machine_id`` is the whitespace-separated token between ``MACHINE`` and
    ``FROM``, preserved as a string (PSS/E ids can be alphanumeric, e.g.
    ``"H1"``).

    Args:
        line: The raw .mon line to parse.
        flowgate_id: Id of the owning flowgate, stamped onto the result.

    Returns:
        A generator :class:`FlowgateElement` with ``role == "contingency"``
        and ``raw_tokens == (bus_token, machine_id)``.

    Raises:
        ValueError: If the line does not match the expected REMOVE MACHINE
            layout.
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
    """Parse a PSS/E .mon flowgate-definitions file into Flowgate objects.

    The parser is a small state machine over the .mon grammar. Recognized
    constructs::

        MONITOR FLOWGATE <id> '<description>'
          BRANCH FROM BUS '<token>' TO BUS '<token>' CKT <id>   # monitored branch
        CONTINGENCY <id>
          OPEN BRANCH FROM BUS '...' TO BUS '...' CKT <id>       # branch outage
          REMOVE MACHINE <id> FROM BUS '<token>'                 # generator outage
        END                                                      # closes contingency
          SC <name>                                              # Security Coordinator
          CA <args>                                              # ignored
          TP <args>                                              # ignored
        END                                                      # closes flowgate

    Unknown lines inside a block are logged at WARNING level and skipped
    (RESILIENT behavior).

    Args:
        path: Path to the .mon flowgate-definitions file.

    Returns:
        One :class:`Flowgate` per MONITOR FLOWGATE block, in file order.

    Raises:
        ValueError: On structural errors such as an unbalanced MONITOR/END,
            a nested MONITOR FLOWGATE, a CONTINGENCY outside a MONITOR block,
            or a malformed BRANCH/REMOVE MACHINE line.
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
    """Keep only flowgates whose Security Coordinator matches ``sc``.

    The comparison is case-sensitive and exact.

    Args:
        fgs: Flowgates to filter.
        sc: Security Coordinator code to match against each flowgate's ``sc``.

    Returns:
        A new list containing only the flowgates whose ``sc`` equals ``sc``.
    """
    return [fg for fg in fgs if fg.sc == sc]
