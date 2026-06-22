"""High-level convenience wrapper that composes the flowgate pipeline end-to-end."""
from __future__ import annotations

import pathlib
from collections.abc import Iterable

import pandas as pd

from psse_model_util.flowgate._collect import collect_key_facilities
from psse_model_util.flowgate._parse import filter_by_sc, parse_mon_file
from psse_model_util.flowgate._resolve import resolve_elements
from psse_model_util.flowgate._types import (
    DEFAULT_GEN_MIN_MW,
    DEFAULT_HOPS,
    DEFAULT_KV_MAX,
    DEFAULT_KV_MIN,
)
from psse_model_util.model import Model


def extract_key_facilities(
    mon_path: pathlib.Path | str,
    raw_path: pathlib.Path | str,
    *,
    sc: str,
    areas: Iterable[int] | None = None,
    hops: int = DEFAULT_HOPS,
    kv_min: float = DEFAULT_KV_MIN,
    kv_max: float = DEFAULT_KV_MAX,
    gen_min_mw: float = DEFAULT_GEN_MIN_MW,
) -> dict[str, pd.DataFrame]:
    """Run the full flowgate pipeline and return the 4-DataFrame result.

    Convenience wrapper that composes the four stage functions in order:

        parse_mon_file(mon_path)
        -> filter_by_sc(sc)
        -> Model(raw_path)
        -> [optional] model.network.filter_by_area(areas)
        -> resolve_elements
        -> collect_key_facilities

    and folds the unresolved DataFrame from `resolve_elements` into the
    final dict so callers get all four outputs in one place.

    Parameters
    ----------
    mon_path : Path | str
        Path to the PSS/E .mon flowgate-definitions file.
    raw_path : Path | str
        Path to the PSS/E .raw model.
    sc : str
        Security Coordinator filter applied after parsing.
    areas : Iterable[int] | None, default None
        If provided, `Network.filter_by_area` is called to restrict the
        search domain to those area IDs before resolution. Seeds whose
        buses fall outside the listed areas will appear in the
        `unresolved` DataFrame with reason "bus_not_found".
    hops, kv_min, kv_max, gen_min_mw
        Forwarded to `collect_key_facilities`.

    Returns
    -------
    dict[str, pd.DataFrame]
        Keys: 'branches', 'generators', 'transformers_3w', 'unresolved'.
    """
    fgs = parse_mon_file(mon_path)
    fgs_filtered = filter_by_sc(fgs, sc=sc)
    model = Model(raw_path)
    if areas is not None:
        model.network.filter_by_area(list(areas), inplace=True)
    seeds, unresolved = resolve_elements(fgs_filtered, model)
    return {
        **collect_key_facilities(
            model,
            seeds,
            hops=hops,
            kv_min=kv_min,
            kv_max=kv_max,
            gen_min_mw=gen_min_mw,
        ),
        "unresolved": unresolved,
    }
