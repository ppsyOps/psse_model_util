"""Tests for the bus-only graph and neighborhood expansion."""
from pathlib import Path

import networkx as nx
import pytest

from psse_model_util.model import Model

DATA_DIR = Path(__file__).resolve().parent / "data"


@pytest.fixture(scope="module")
def model_1():
    return Model(DATA_DIR / "Model_1.raw")


def test_bus_only_graph_has_all_buses(model_1):
    from psse_model_util.flowgate import _build_bus_only_graph

    g = _build_bus_only_graph(model_1)
    assert isinstance(g, nx.Graph)
    assert g.number_of_nodes() == len(model_1.network.bus)


def test_bus_only_graph_has_acline_edges(model_1):
    from psse_model_util.flowgate import _build_bus_only_graph

    g = _build_bus_only_graph(model_1)
    ac = model_1.network.acline.reset_index()
    sample = ac.iloc[0]
    assert g.has_edge(int(sample["ibus"]), int(sample["jbus"]))


def test_bus_only_graph_3w_triangle(model_1):
    """3W transformers contribute a triangle among (ibus, jbus, kbus)."""
    from psse_model_util.flowgate import _build_bus_only_graph

    g = _build_bus_only_graph(model_1)
    xf = model_1.network.transformer.reset_index()
    xf3 = xf[xf["kbus"] != 0]
    if xf3.empty:
        pytest.skip("Model_1 has no 3W transformers")
    row = xf3.iloc[0]
    i, j, k = int(row["ibus"]), int(row["jbus"]), int(row["kbus"])
    assert g.has_edge(i, j)
    assert g.has_edge(j, k)
    assert g.has_edge(i, k)


def test_neighborhood_hops_0_returns_seed_only(model_1):
    from psse_model_util.flowgate import neighborhood_buses

    seed = int(model_1.network.acline.reset_index().iloc[0]["ibus"])
    result = neighborhood_buses(model_1, {seed}, hops=0)
    assert result == {seed}


def test_neighborhood_hops_1_includes_neighbors(model_1):
    from psse_model_util.flowgate import _build_bus_only_graph, neighborhood_buses

    g = _build_bus_only_graph(model_1)
    seed = int(model_1.network.acline.reset_index().iloc[0]["ibus"])
    result = neighborhood_buses(model_1, {seed}, hops=1)
    expected = {seed} | set(g.neighbors(seed))
    assert result == expected


def test_neighborhood_multiple_seeds_unions(model_1):
    from psse_model_util.flowgate import neighborhood_buses

    ac = model_1.network.acline.reset_index()
    seed_a = int(ac.iloc[0]["ibus"])
    seed_b = int(ac.iloc[10]["ibus"]) if len(ac) > 10 else int(ac.iloc[-1]["ibus"])
    result = neighborhood_buses(model_1, {seed_a, seed_b}, hops=1)
    single_a = neighborhood_buses(model_1, {seed_a}, hops=1)
    single_b = neighborhood_buses(model_1, {seed_b}, hops=1)
    assert result == single_a | single_b


def test_neighborhood_grows_monotonically(model_1):
    from psse_model_util.flowgate import neighborhood_buses

    seed = int(model_1.network.acline.reset_index().iloc[0]["ibus"])
    n0 = neighborhood_buses(model_1, {seed}, hops=0)
    n1 = neighborhood_buses(model_1, {seed}, hops=1)
    n2 = neighborhood_buses(model_1, {seed}, hops=2)
    n4 = neighborhood_buses(model_1, {seed}, hops=4)
    assert n0 <= n1 <= n2 <= n4
