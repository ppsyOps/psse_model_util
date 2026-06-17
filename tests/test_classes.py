"""
test_classes.py — dataformat.classes tests.

Ported from tests/legacy_tests/dataformat/test_classes.py; updated for the
current API and project layout after refactoring.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from psse_model_util.dataformat.classes import DictToClassConverter, dict_to_dataclass, infer_type

# ---------------------------------------------------------------------------
# DictToClassConverter
# ---------------------------------------------------------------------------

def test_dict_to_class_converter():
    now = datetime.now()
    test_dict = {
        "a": 123,
        "prop2": 456,
        "list_example": [1, 2, 3],
        "set_example": {"a", "b"},
        "complex_example": {"nested": "dict"},
        "dtdt_example": now,
    }
    obj = DictToClassConverter(test_dict)
    assert obj.a == 123
    assert obj.prop2 == 456
    assert obj.list_example == [1, 2, 3]
    assert obj.set_example == {"a", "b"}
    assert obj.complex_example == {"nested": "dict"}
    assert obj.dtdt_example == now


# ---------------------------------------------------------------------------
# infer_type
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("expected_type, input_value", [
    (list[int],    [1, 2, 3]),
    (set[str],     {"a", "b"}),
    (tuple[int, ...], (1, 2)),
    (int,          123),
    (datetime,     datetime.now()),
    (list[Any],    [1, 2, 3, 4.5, True]),
    (list[Any],    [1, 2, "3", 4.5, True]),
    (list[Any],    [1, 2, 3, 4.5, datetime.now()]),
    (list[Any],    [1, 2, 3, 4.5, datetime.now(), True]),
    (list[Any],    [1, 2, 3, 4.5, datetime.now(), True, None]),
    (list[Any],    [1, 2, 3, 4.5, datetime.now(), True, None, object()]),
    (list[Any],    []),
    (set[Any],     set()),
    (tuple[Any],   ()),
    (dict,         {}),
    (Any,          None),
    (list[Any],    []),
    (list[Any],    [None]),
    (list[Any],    [None, None]),
    (list[Any],    [None, None, None]),
])
def test_infer_type(expected_type, input_value):
    assert infer_type(input_value) == expected_type


# ---------------------------------------------------------------------------
# dict_to_dataclass
# ---------------------------------------------------------------------------

def test_dict_to_dataclass_basic():
    result = dict_to_dataclass({"int_field": 123, "float_field": 3.14,
                                "str_field": "hello", "bool_field": True})
    assert result.int_field == 123
    assert isinstance(result.int_field, int)
    assert result.float_field == 3.14
    assert isinstance(result.float_field, float)
    assert result.str_field == "hello"
    assert isinstance(result.str_field, str)
    assert result.bool_field is True
    assert isinstance(result.bool_field, bool)


def test_dict_to_dataclass_collections():
    result = dict_to_dataclass({"list_field": [1, 2, 3],
                                "set_field": {"a", "b", "c"},
                                "tuple_field": (4, 5, 6)})
    assert result.list_field == [1, 2, 3]
    assert isinstance(result.list_field, list)
    assert result.set_field == {"a", "b", "c"}
    assert isinstance(result.set_field, set)
    assert result.tuple_field == (4, 5, 6)
    assert isinstance(result.tuple_field, tuple)


def test_dict_to_dataclass_nested():
    result = dict_to_dataclass({"nested_dict": {"key": "value"},
                                "nested_list": [{"a": 1}, {"b": 2}]})
    assert result.nested_dict == {"key": "value"}
    assert isinstance(result.nested_dict, dict)
    assert result.nested_list == [{"a": 1}, {"b": 2}]
    assert isinstance(result.nested_list, list)


def test_dict_to_dataclass_datetime():
    now = datetime.now()
    result = dict_to_dataclass({"date_field": now})
    assert result.date_field == now
    assert isinstance(result.date_field, datetime)


def test_dict_to_dataclass_empty():
    result = dict_to_dataclass({})
    assert vars(result) == {}


def test_dict_to_dataclass_mixed_types():
    result = dict_to_dataclass({"mixed_list": [1, "two", 3.0],
                                "mixed_set": {1, "two", 3.0}})
    assert result.mixed_list == [1, "two", 3.0]
    assert isinstance(result.mixed_list, list)
    assert result.mixed_set == {1, "two", 3.0}
    assert isinstance(result.mixed_set, set)


def test_dict_to_dataclass_mutable_default():
    input_dict = {"mutable_list": [1, 2, 3]}
    result1 = dict_to_dataclass(input_dict)
    result2 = dict_to_dataclass(input_dict)

    result1.mutable_list.append(4)
    assert result1.mutable_list == [1, 2, 3, 4]
    assert result2.mutable_list == [1, 2, 3]

    result3 = dict_to_dataclass(input_dict)
    assert result3.mutable_list == [1, 2, 3]


def test_dict_to_dataclass_multiple_instances():
    input_dict = {"mutable_list": [1, 2, 3], "mutable_dict": {"a": 1}}
    result1 = dict_to_dataclass(input_dict)
    result2 = dict_to_dataclass(input_dict)

    result1.mutable_list.append(4)
    result1.mutable_dict["b"] = 2

    assert result1.mutable_list == [1, 2, 3, 4]
    assert result1.mutable_dict == {"a": 1, "b": 2}
    assert result2.mutable_list == [1, 2, 3]
    assert result2.mutable_dict == {"a": 1}
