"""Resolve parsed FlowgateElements against a PSS/E Model.

Produces ResolvedSeed records for everything that maps to real bus / branch /
generator ids, and a pandas DataFrame of rows that did not resolve.
"""
from __future__ import annotations

import pandas as pd

from psse_model_util.flowgate._parse import _split_bus_token
from psse_model_util.flowgate._types import (
    KV_KEY_DECIMALS,
    Flowgate,
    FlowgateElement,
    ResolvedSeed,
)
from psse_model_util.model import Model

_UNRESOLVED_COLUMNS = [
    "flowgate_id", "role", "element_type",
    "from_token", "to_token", "ckt_id",  # populated for element_type == "branch"
    "bus_token", "machine_id",            # populated for element_type == "generator"
    "reason",
]


def _unresolved_token_fields(elem: FlowgateElement) -> dict:
    """Split a FlowgateElement's raw_tokens into per-type unresolved columns.

    Branches fill (from_token, to_token, ckt_id); generators fill
    (bus_token, machine_id). The other columns are None so they render
    as empty cells in the CSV.
    """
    if elem.element_type == "branch":
        from_token, to_token, ckt_id = elem.raw_tokens
        return {
            "from_token": from_token,
            "to_token": to_token,
            "ckt_id": ckt_id,
            "bus_token": None,
            "machine_id": None,
        }
    # element_type == "generator" (enforced by FlowgateElement.__post_init__)
    bus_token, machine_id = elem.raw_tokens
    return {
        "from_token": None,
        "to_token": None,
        "ckt_id": None,
        "bus_token": bus_token,
        "machine_id": machine_id,
    }


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
                        **_unresolved_token_fields(elem),
                        "reason": "bus_not_found",
                    })
                    continue
                if not _branch_exists(model, from_ibus, to_ibus, ckt):
                    unresolved_rows.append({
                        "flowgate_id": elem.flowgate_id,
                        "role": elem.role,
                        "element_type": elem.element_type,
                        **_unresolved_token_fields(elem),
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
                        **_unresolved_token_fields(elem),
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
                        **_unresolved_token_fields(elem),
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
