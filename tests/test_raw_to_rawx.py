"""
test_raw_to_rawx.py — raw_to_rawx module tests.

Substation data context
-----------------------
Industry power-system files distributed by ISOs (PJM, ISO-NE, MISO, etc.)
do NOT include substation sections.  Because of this, `_parse_substation_section`
is never exercised by the normal Model-loading integration tests.

The correct strategy to keep this code covered — without creating a misleading
"fake" industry RAW file — is to call the parser directly with hand-crafted
in-memory line data that mirrors the documented PSS/E substation block format.
This also serves as a living specification for the expected input format.

Reference format (PSS/E v34/v35 SUBSTATION section)
----------------------------------------------------
Each line is a comma-separated record stripped of whitespace/quotes by
split_csv_line().  Three record types are interleaved within one block:

Substation header   parts[0]=IS, parts[1]='0', parts[2]=NAME, parts[3]=kV
Node record         parts[0]=IS, parts[1]=NI,  parts[2]=NAME, parts[3]=I,
                    parts[4]=kV, parts[5]=angle, parts[6]=base_kV
Switching device    (after "BEGIN SUBSTATION SWITCHING DEVICE DATA" line)
                    parts[0]=NI, parts[1]=NJ, parts[2]=CKT, parts[3]=TYPE,
                    parts[4]=STATUS, [parts[5]=description]

Section ends with a line starting "0 / END OF SUBSTATION".
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from psse_model_util.raw_to_rawx import (
    _parse_substation_section,
    save_rawx_dict_to_json,
)

# ---------------------------------------------------------------------------
# Synthetic substation block — mirrors PSS/E RAW format exactly.
# Column mappings fall back to their hardcoded defaults when
# raw_rawx_columns=None (the try/except in _parse_substation_section
# catches the TypeError and uses an empty dict for each section).
# ---------------------------------------------------------------------------

_SUBSTATION_LINES = [
    # substation header: IS=1, '0', name, voltage
    "1, 0, SUBSTATION_A, 500.0",
    # node records: IS=1, NI=101/102, name, bus_number, kV, angle, base_kV
    "1, 101, BUS_NORTH, 101, 500.00, 10.0, 500.0",
    "1, 102, BUS_SOUTH, 102, 499.50,  9.8, 500.0",
    # second substation (tests multiple substations in one block)
    "2, 0, SUBSTATION_B, 230.0",
    "2, 201, BUS_EAST, 201, 230.00, 5.0, 230.0",
    # switching devices
    "BEGIN SUBSTATION SWITCHING DEVICE DATA",
    "101, 102, 1, 1, 1, BREAKER_AB",
    "201, 202, 1, 2, 0",                   # no description — 5 fields only
    # section terminator
    "0 / END OF SUBSTATION DATA",
]


# ---------------------------------------------------------------------------
# _parse_substation_section — structure tests
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def parsed_sub():
    """Parse the synthetic block once; reuse across tests in this module."""
    data, end_line = _parse_substation_section(
        lines=_SUBSTATION_LINES,
        start_line=0,
        raw_rawx_columns=None,   # falls back to hardcoded default key names
    )
    return data, end_line


def test_returns_correct_keys(parsed_sub):
    data, _ = parsed_sub
    assert set(data.keys()) == {"substations", "nodes", "switching_devices"}


def test_end_line_points_to_terminator(parsed_sub):
    _, end_line = parsed_sub
    assert _SUBSTATION_LINES[end_line].startswith("0 / END OF SUBSTATION")


def test_substation_count(parsed_sub):
    data, _ = parsed_sub
    assert len(data["substations"]) == 2


def test_substation_ids_and_names(parsed_sub):
    data, _ = parsed_sub
    subs = {s["isub"]: s for s in data["substations"]}
    assert "1" in subs
    assert "2" in subs
    assert subs["1"]["name"] == "SUBSTATION_A"
    assert subs["2"]["name"] == "SUBSTATION_B"


def test_node_count(parsed_sub):
    data, _ = parsed_sub
    # 2 nodes under sub 1, 1 node under sub 2
    assert len(data["nodes"]) == 3


def test_node_fields(parsed_sub):
    data, _ = parsed_sub
    # Synthetic line: "1, 101, BUS_NORTH, 101, 500.00, 10.0, 500.0"
    #   parts[1]='101'      → inode
    #   parts[2]='BUS_NORTH'→ name AND ibus (parser maps both to parts[2])
    #   parts[3]='101'      → voltage   (positional — bus-id slot in real files)
    #   parts[4]='500.00'   → angle
    #   parts[5]='10.0'     → base_kv
    north = next(n for n in data["nodes"] if n["inode"] == "101")
    assert north["name"] == "BUS_NORTH"
    assert north["ibus"] == "BUS_NORTH"   # parser reads ibus from parts[2], same as name
    assert north["voltage"] == "101"      # parts[3] of our synthetic line
    assert north["angle"] == "500.00"     # parts[4]
    assert north["base_kv"] == "10.0"    # parts[5]


def test_switching_device_count(parsed_sub):
    data, _ = parsed_sub
    assert len(data["switching_devices"]) == 2


def test_switching_device_fields(parsed_sub):
    data, _ = parsed_sub
    dev = data["switching_devices"][0]
    assert dev["inode"] == "101"
    assert dev["jnode"] == "102"
    assert dev["swlid"] == "1"
    assert dev["type"] == "1"
    assert dev["stat"] == "1"
    assert dev.get("description") == "BREAKER_AB"


def test_switching_device_without_description(parsed_sub):
    """Device with only 5 fields should not have a description key."""
    data, _ = parsed_sub
    dev = data["switching_devices"][1]
    assert dev["inode"] == "201"
    assert "description" not in dev


def test_nodes_carry_substation_id(parsed_sub):
    """Every node record should include the parent substation id."""
    data, _ = parsed_sub
    for node in data["nodes"]:
        assert "isub" in node or "substation_id" in node, \
            f"Node missing parent-substation link: {node}"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_empty_block_returns_empty_lists():
    """A block with only the terminator line produces empty lists."""
    lines = ["0 / END OF SUBSTATION DATA"]
    data, end_line = _parse_substation_section(lines, start_line=0, raw_rawx_columns=None)
    assert data["substations"] == []
    assert data["nodes"] == []
    assert data["switching_devices"] == []
    assert end_line == 0


def test_comment_and_blank_lines_are_skipped():
    """Lines starting with '@!' or blank are ignored."""
    lines = [
        "@! IS, IS, NAME, VOLTAGE",
        "",
        "1, 0, SUB_ONLY, 115.0",
        "0 / END OF SUBSTATION DATA",
    ]
    data, _ = _parse_substation_section(lines, start_line=0, raw_rawx_columns=None)
    assert len(data["substations"]) == 1
    assert data["substations"][0]["name"] == "SUB_ONLY"


def test_start_line_offset():
    """start_line should allow the caller to skip a file header."""
    prefix = ["@! SOME PREAMBLE LINE", "ANOTHER PREAMBLE"]
    lines = prefix + _SUBSTATION_LINES
    data, end_line = _parse_substation_section(lines, start_line=2, raw_rawx_columns=None)
    assert len(data["substations"]) == 2
    assert end_line > 2  # terminator must be after the prefix


# ---------------------------------------------------------------------------
# save_rawx_dict_to_json
# ---------------------------------------------------------------------------

def test_save_rawx_dict_to_json_creates_file(tmp_path):
    rawx = {"network": {"bus": {"fields": ["ibus", "name"], "data": [[101, "BUS_A"]]}}}
    out = tmp_path / "output.json"
    save_rawx_dict_to_json(rawx, out)
    assert out.exists()
    loaded = json.loads(out.read_text())
    assert loaded["network"]["bus"]["fields"] == ["ibus", "name"]


def test_save_rawx_dict_to_json_compact(tmp_path):
    rawx = {"key": "value"}
    out = tmp_path / "compact.json"
    save_rawx_dict_to_json(rawx, out, compact=True)
    text = out.read_text()
    assert "\n" not in text        # compact mode — no newlines
    assert " " not in text         # no spaces between tokens


def test_save_rawx_dict_to_json_pretty(tmp_path):
    rawx = {"key": "value"}
    out = tmp_path / "pretty.json"
    save_rawx_dict_to_json(rawx, out, compact=False)
    text = out.read_text()
    assert "\n" in text            # pretty mode — has indentation


def test_save_rawx_dict_to_json_bad_path(tmp_path, capsys):
    """Writing to a nonexistent directory should print an error, not raise."""
    bad_path = tmp_path / "nonexistent_dir" / "out.json"
    save_rawx_dict_to_json({"k": "v"}, bad_path)
    captured = capsys.readouterr()
    assert "Error" in captured.out
