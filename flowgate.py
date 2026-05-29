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
