"""Flowgate (.mon) parsing and key-facility neighborhood extraction.

Parses PSS/E .mon flowgate-definition files, resolves their monitored and
contingency elements against a PSS/E Model, expands an n-hop bus
neighborhood around each, filters by voltage and machine rating, and
emits four DataFrames (branches, generators, transformers_3w, unresolved).

The implementation is split across private submodules:

  - `_types`   — constants, valid-value tuples, and the three frozen
                 dataclasses (FlowgateElement, Flowgate, ResolvedSeed).
  - `_parse`   — state-machine parser for .mon files plus `filter_by_sc`.
  - `_resolve` — `resolve_elements` plus bus / branch / generator lookup helpers.
  - `_graph`   — bus-only `nx.Graph` builder and `neighborhood_buses`.
  - `_collect` — `collect_key_facilities` plus per-equipment-type helpers.
  - `_api`     — `extract_key_facilities` end-to-end wrapper.

All public names plus the underscored helpers that tests import directly
are re-exported here so `from psse_model_util.flowgate import X` works for
every previously-published symbol.

See docs/superpowers/specs/2026-05-29-flowgate-key-elements-design.md.
"""
# ruff: noqa: I001
# The public-API / compat-re-export sections below are grouped intentionally
# by submodule and visibility, not alphabetically. Disable the import sorter
# so the section structure (with explanatory comments between groups) is
# preserved.
from __future__ import annotations

# --- Public API: defaults + dataclasses ---
from psse_model_util.flowgate._types import (
    DEFAULT_GEN_MIN_MW,
    DEFAULT_HOPS,
    DEFAULT_KV_MAX,
    DEFAULT_KV_MIN,
    KV_KEY_DECIMALS,
    Flowgate,
    FlowgateElement,
    ResolvedSeed,
)

# --- Public API: stage functions + end-to-end wrapper ---
from psse_model_util.flowgate._api import extract_key_facilities
from psse_model_util.flowgate._collect import collect_key_facilities
from psse_model_util.flowgate._graph import neighborhood_buses
from psse_model_util.flowgate._parse import filter_by_sc, parse_mon_file
from psse_model_util.flowgate._resolve import resolve_elements

# --- Compat re-exports: underscored helpers that existing tests import
# directly. The `X as X` redundant-alias idiom (PEP 484) makes the
# re-export explicit so ruff doesn't flag them as unused imports. These
# are NOT part of the stable public API; they're here so external test
# suites and internal consumers don't break on the package split.
from psse_model_util.flowgate._collect import (
    _BRANCH_COLS as _BRANCH_COLS,
    _GEN_COLS as _GEN_COLS,
    _XF3_COLS as _XF3_COLS,
    _collect_3w_for_fg as _collect_3w_for_fg,
    _collect_branches_for_fg as _collect_branches_for_fg,
    _collect_generators_for_fg as _collect_generators_for_fg,
    _int_or_none as _int_or_none,
    _merge_bus_ends as _merge_bus_ends,
)
from psse_model_util.flowgate._graph import _build_bus_only_graph as _build_bus_only_graph
from psse_model_util.flowgate._parse import (
    _BUS_TOKEN_LEN as _BUS_TOKEN_LEN,
    _BUS_TOKEN_RE as _BUS_TOKEN_RE,
    _parse_branch_line as _parse_branch_line,
    _parse_remove_machine_line as _parse_remove_machine_line,
    _split_bus_token as _split_bus_token,
)
from psse_model_util.flowgate._resolve import (
    _UNRESOLVED_COLUMNS as _UNRESOLVED_COLUMNS,
    _branch_exists as _branch_exists,
    _build_bus_lookup as _build_bus_lookup,
    _unresolved_token_fields as _unresolved_token_fields,
)

# Public API surface — what `from psse_model_util.flowgate import *` exposes.
# Underscored names above are deliberately omitted: they're test-compat shims.
__all__ = [
    # Defaults
    "DEFAULT_GEN_MIN_MW",
    "DEFAULT_HOPS",
    "DEFAULT_KV_MAX",
    "DEFAULT_KV_MIN",
    "KV_KEY_DECIMALS",
    # Dataclasses
    "Flowgate",
    "FlowgateElement",
    "ResolvedSeed",
    # Stage functions
    "parse_mon_file",
    "filter_by_sc",
    "resolve_elements",
    "neighborhood_buses",
    "collect_key_facilities",
    # End-to-end wrapper
    "extract_key_facilities",
]
