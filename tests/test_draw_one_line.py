"""Headless smoke tests for Network.draw_one_line and node-position save/load.

draw_one_line builds a Plotly figure and calls fig.show(); we monkeypatch
Figure.show to a no-op so it runs without a renderer, and redirect Path.home()
to a tmp dir so the position cache never touches the real home directory.
"""
from __future__ import annotations

from pathlib import Path

import plotly.graph_objects as go
import pytest

from psse_model_util.common.dirs import clear_cache
from psse_model_util.model import Model

DATA_DIR = Path(__file__).resolve().parent / "data"


@pytest.fixture(scope="module")
def network():
    clear_cache()
    return Model(DATA_DIR / "sample_v35.rawx", force_recalculate=True).network


@pytest.fixture(autouse=True)
def _headless(monkeypatch, tmp_path):
    # fig.show() would try to open a browser/renderer — make it a no-op.
    monkeypatch.setattr(go.Figure, "show", lambda self, *a, **k: None)
    # Redirect the position cache (Path.home()/.cache/...) into a tmp dir.
    monkeypatch.setattr(Path, "home", lambda: tmp_path)


def _a_bus(network):
    return next(n for n in network.graph().nodes if n[0] == "bus")


def test_draw_light_theme_runs(network):
    network.draw_one_line(_a_bus(network), distance=1, save_positions=False)


def test_draw_dark_theme_runs(network):
    network.draw_one_line(_a_bus(network), distance=2, theme="dark", save_positions=False)


def test_draw_save_then_load_positions(network):
    node = _a_bus(network)
    # save_positions=True writes the layout into the (tmp) home cache.
    network.draw_one_line(node, distance=1, save_positions=True)
    saved = network.load_node_positions()
    assert isinstance(saved, dict) and saved  # non-empty after a save

    # Feeding the saved positions back exercises the load_positions branch.
    network.draw_one_line(node, distance=1, load_positions=saved, save_positions=False)


def test_draw_with_partial_positions_fills_missing(network):
    # Provide positions for only one node so the "missing nodes" spring-layout
    # fallback runs for the rest.
    node = _a_bus(network)
    partial = {str(node): (0.0, 0.0)}
    network.draw_one_line(node, distance=2, load_positions=partial, save_positions=False)


def test_load_node_positions_missing_returns_empty(network):
    # Fresh tmp home for this test -> no cache file yet.
    assert network.load_node_positions() == {}
