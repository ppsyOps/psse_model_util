"""Constants, valid-value tuples, and frozen dataclasses for the flowgate pipeline.

This module has no internal dependencies on other flowgate submodules — every
other submodule may import from here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# ---------- defaults (override at call site or CLI) ----------
DEFAULT_HOPS: int = 4
DEFAULT_KV_MIN: float = 160.0
DEFAULT_KV_MAX: float = 765.0
DEFAULT_GEN_MIN_MW: float = 15.0
KV_KEY_DECIMALS: int = 3         # rounding precision for bus-lookup key


# ---------- dataclasses ----------
_VALID_ROLES = ("monitor", "contingency")
_VALID_ELEMENT_TYPES = ("branch", "generator")


@dataclass(frozen=True)
class FlowgateElement:
    """One element parsed from a .mon flowgate block.

    raw_tokens preserves the original text fragments so the unresolved
    report can echo them back verbatim. Shape depends on element_type:

      - element_type == "branch":    (from_bus_token, to_bus_token, ckt_id)
        from_bus_token / to_bus_token are 18-char PSS/E tokens (12-char
        padded name + 6-char kV); ckt_id is the circuit id as parsed
        from the `CKT <id>` keyword.

      - element_type == "generator": (bus_token, machine_id)
        bus_token is the 18-char PSS/E token for the machine's host bus;
        machine_id is the PSS/E machine id as a string (may be
        alphanumeric, e.g. "H1").

    Consumers of `resolve_elements`'s unresolved DataFrame that need to
    interpret the `raw_tokens` column must branch on `element_type`.
    """
    flowgate_id: int
    role: Literal["monitor", "contingency"]
    element_type: Literal["branch", "generator"]
    raw_tokens: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.role not in _VALID_ROLES:
            raise ValueError(
                f"FlowgateElement.role must be one of {_VALID_ROLES!r}, got {self.role!r}"
            )
        if self.element_type not in _VALID_ELEMENT_TYPES:
            raise ValueError(
                f"FlowgateElement.element_type must be one of "
                f"{_VALID_ELEMENT_TYPES!r}, got {self.element_type!r}"
            )


@dataclass(frozen=True)
class Flowgate:
    flowgate_id: int
    description: str
    sc: str  # Security Coordinator (e.g. "SCA"). Empty string means no SC declared.
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

    def __post_init__(self) -> None:
        if self.role not in _VALID_ROLES:
            raise ValueError(
                f"ResolvedSeed.role must be one of {_VALID_ROLES!r}, got {self.role!r}"
            )
        if self.element_type not in _VALID_ELEMENT_TYPES:
            raise ValueError(
                f"ResolvedSeed.element_type must be one of "
                f"{_VALID_ELEMENT_TYPES!r}, got {self.element_type!r}"
            )
