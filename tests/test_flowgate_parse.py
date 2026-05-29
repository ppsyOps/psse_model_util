"""Tests for psse_model_util.flowgate parser stage."""
from pathlib import Path

import pytest

DATA_DIR = Path(__file__).resolve().parent / "data"


def test_module_imports_and_has_constants():
    from psse_model_util import flowgate

    assert flowgate.DEFAULT_HOPS == 4
    assert flowgate.DEFAULT_KV_MIN == 160.0
    assert flowgate.DEFAULT_KV_MAX == 765.0
    assert flowgate.DEFAULT_GEN_MIN_MW == 15.0
    assert flowgate.DEFAULT_SC == "PJM"
    assert flowgate.KV_KEY_DECIMALS == 3


def test_dataclasses_exist():
    from psse_model_util.flowgate import Flowgate, FlowgateElement, ResolvedSeed

    fge = FlowgateElement(
        flowgate_id=1, role="monitor", element_type="branch", raw_tokens=("a",)
    )
    fg = Flowgate(
        flowgate_id=1, description="d", sc="PJM", monitor=[fge], contingency=[]
    )
    rs = ResolvedSeed(
        flowgate_id=1,
        role="monitor",
        element_type="branch",
        seed_buses=frozenset({101, 102}),
        raw_tokens=("a",),
    )

    assert fge.role == "monitor"
    assert fg.sc == "PJM"
    assert 101 in rs.seed_buses


def test_split_bus_token_basic():
    from psse_model_util.flowgate import _split_bus_token

    name, kv = _split_bus_token("05TANNER    345.00")
    assert name == "05TANNER"
    assert kv == 345.00


def test_split_bus_token_strips_quotes():
    from psse_model_util.flowgate import _split_bus_token

    name, kv = _split_bus_token("'05TANNER    345.00'")
    assert name == "05TANNER"
    assert kv == 345.00


def test_split_bus_token_preserves_decimal():
    from psse_model_util.flowgate import _split_bus_token

    name, kv = _split_bus_token("'SOMEBUS     69.125'")
    assert name == "SOMEBUS"
    assert kv == 69.125


def test_split_bus_token_name_with_special_chars():
    """Real PSS/E names contain semicolons and digits, e.g. 'STATELINE; R345.00'."""
    from psse_model_util.flowgate import _split_bus_token

    name, kv = _split_bus_token("'STATELINE; R345.00'")
    assert name == "STATELINE; R"
    assert kv == 345.00


def test_split_bus_token_rejects_wrong_length():
    from psse_model_util.flowgate import _split_bus_token

    with pytest.raises(ValueError, match="bus token"):
        _split_bus_token("too short")
