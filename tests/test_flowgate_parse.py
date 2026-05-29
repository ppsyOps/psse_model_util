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


SIMPLE_MON_TEXT = """\
BUSNAMES
MONITOR FLOWGATE 1600  'Tanners Creek - Dearborn 345kV l/o L765.Marysville-Sorenson'
         BRANCH FROM BUS '05TANNER    345.00' TO BUS '06DEARB1    345.00' CKT Z1
 CONTINGENCY 1600
    OPEN BRANCH FROM BUS '05MARYSVL_RS765.00' TO BUS '05SORENSN_RM765.00' CKT 1
 END
    CA AEP OVEC
    SC PJM
    TP PJM PJM
END
"""


def test_parse_mon_string_one_flowgate(tmp_path):
    from psse_model_util.flowgate import parse_mon_file

    p = tmp_path / "one.mon"
    p.write_text(SIMPLE_MON_TEXT)
    fgs = parse_mon_file(p)

    assert len(fgs) == 1
    fg = fgs[0]
    assert fg.flowgate_id == 1600
    assert fg.sc == "PJM"
    assert fg.description.startswith("Tanners Creek")
    assert len(fg.monitor) == 1
    assert len(fg.contingency) == 1


def test_parse_monitor_element_tokens(tmp_path):
    from psse_model_util.flowgate import parse_mon_file

    p = tmp_path / "mon.mon"
    p.write_text(SIMPLE_MON_TEXT)
    fgs = parse_mon_file(p)

    mon = fgs[0].monitor[0]
    assert mon.role == "monitor"
    assert mon.element_type == "branch"
    # raw_tokens: (from_token, to_token, ckt) for branch
    assert mon.raw_tokens[0] == "05TANNER    345.00"
    assert mon.raw_tokens[1] == "06DEARB1    345.00"
    assert mon.raw_tokens[2] == "Z1"


def test_parse_contingency_element_tokens(tmp_path):
    from psse_model_util.flowgate import parse_mon_file

    p = tmp_path / "c.mon"
    p.write_text(SIMPLE_MON_TEXT)
    fgs = parse_mon_file(p)

    con = fgs[0].contingency[0]
    assert con.role == "contingency"
    assert con.element_type == "branch"
    assert con.raw_tokens[0] == "05MARYSVL_RS765.00"
    assert con.raw_tokens[1] == "05SORENSN_RM765.00"
    assert con.raw_tokens[2] == "1"


MALFORMED_HEADER_MON = """\
MONITOR FLOWGATE 1234 unquoted description
         BRANCH FROM BUS '05TANNER    345.00' TO BUS '06DEARB1    345.00' CKT 1
 CONTINGENCY 1234
    OPEN BRANCH FROM BUS '05TANNER    345.00' TO BUS '06DEARB1    345.00' CKT 2
 END
    SC PJM
END
"""


def test_parse_malformed_monitor_flowgate_header_raises(tmp_path):
    """A MONITOR FLOWGATE line that doesn't match the strict regex must raise,
    not silently fall through to the unknown-line warning."""
    from psse_model_util.flowgate import parse_mon_file

    p = tmp_path / "bad.mon"
    p.write_text(MALFORMED_HEADER_MON)
    with pytest.raises(ValueError, match="malformed MONITOR FLOWGATE"):
        parse_mon_file(p)


REMOVE_MACHINE_MON = """\
MONITOR FLOWGATE 59031  'Clifty Creek-Carrollton 138 (flo) Ghent Unit 3'
         BRANCH FROM BUS '06CLIFTY    138.00' TO BUS '4CARROLLTON 138.00' CKT 1
 CONTINGENCY 59031
    REMOVE MACHINE 3 FROM BUS '1GHENT 3    22.000'
 END
    CA OVEC LGEE
    SC LGEE
    TP PJM LGEE
END
"""


def test_parse_remove_machine(tmp_path):
    from psse_model_util.flowgate import parse_mon_file

    p = tmp_path / "rm.mon"
    p.write_text(REMOVE_MACHINE_MON)
    fgs = parse_mon_file(p)

    assert len(fgs) == 1
    con = fgs[0].contingency[0]
    assert con.role == "contingency"
    assert con.element_type == "generator"
    # raw_tokens: (bus_token, machine_id)
    assert con.raw_tokens[0] == "1GHENT 3    22.000"
    assert con.raw_tokens[1] == "3"


def test_parse_remove_machine_alphanumeric_id(tmp_path):
    """PSS/E machine ids can be alphanumeric (e.g. 'H1')."""
    from psse_model_util.flowgate import parse_mon_file

    mon = REMOVE_MACHINE_MON.replace("REMOVE MACHINE 3 ", "REMOVE MACHINE H1 ")
    p = tmp_path / "rm2.mon"
    p.write_text(mon)
    fgs = parse_mon_file(p)
    assert fgs[0].contingency[0].raw_tokens[1] == "H1"
