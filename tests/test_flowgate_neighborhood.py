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
