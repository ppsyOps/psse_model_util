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
    assert flowgate.KV_KEY_DECIMALS == 3


def test_dataclasses_exist():
    from psse_model_util.flowgate import Flowgate, FlowgateElement, ResolvedSeed

    fge = FlowgateElement(
        flowgate_id=1, role="monitor", element_type="branch", raw_tokens=("a",)
    )
    fg = Flowgate(
        flowgate_id=1, description="d", sc="SCA", monitor=[fge], contingency=[]
    )
    rs = ResolvedSeed(
        flowgate_id=1,
        role="monitor",
        element_type="branch",
        seed_buses=frozenset({101, 102}),
        raw_tokens=("a",),
    )

    assert fge.role == "monitor"
    assert fg.sc == "SCA"
    assert 101 in rs.seed_buses


def test_flowgate_element_rejects_bad_role():
    from psse_model_util.flowgate import FlowgateElement

    with pytest.raises(ValueError, match="role must be one of"):
        FlowgateElement(
            flowgate_id=1, role="bogus", element_type="branch", raw_tokens=("a",)
        )


def test_flowgate_element_rejects_bad_element_type():
    from psse_model_util.flowgate import FlowgateElement

    with pytest.raises(ValueError, match="element_type must be one of"):
        FlowgateElement(
            flowgate_id=1, role="monitor", element_type="bus", raw_tokens=("a",)
        )


def test_resolved_seed_rejects_bad_role():
    from psse_model_util.flowgate import ResolvedSeed

    with pytest.raises(ValueError, match="role must be one of"):
        ResolvedSeed(
            flowgate_id=1,
            role="bogus",
            element_type="branch",
            seed_buses=frozenset({1}),
            raw_tokens=("a",),
        )


def test_resolved_seed_rejects_bad_element_type():
    from psse_model_util.flowgate import ResolvedSeed

    with pytest.raises(ValueError, match="element_type must be one of"):
        ResolvedSeed(
            flowgate_id=1,
            role="monitor",
            element_type="3w",
            seed_buses=frozenset({1}),
            raw_tokens=("a",),
        )


def test_split_bus_token_basic():
    from psse_model_util.flowgate import _split_bus_token

    name, kv = _split_bus_token("NUCPLNT     500.00")
    assert name == "NUCPLNT"
    assert kv == 500.00


def test_split_bus_token_strips_quotes():
    from psse_model_util.flowgate import _split_bus_token

    name, kv = _split_bus_token("'NUCPLNT     500.00'")
    assert name == "NUCPLNT"
    assert kv == 500.00


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
MONITOR FLOWGATE 1600  'NUCPLNT - MID500 500kV l/o EAST500-SUB500'
         BRANCH FROM BUS 'NUCPLNT     500.00' TO BUS 'MID500      500.00' CKT Z1
 CONTINGENCY 1600
    OPEN BRANCH FROM BUS 'EAST500     500.00' TO BUS 'SUB500      500.00' CKT 1
 END
    CA SYN SYN
    SC SCA
    TP SCA SCA
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
    assert fg.sc == "SCA"
    assert fg.description.startswith("NUCPLNT")
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
    assert mon.raw_tokens[0] == "NUCPLNT     500.00"
    assert mon.raw_tokens[1] == "MID500      500.00"
    assert mon.raw_tokens[2] == "Z1"


def test_parse_contingency_element_tokens(tmp_path):
    from psse_model_util.flowgate import parse_mon_file

    p = tmp_path / "c.mon"
    p.write_text(SIMPLE_MON_TEXT)
    fgs = parse_mon_file(p)

    con = fgs[0].contingency[0]
    assert con.role == "contingency"
    assert con.element_type == "branch"
    assert con.raw_tokens[0] == "EAST500     500.00"
    assert con.raw_tokens[1] == "SUB500      500.00"
    assert con.raw_tokens[2] == "1"


MALFORMED_HEADER_MON = """\
MONITOR FLOWGATE 1234 unquoted description
         BRANCH FROM BUS 'NUCPLNT     500.00' TO BUS 'MID500      500.00' CKT 1
 CONTINGENCY 1234
    OPEN BRANCH FROM BUS 'NUCPLNT     500.00' TO BUS 'MID500      500.00' CKT 2
 END
    SC SCA
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
MONITOR FLOWGATE 59031  'MID230-DOWNTN 230 (flo) NUC-A Unit 1'
         BRANCH FROM BUS 'MID230      230.00' TO BUS 'DOWNTN      230.00' CKT 1
 CONTINGENCY 59031
    REMOVE MACHINE 3 FROM BUS 'NUC-A       21.600'
 END
    CA SYN SYN
    SC SCB
    TP SCA SCB
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
    assert con.raw_tokens[0] == "NUC-A       21.600"
    assert con.raw_tokens[1] == "3"


def test_parse_remove_machine_alphanumeric_id(tmp_path):
    """PSS/E machine ids can be alphanumeric (e.g. 'H1')."""
    from psse_model_util.flowgate import parse_mon_file

    mon = REMOVE_MACHINE_MON.replace("REMOVE MACHINE 3 ", "REMOVE MACHINE H1 ")
    p = tmp_path / "rm2.mon"
    p.write_text(mon)
    fgs = parse_mon_file(p)
    assert fgs[0].contingency[0].raw_tokens[1] == "H1"


def test_parse_remove_machine_outside_contingency_raises(tmp_path):
    """A REMOVE MACHINE line in the wrong state must raise, not silently warn."""
    from psse_model_util.flowgate import parse_mon_file

    bad = """\
MONITOR FLOWGATE 1234  'malformed FG'
         REMOVE MACHINE 1 FROM BUS 'MID230      230.00'
         BRANCH FROM BUS 'MID230      230.00' TO BUS 'DOWNTN      230.00' CKT 1
 CONTINGENCY 1234
 END
    SC SCA
END
"""
    p = tmp_path / "bad.mon"
    p.write_text(bad)
    with pytest.raises(ValueError, match="REMOVE MACHINE outside CONTINGENCY"):
        parse_mon_file(p)


def test_parse_malformed_remove_machine_line_raises(tmp_path):
    """A REMOVE MACHINE line missing the FROM BUS token must raise."""
    from psse_model_util.flowgate import parse_mon_file

    bad = """\
MONITOR FLOWGATE 1234  'malformed FG'
         BRANCH FROM BUS 'MID230      230.00' TO BUS 'DOWNTN      230.00' CKT 1
 CONTINGENCY 1234
    REMOVE MACHINE 1 GARBAGE NOT A BUS
 END
    SC SCA
END
"""
    p = tmp_path / "bad2.mon"
    p.write_text(bad)
    with pytest.raises(ValueError, match="malformed REMOVE MACHINE"):
        parse_mon_file(p)


MULTI_FG_MON = """\
MONITOR FLOWGATE 100  'desc A'
         BRANCH FROM BUS 'NUCPLNT     500.00' TO BUS 'MID500      500.00' CKT 1
 CONTINGENCY 100
    OPEN BRANCH FROM BUS 'EAST500     500.00' TO BUS 'SUB500      500.00' CKT 1
 END
    SC SCA
END

MONITOR FLOWGATE 200  'desc B'
         BRANCH FROM BUS 'NUCPLNT     500.00' TO BUS 'MID500      500.00' CKT 2
 CONTINGENCY 200
    OPEN BRANCH FROM BUS 'EAST230     230.00' TO BUS 'SUB230      230.00' CKT 1
    OPEN BRANCH FROM BUS 'SUB230      230.00' TO BUS 'FACTS TE    230.00' CKT 1
 END
    SC SCB
END
"""


def test_parse_multiple_flowgates(tmp_path):
    from psse_model_util.flowgate import parse_mon_file

    p = tmp_path / "multi.mon"
    p.write_text(MULTI_FG_MON)
    fgs = parse_mon_file(p)
    assert [fg.flowgate_id for fg in fgs] == [100, 200]
    assert [fg.sc for fg in fgs] == ["SCA", "SCB"]


def test_parse_multi_element_contingency(tmp_path):
    """A CONTINGENCY block can contain multiple OPEN BRANCH lines."""
    from psse_model_util.flowgate import parse_mon_file

    p = tmp_path / "multi.mon"
    p.write_text(MULTI_FG_MON)
    fgs = parse_mon_file(p)
    assert len(fgs[1].contingency) == 2
    assert fgs[1].contingency[0].raw_tokens[2] == "1"
    assert fgs[1].contingency[1].raw_tokens[0] == "SUB230      230.00"


def test_filter_by_sc(tmp_path):
    from psse_model_util.flowgate import filter_by_sc, parse_mon_file

    p = tmp_path / "multi.mon"
    p.write_text(MULTI_FG_MON)
    fgs = parse_mon_file(p)

    sca_only = filter_by_sc(fgs, sc="SCA")
    assert [fg.flowgate_id for fg in sca_only] == [100]


def test_synthetic_fixture_parses():
    from psse_model_util.flowgate import parse_mon_file

    fgs = parse_mon_file(DATA_DIR / "synthetic_flowgates.mon")
    assert [fg.flowgate_id for fg in fgs] == [1001, 1002, 1003, 9001]
    # FG 1003 contingency should be a generator (REMOVE MACHINE)
    assert fgs[2].contingency[0].element_type == "generator"
    # FG 9001 should have SC SCB
    assert fgs[3].sc == "SCB"


def test_split_bus_token_kv_with_trailing_space():
    """Regression: kV field padded with trailing space (e.g. '21.60 ' from f-string
    `f"{21.6:<6.2f}"`) must not be stripped — the token is exactly 18 chars by
    construction, and the inner-field `.strip()` handles the kV padding cleanly."""
    from psse_model_util.flowgate import _split_bus_token

    name, kv = _split_bus_token("'NUC-A       21.60 '")
    assert name == "NUC-A"
    assert kv == 21.60

    name, kv = _split_bus_token("'BUSNAME      13.8 '")
    assert name == "BUSNAME"
    assert kv == 13.8
