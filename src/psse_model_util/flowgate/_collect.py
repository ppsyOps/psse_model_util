"""DataFrame assembly: per-FG branch / generator / 3W collection helpers and
the public `collect_key_facilities` entry point.
"""
from __future__ import annotations

import pandas as pd

from psse_model_util.flowgate._graph import _build_bus_only_graph, neighborhood_buses
from psse_model_util.flowgate._types import (
    DEFAULT_GEN_MIN_MW,
    DEFAULT_HOPS,
    DEFAULT_KV_MAX,
    DEFAULT_KV_MIN,
    ResolvedSeed,
)
from psse_model_util.model import Model

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


def _merge_bus_ends(
    df: pd.DataFrame,
    bus_attrs: pd.DataFrame,
    ends: list[tuple[str, str]],
) -> pd.DataFrame:
    """Left-join `bus_attrs` onto `df` once per `(join_col, prefix)` pair.

    For each entry `(join_col, prefix)`, the bus DataFrame's `name`,
    `baskv`, and `area` columns are renamed to `prefix + "name"`,
    `prefix + "volt"`, and `prefix + "area"`, and the join key column is
    renamed to `join_col` (so the merge aligns even when `join_col != "ibus"`).

    Example for a 2-end branch:

        _merge_bus_ends(
            df,
            bus_attrs,
            ends=[("ibus", "from_"), ("jbus", "to_")],
        )

    produces a frame with `from_name, from_volt, from_area, to_name,
    to_volt, to_area` columns added.
    """
    result = df
    for join_col, prefix in ends:
        renames = {
            "name": f"{prefix}name",
            "baskv": f"{prefix}volt",
            "area": f"{prefix}area",
        }
        if join_col != "ibus":
            renames["ibus"] = join_col
        right = bus_attrs.rename(columns=renames)[
            [join_col, f"{prefix}name", f"{prefix}volt", f"{prefix}area"]
        ]
        result = result.merge(right, on=join_col, how="left")
    return result


def _int_or_none(value) -> int | None:
    """Coerce a pandas cell to int, or return None when the cell is NaN.

    Left-joins against an area-filtered bus table can yield NaN areas when
    the joined bus was dropped from the filtered set; this helper keeps
    those rows in the output with an empty area column rather than
    crashing on int(NaN).

    Design choice — keep, don't drop:

    A branch with one endpoint inside the kept areas and one endpoint
    outside is **kept** in the output; the outside endpoint's area cell is
    empty (None → empty CSV cell). Dropping these rows would discard
    real signal — they're exactly the branches at the perimeter of the
    search area, which downstream analysis (e.g. tie-line review) often
    cares about most. Consumers who want strictly-inside rows can filter
    on `(from_area.notna() & to_area.notna())` themselves.
    """
    return int(value) if pd.notna(value) else None


def _collect_branches_for_fg(
    model: Model,
    neighborhood: set[int],
    fg_id: int,
    role: str,
    kv_min: float,
    kv_max: float,
    bus_attrs: pd.DataFrame,
) -> list[dict]:
    """Collect AC lines and 2W transformers with at least one endpoint in
    `neighborhood` and at least one end within [kv_min, kv_max].

    bus_attrs is the bus DataFrame reset_index with ibus as a column,
    pre-projected to [ibus, name, baskv, area].
    """
    out_rows: list[dict] = []

    xf = model.network.transformer.reset_index()
    sources = [
        (
            model.network.acline.reset_index(),
            "line",
            None,  # no extra mask; the neighborhood filter alone applies
        ),
        (
            xf,
            "transformer_2w",
            xf["kbus"] == 0,  # restrict to 2-winding rows
        ),
    ]
    ends = [("ibus", "from_"), ("jbus", "to_")]

    for source_df, equipment_type, extra_mask in sources:
        mask = source_df["ibus"].isin(neighborhood) | source_df["jbus"].isin(neighborhood)
        if extra_mask is not None:
            mask = mask & extra_mask
        df = source_df[mask]
        if df.empty:
            continue
        joined = _merge_bus_ends(df, bus_attrs, ends=ends)
        in_kv = (
            joined["from_volt"].between(kv_min, kv_max)
            | joined["to_volt"].between(kv_min, kv_max)
        )
        kept = joined[in_kv].copy()  # defragment after the merge chain
        if kept.empty:
            continue
        kept = kept.assign(
            flowgate_id=fg_id,
            role=role,
            equipment_type=equipment_type,
            from_area=kept["from_area"].map(_int_or_none),
            to_area=kept["to_area"].map(_int_or_none),
            ckt_id=kept["ckt"].astype(str).str.strip(),
        )
        out_rows.extend(kept[_BRANCH_COLS].to_dict("records"))

    return out_rows


def _collect_generators_for_fg(
    model: Model,
    neighborhood: set[int],
    fg_id: int,
    role: str,
    gen_min_mw: float,
    bus_attrs: pd.DataFrame,
) -> list[dict]:
    """Collect generators with ibus in `neighborhood` and pt >= gen_min_mw.

    bus_attrs is the bus DataFrame reset_index with ibus as a column,
    pre-projected to [ibus, name, baskv, area].
    """
    gen = model.network.generator.reset_index()
    hit = gen[(gen["ibus"].isin(neighborhood)) & (gen["pt"] >= gen_min_mw)]
    if hit.empty:
        return []
    hit = hit.merge(
        bus_attrs.rename(columns={"name": "bus_name", "baskv": "volt"})[
            ["ibus", "bus_name", "volt", "area"]
        ],
        on="ibus", how="left",
    )
    hit = hit.assign(
        flowgate_id=fg_id,
        role=role,
        volt=hit["volt"].astype(float),
        area=hit["area"].map(_int_or_none),
        ckt_id=hit["machid"].astype(str).str.strip(),
    )
    return hit[_GEN_COLS].to_dict("records")


def _collect_3w_for_fg(
    model: Model,
    neighborhood: set[int],
    fg_id: int,
    role: str,
    kv_min: float,
    kv_max: float,
    bus_attrs: pd.DataFrame,
) -> list[dict]:
    """Collect 3W transformers with at least one winding bus in `neighborhood`
    and at least one winding within [kv_min, kv_max]. Winding kV comes from
    each winding bus's baskv (not the transformer's nomv* which may be 0).
    """
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
    # Join bus attrs three times — winding voltages come from each winding
    # bus's baskv (not the transformer's nomv* which may be 0). _merge_bus_ends
    # is shaped for the 2-end branch case (which carries an `_area` field);
    # 3W windings don't need area columns, so we inline the three merges.
    xf3 = xf3.merge(
        bus_attrs.rename(columns={"name": "w1_bus_name", "baskv": "w1_volt"})[
            ["ibus", "w1_bus_name", "w1_volt"]
        ],
        on="ibus", how="left",
    ).merge(
        bus_attrs.rename(columns={"ibus": "jbus", "name": "w2_bus_name", "baskv": "w2_volt"})[
            ["jbus", "w2_bus_name", "w2_volt"]
        ],
        on="jbus", how="left",
    ).merge(
        bus_attrs.rename(columns={"ibus": "kbus", "name": "w3_bus_name", "baskv": "w3_volt"})[
            ["kbus", "w3_bus_name", "w3_volt"]
        ],
        on="kbus", how="left",
    )
    in_kv = (
        xf3["w1_volt"].between(kv_min, kv_max)
        | xf3["w2_volt"].between(kv_min, kv_max)
        | xf3["w3_volt"].between(kv_min, kv_max)
    )
    kept = xf3[in_kv].copy()  # defragment after the 3-merge chain
    if kept.empty:
        return []
    kept = kept.assign(
        flowgate_id=fg_id,
        role=role,
        transformer_name=kept["name"].astype(str).str.strip(),
        w1_volt=kept["w1_volt"].astype(float),
        w2_volt=kept["w2_volt"].astype(float),
        w3_volt=kept["w3_volt"].astype(float),
        ckt_id=kept["ckt"].astype(str).str.strip(),
    )
    return kept[_XF3_COLS].to_dict("records")


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

    The returned dict contains 3 keys: 'branches', 'generators',
    'transformers_3w'. Resolution failures live in the second return value
    of `resolve_elements`; callers compose the final 4-key dict themselves
    if they need an 'unresolved' entry. Example:

        seeds, unresolved = resolve_elements(fgs, model)
        result = {
            **collect_key_facilities(model, seeds),
            "unresolved": unresolved,
        }
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

    bus_attrs = model.network.bus.reset_index()[["ibus", "name", "baskv", "area"]]
    # Build the bus-only graph once and reuse across all (fg, role) iterations.
    # Per spec §5.3 — avoids rebuilding the graph N times for N flowgates.
    g = _build_bus_only_graph(model)

    for (fg_id, role), seed_set in fg_role_seeds.items():
        neighborhood = neighborhood_buses(model, seed_set, hops=hops, graph=g)
        branch_rows.extend(
            _collect_branches_for_fg(
                model, neighborhood, fg_id, role, kv_min, kv_max, bus_attrs
            )
        )
        gen_rows.extend(
            _collect_generators_for_fg(
                model, neighborhood, fg_id, role, gen_min_mw, bus_attrs
            )
        )
        xf3_rows.extend(
            _collect_3w_for_fg(
                model, neighborhood, fg_id, role, kv_min, kv_max, bus_attrs
            )
        )

    return {
        "branches": pd.DataFrame(branch_rows, columns=_BRANCH_COLS),
        "generators": pd.DataFrame(gen_rows, columns=_GEN_COLS),
        "transformers_3w": pd.DataFrame(xf3_rows, columns=_XF3_COLS),
    }
