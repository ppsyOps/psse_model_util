import pytest
from datetime import datetime
from typing import Any, List, Set

from psse_model_util.dataformat.classes import dict_to_dataclass, DictToClassConverter, infer_type


def test_dict_to_class_converter():
    test_dict = {
        "a": 123,
        "prop2": 456,
        "list_example": [1, 2, 3],
        "set_example": {"a", "b"},
        "complex_example": {"nested": "dict"},
        "dtdt_example": datetime.now()
    }

    class_obj = DictToClassConverter(test_dict)
    assert class_obj.a == 123
    assert class_obj.prop2 == 456
    assert class_obj.list_example == [1, 2, 3]
    assert class_obj.set_example == {"a", "b"}
    assert class_obj.complex_example == {"nested": "dict"}
    assert class_obj.dtdt_example == test_dict["dtdt_example"]


@pytest.mark.parametrize("input_value, expected_type", [
    ([1, 2, 3], list[int]),
    ({"a", "b"}, set[str]),
    ((1, 2), tuple[int, ...]),
    (123, int),
    (datetime.now(), datetime),
    ([1, 2, 3, 4.5, True], list[Any]),
    ([1, 2, '3', 4.5, True], list[Any]),
    ([1, 2, 3, 4.5, datetime.now()], list[Any]),
    ([1, 2, 3, 4.5, datetime.now(), True], list[Any]),
    ([1, 2, 3, 4.5, datetime.now(), True, None], list[Any]),
    ([1, 2, 3, 4.5, datetime.now(), True, None, object()], list[Any]),
    ([], list[Any]),
    (set(), set[Any]),
    ((), tuple[Any, ...]),
    ({}, dict[Any, Any]),
    (None, Any),
    ([], list[Any]),
    ([None], list[Any]),
    ([None, None], list[Any]),
    ([None, None, None], list[Any]),
])


def test_infer_type(input_value, expected_type):
    assert infer_type(input_value) == expected_type


def test_dict_to_dataclass_basic():
    input_dict = {
        "int_field": 123,
        "float_field": 3.14,
        "str_field": "hello",
        "bool_field": True
    }
    result = dict_to_dataclass(input_dict)

    assert result.int_field == 123
    assert isinstance(result.int_field, int)
    assert result.float_field == 3.14
    assert isinstance(result.float_field, float)
    assert result.str_field == "hello"
    assert isinstance(result.str_field, str)
    assert result.bool_field is True
    assert isinstance(result.bool_field, bool)


def test_dict_to_dataclass_collections():
    input_dict = {
        "list_field": [1, 2, 3],
        "set_field": {"a", "b", "c"},
        "tuple_field": (4, 5, 6)
    }
    result = dict_to_dataclass(input_dict)

    assert result.list_field == [1, 2, 3]
    assert isinstance(result.list_field, List)
    assert result.set_field == {"a", "b", "c"}
    assert isinstance(result.set_field, Set)
    assert result.tuple_field == (4, 5, 6)
    assert isinstance(result.tuple_field, tuple)


def test_dict_to_dataclass_nested():
    input_dict = {
        "nested_dict": {"key": "value"},
        "nested_list": [{"a": 1}, {"b": 2}]
    }
    result = dict_to_dataclass(input_dict)

    assert result.nested_dict == {"key": "value"}
    assert isinstance(result.nested_dict, dict)
    assert result.nested_list == [{"a": 1}, {"b": 2}]
    assert isinstance(result.nested_list, List)


def test_dict_to_dataclass_datetime():
    now = datetime.now()
    input_dict = {
        "date_field": now
    }
    result = dict_to_dataclass(input_dict)

    assert result.date_field == now
    assert isinstance(result.date_field, datetime)


def test_dict_to_dataclass_empty():
    input_dict = {}
    result = dict_to_dataclass(input_dict)

    assert hasattr(result, '__annotations__')  # The dataclass will have __annotations__, even if empty
    assert result.__annotations__ == {}  # But the annotations should be an empty dict
    assert vars(result) == {}  # The instance should have no attributes


def test_dict_to_dataclass_mixed_types():
    input_dict = {
        "mixed_list": [1, "two", 3.0],
        "mixed_set": {1, "two", 3.0}
    }
    result = dict_to_dataclass(input_dict)

    assert result.mixed_list == [1, "two", 3.0]
    assert isinstance(result.mixed_list, List)
    assert result.mixed_set == {1, "two", 3.0}
    assert isinstance(result.mixed_set, Set)


def test_dict_to_dataclass_mutable_default():
    input_dict = {
        "mutable_list": [1, 2, 3]
    }
    result1 = dict_to_dataclass(input_dict)
    result2 = dict_to_dataclass(input_dict)

    result1.mutable_list.append(4)
    assert result1.mutable_list == [1, 2, 3, 4]
    assert result2.mutable_list == [1, 2, 3]  # result2 should not be affected

    # Test that new instances get a fresh copy
    result3 = dict_to_dataclass(input_dict)
    assert result3.mutable_list == [1, 2, 3]  # New instance should have the original list


def test_dict_to_dataclass_multiple_instances():
    input_dict = {
        "mutable_list": [1, 2, 3],
        "mutable_dict": {"a": 1}
    }
    result1 = dict_to_dataclass(input_dict)
    result2 = dict_to_dataclass(input_dict)

    result1.mutable_list.append(4)
    result1.mutable_dict["b"] = 2

    assert result1.mutable_list == [1, 2, 3, 4]
    assert result1.mutable_dict == {"a": 1, "b": 2}
    assert result2.mutable_list == [1, 2, 3]
    assert result2.mutable_dict == {"a": 1}

if __name__ == "__main__":
    pytest.main()

if __name__ == "__main__":
    pytest.main()
