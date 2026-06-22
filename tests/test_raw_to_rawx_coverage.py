"""
test_raw_to_rawx_coverage.py — characterization tests targeting previously
uncovered branches of ``psse_model_util.raw_to_rawx``.

These complement ``test_raw_to_rawx.py`` (which focuses on the synthetic
substation block).  Here we drive:

* the public ``raw_file_to_rawx_dict`` entry point against real ``.raw``
  fixtures, in both dict and DataFrame output modes (covers the main parse
  loop, ``_read_syswide`` terminator handling, ``_get_raw_rawx_columns``
  caching, line-type dispatch, EOF handling);
* ``main`` (the module's CLI driver) against the v34/v35 fixture pair;
* helper error/edge branches: ``_get_column_names`` bad-DataFrame ValueError,
  ``_parse_substation_section`` with a real column-mapping DataFrame,
  ``_read_caseid`` padding, ``_raw_to_rawx_section_name`` miss, and
  ``save_rawx_dict_to_json`` TypeError path.

All expected values were derived by running the code (characterization), not
by guessing.  Nothing under ``src/`` is modified and the Model pickle cache is
never touched.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from psse_model_util import raw_to_rawx as r
from psse_model_util.raw_to_rawx import (
    _get_column_names,
    _get_raw_rawx_columns,
    _parse_substation_section,
    _raw_to_rawx_section_name,
    _read_caseid,
    _read_syswide,
    main,
    raw_file_to_rawx_dict,
    save_rawx_dict_to_json,
)

DATA_DIR = Path(__file__).resolve().parent / "data"
RAW34 = DATA_DIR / "sample_34.raw"
RAW35 = DATA_DIR / "sample_v35.raw"
MINIMAL = DATA_DIR / "minimal.raw"


# ---------------------------------------------------------------------------
# Public entry point: raw_file_to_rawx_dict
# ---------------------------------------------------------------------------

def test_raw_file_to_rawx_dict_v34_structure():
    """A real v34 file produces a rawx dict with general + network sections."""
    result = raw_file_to_rawx_dict(RAW34)
    assert set(result.keys()) >= {"general", "network"}
    # version is the full float from the "/ PSS(R)E-34.8" tag, not the integer rev
    assert result["general"]["version"] == 34.8
    # caseid lives under network and carries the revision we asserted on
    assert result["network"]["caseid"]["data"][2] == "34"
    # bus is always present in these fixtures
    assert "bus" in result["network"]


def test_raw_file_to_rawx_dict_v35_structure():
    """A real v35 file resolves version 35 and parses without raising."""
    result = raw_file_to_rawx_dict(RAW35)
    assert result["general"]["version"] == 35.4
    assert result["network"]["caseid"]["data"][2] == "35"


def test_raw_file_to_rawx_dict_dict_mode_default():
    """Default mode returns sections as {'fields', 'data'} dicts, not DataFrames."""
    result = raw_file_to_rawx_dict(MINIMAL)
    bus = result["network"]["bus"]
    assert isinstance(bus, dict)
    assert set(bus.keys()) == {"fields", "data"}
    assert not isinstance(bus, pd.DataFrame)


def test_raw_file_to_rawx_dict_dataframe_mode():
    """return_dataframes=True materializes at least one section as a DataFrame."""
    result = raw_file_to_rawx_dict(MINIMAL, return_dataframes=True)
    df_sections = [
        name for name, val in result["network"].items()
        if isinstance(val, pd.DataFrame)
    ]
    assert df_sections, "expected at least one section rendered as a DataFrame"
    # bus should be one of them and carry its mapped columns
    assert isinstance(result["network"]["bus"], pd.DataFrame)


def test_raw_file_to_rawx_dict_accepts_str_path():
    """The entry point accepts a str path as well as a Path."""
    result = raw_file_to_rawx_dict(str(RAW34))
    assert "network" in result


# ---------------------------------------------------------------------------
# main() — the module CLI driver (covers the big 686-727 block)
# ---------------------------------------------------------------------------

def test_main_both_files_no_save(capsys):
    """main() parses both v34 and v35 fixtures and prints results without saving."""
    main(str(RAW34), str(RAW35), save_json=False)
    out = capsys.readouterr().out
    # main prints 'result' twice (once per file) and never the save-success line
    assert out.count("result") >= 2
    assert "Successfully saved" not in out


def test_main_saves_json(tmp_path, monkeypatch):
    """With save_json=True, main writes JSON into site_temp_dir for each file."""
    # redirect site_temp_dir so we do not pollute the real temp dir
    monkeypatch.setattr(r, "site_temp_dir", tmp_path)
    main(str(RAW34), str(RAW35), save_json=True)
    produced = list(tmp_path.glob("*.json"))
    stems = {p.stem for p in produced}
    assert RAW34.stem in stems
    assert RAW35.stem in stems
    # compact v34 file should be valid JSON and round-trip-loadable
    v34_json = tmp_path / f"{RAW34.stem}.json"
    data = json.loads(v34_json.read_text())
    assert data["general"]["version"] == 34.8


def test_main_only_v34(capsys):
    """Passing an empty v35 path exercises only the first branch of main()."""
    main(str(RAW34), "", save_json=False)
    out = capsys.readouterr().out
    assert "result" in out


# ---------------------------------------------------------------------------
# _read_caseid — field padding + structure
# ---------------------------------------------------------------------------

def test_read_caseid_pads_missing_fields():
    """A short case line is padded out to the full 8-field width."""
    line = "0, 100.00, 34, 0, 1, 60.00 / PSS(R)E-34.8 MON"
    caseid = _read_caseid(line)
    assert caseid["fields"][0] == "ic"
    assert len(caseid["data"]) == len(caseid["fields"]) == 8
    # title1/title2 missing in the source -> padded with empty strings
    assert caseid["data"][-1] == ""
    assert caseid["data"][2] == "34"


# ---------------------------------------------------------------------------
# _get_raw_rawx_columns — load then cached-return path
# ---------------------------------------------------------------------------

def test_get_raw_rawx_columns_loads_and_caches():
    """First call loads the mapping CSV; a second returns the cached frame."""
    # reset module cache to force the load branch
    r.raw_rawx_columns = pd.DataFrame()
    first = _get_raw_rawx_columns(version=34)
    assert isinstance(first, pd.DataFrame)
    assert not first.empty
    # required columns survived the rename/drop
    for col in ("subsection_raw", "field_idx_raw", "field_raw", "field_rawx"):
        assert col in first.columns
    # second call hits the cached-return branch (same object)
    second = _get_raw_rawx_columns(version=34)
    assert second is first


# ---------------------------------------------------------------------------
# _get_column_names — bad DataFrame raises ValueError
# ---------------------------------------------------------------------------

def test_get_column_names_missing_columns_raises():
    bad_df = pd.DataFrame({"foo": [1], "bar": [2]})
    with pytest.raises(ValueError, match="must contain"):
        _get_column_names("BUS DATA", bad_df)


def test_get_column_names_returns_pairs():
    cols = _get_raw_rawx_columns(version=34)
    pairs, raw_names = _get_column_names("BUS DATA", cols)
    assert pairs, "expected non-empty (field_raw, field_rawx) pairs"
    # each entry is a 2-tuple
    assert all(len(p) == 2 for p in pairs)


# ---------------------------------------------------------------------------
# _raw_to_rawx_section_name — hit and miss
# ---------------------------------------------------------------------------

def test_section_name_known():
    assert _raw_to_rawx_section_name("BUS DATA") == "bus"


def test_section_name_unknown_returns_none():
    assert _raw_to_rawx_section_name("NOT A REAL SECTION ZZZ") is None


def test_section_name_none_input():
    # section_raw falsy -> upper() skipped, no match -> None
    assert _raw_to_rawx_section_name("") is None


# ---------------------------------------------------------------------------
# _parse_substation_section — with a real column-mapping DataFrame
# (covers the dict-comprehension success path at 337 and the return at 425)
# ---------------------------------------------------------------------------

def test_parse_substation_with_real_columns_df():
    cols = _get_raw_rawx_columns(version=34)
    lines = [
        "1, 0, SUB_A, 500.0",
        "1, 101, BUS_N, 101, 500.0, 10.0, 500.0",
        "0 / END OF SUBSTATION DATA",
    ]
    data, end_line = _parse_substation_section(lines, 0, raw_rawx_columns=cols)
    assert end_line == 2
    assert len(data["substations"]) == 1
    assert len(data["nodes"]) == 1
    # node carries its parent substation id
    assert "substation_id" in data["nodes"][0]


# ---------------------------------------------------------------------------
# save_rawx_dict_to_json — TypeError (non-serializable) branch
# ---------------------------------------------------------------------------

def test_save_rawx_dict_to_json_type_error(tmp_path, capsys):
    """A non-JSON-serializable value triggers the TypeError branch (no raise)."""
    out = tmp_path / "bad.json"
    # a set is not JSON-serializable -> json.dump raises TypeError, caught+printed
    save_rawx_dict_to_json({"k": {1, 2, 3}}, out)
    captured = capsys.readouterr().out
    assert "Error encoding dictionary to JSON" in captured


# ---------------------------------------------------------------------------
# _read_syswide — stops at the "0 / END OF" terminator (the break branch)
# ---------------------------------------------------------------------------

def test_read_syswide_stops_at_terminator():
    """Lines after the '0 / END OF' marker are not parsed (break branch)."""
    lines = [
        "GENERAL, THRSHZ=0.0001, PQBRAK=0.7",
        "GAUSS, ITMX=100, ACCP=1.6",
        "RATING, 1, \"R1\", \"desc one\"",
        "0 / END OF SYSTEM-WIDE DATA",
        "SHOULD_NOT_BE_READ, X=1",
    ]
    res = _read_syswide(lines)
    assert set(res.keys()) == {"general", "gauss", "rating"}
    assert res["general"]["fields"] == ["thrshz", "pqbrak"]
    assert res["rating"]["data"] == [["1", "R1", "desc one"]]
    # the line after the terminator must NOT have been parsed
    assert "should_not_be_read" not in res
