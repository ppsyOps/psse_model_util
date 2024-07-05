import psse_model_util
import pytest
import os


def test_read_raw34():
    filename = "data/sample.raw"
    data = psse_model_util.read_case_raw(filename)

    assert len(data["BUS"]) == 42
    assert isinstance(data["LOAD"][0]["I"], int)


def test_read_raw34_minimal():
    filename = "data/minimal.raw"
    data = psse_model_util.read_case_raw(filename)

    assert len(data["BUS"]) == 2
    assert isinstance(data["LOAD"][0]["I"], int)


def test_read_raw35():
    filename = "data/sample_v35.raw"
    data = psse_model_util.read_case_raw(filename)

    assert len(data["BUS"]) == 48
    assert isinstance(data["LOAD"][0]["I"], int)


def test_read_seq():
    filename = "data/example.seq"
    data = psse_model_util.read_case_seq(filename)

    assert isinstance(data, dict)
    assert len(data["GENERATOR"]) == 6
    assert data["GENERATOR"][0]["I"] == 101

