"""
test_derived_name.py — tests for the `derived_name` column added by
Network.append_bus_info_to_dfs() (via section_with_bus()).

derived_name rules:
  - base kV rendered with trailing zeros stripped + 'kV' suffix
    (500.0 -> '500kV', 34.5 -> '34.5kV', 123.45 -> '123.45kV')
  - single-bus equipment:  "<name> <kv>kV - <id>"
  - multi-bus equipment:   "<name> <kv>kV - <name> <kv>kV <id>"  (bare id, no label)
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from psse_model_util.model import Model, _fmt_kv

DATA_DIR = Path(__file__).resolve().parent / "data"
TEST_RAWX_FILE = DATA_DIR / "sample_v35.rawx"


@pytest.fixture
def network_with_bus_info():
    net = Model(file_path_or_json=TEST_RAWX_FILE, force_recalculate=True).network
    net.append_bus_info_to_dfs()
    return net


# ---------------------------------------------------------------------------
# _fmt_kv
# ---------------------------------------------------------------------------

class TestFmtKv:
    def test_integral_drops_decimal(self):
        assert _fmt_kv(500.0) == "500kV"

    def test_one_decimal(self):
        assert _fmt_kv(34.5) == "34.5kV"

    def test_strips_trailing_zeros(self):
        assert _fmt_kv(123.450) == "123.45kV"

    def test_nan_is_empty(self):
        assert _fmt_kv(np.nan) == ""


# ---------------------------------------------------------------------------
# derived_name on real sections
# ---------------------------------------------------------------------------

def test_acline_derived_name(network_with_bus_info):
    acline = network_with_bus_info.acline
    assert "derived_name" in acline.columns
    # (151, 152, '1'): NUCPLNT 500kV - MID500 500kV CKT 1  (acline is special: 'CKT' label)
    assert acline.loc[(151, 152, "1"), "derived_name"] == "NUCPLNT 500kV - MID500 500kV CKT 1"


def test_transformer_two_winding_derived_name(network_with_bus_info):
    transformer = network_with_bus_info.transformer
    assert "derived_name" in transformer.columns
    # (101, 151, 0, 'T1'): two-winding, kbus=0 absent -> third bus segment omitted
    assert transformer.loc[(101, 151, 0, "T1"), "derived_name"] == "NUC-A 21.6kV - NUCPLNT 500kV CKT T1"


def test_load_single_bus_derived_name(network_with_bus_info):
    load = network_with_bus_info.load
    assert "derived_name" in load.columns
    # (152, '1'): MID500 500kV - 1
    assert load.loc[(152, "1"), "derived_name"] == "MID500 500kV - 1"


def test_vscdc_is_two_bus_derived_name(network_with_bus_info):
    vscdc = network_with_bus_info.vscdc
    assert "derived_name" in vscdc.columns
    # VDCLINE1: ibus1=3005 (WEST 230), ibus2=3008 (CATDOG 230), id=name
    assert vscdc.loc["VDCLINE1", "derived_name"] == "WEST 230kV - CATDOG 230kV VDCLINE1"
