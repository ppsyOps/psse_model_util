"""Bus-only network graph and n-hop neighborhood expansion.

`_build_bus_only_graph` produces an `nx.Graph` whose nodes are bus ibus
values and whose edges are AC lines + transformer windings. `neighborhood_buses`
returns the union of `nx.ego_graph` results around a set of seed buses.
"""
from __future__ import annotations

import logging

import networkx as nx

from psse_model_util.flowgate._types import DEFAULT_HOPS
from psse_model_util.model import Model

logger = logging.getLogger(__name__)


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


def neighborhood_buses(
    model: Model,
    seed_buses: set[int],
    hops: int = DEFAULT_HOPS,
    graph: nx.Graph | None = None,
) -> set[int]:
    """Return the set of buses within `hops` edges of any bus in `seed_buses`
    on the bus-only graph (AC lines + transformer windings).

    Includes the seed buses themselves. Uses nx.ego_graph with radius=hops.

    If `graph` is supplied, it is used directly (avoids rebuilding for
    multi-FG callers like `collect_key_facilities`). Otherwise a fresh
    bus-only graph is built from `model`.
    """
    g = graph if graph is not None else _build_bus_only_graph(model)
    result: set[int] = set()
    for seed in seed_buses:
        if seed not in g:
            logger.warning("seed bus %s not in bus-only graph; skipping", seed)
            continue
        sub = nx.ego_graph(g, seed, radius=hops, undirected=True)
        result.update(int(n) for n in sub.nodes)
    return result
