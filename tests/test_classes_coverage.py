"""
test_classes_coverage.py — characterization tests for dataformat/classes.py.

Targets the pure, coverable symbols in the module (the ModelDF class is dead
code — its __init__ raises NotImplementedError — and is deliberately untouched):

  - get_builtin_base_type        (lines ~180-209)
  - infer_type                   (lines ~262-288, incl. 282-283)
  - dict_to_dataclass            (lines ~330-340)
  - DictToClassConverter         (lines ~217-224)
  - Admittance / Impedance       (lines ~349, 352, 355, 358, 363, 366, 369, 372)
  - Status                       (lines ~377-379, 382, 385)

Expected values were derived by running the code, not guessed.
"""
from __future__ import annotations

from typing import Any

import pytest

from psse_model_util.dataformat.classes import (
    Admittance,
    DictToClassConverter,
    Impedance,
    Status,
    dict_to_dataclass,
    get_builtin_base_type,
    infer_type,
)

# ---------------------------------------------------------------------------
# get_builtin_base_type
# ---------------------------------------------------------------------------


def test_get_builtin_base_type_builtin_returns_itself():
    # A builtin type's __module__ == 'builtins', so it returns itself (line 192).
    assert get_builtin_base_type(int) is int
    assert get_builtin_base_type(str) is str


def test_get_builtin_base_type_subclass_of_builtin():
    class MyInt(int):
        pass

    # Recurses into bases (lines 195, 202-206) and finds int.
    assert get_builtin_base_type(MyInt) is int


def test_get_builtin_base_type_plain_class_resolves_to_object():
    # A "plain" class has object as its base; object.__module__ == 'builtins',
    # so the recursion returns object rather than None.
    class Plain:
        pass

    assert get_builtin_base_type(Plain) is object


def test_get_builtin_base_type_deep_chain():
    class MyInt(int):
        pass

    class Deeper(MyInt):
        pass

    # Multi-level recursion still resolves to the builtin int.
    assert get_builtin_base_type(Deeper) is int


# ---------------------------------------------------------------------------
# infer_type
# ---------------------------------------------------------------------------


def test_infer_type_none_returns_any():
    assert infer_type(None) is Any


def test_infer_type_scalars():
    assert infer_type(5) is int
    assert infer_type(3.14) is float
    assert infer_type("x") is str
    # bool is a subclass of int; type() reports bool.
    assert infer_type(True) is bool


def test_infer_type_uniform_list():
    assert infer_type([1, 2, 3]) == list[int]


def test_infer_type_uniform_set():
    assert infer_type({"a", "b"}) == set[str]


def test_infer_type_uniform_tuple():
    # Exercises the tuple branch (line 280-281; 282-283 is an unreachable dup).
    assert infer_type((1, 2)) == tuple[int, ...]


def test_infer_type_empty_collections():
    assert infer_type([]) == list[Any]
    assert infer_type(()) == tuple[Any]
    assert infer_type(set()) == set[Any]


def test_infer_type_mixed_list_falls_back():
    # Mixed element types -> the catch-all list[Any] (line 284).
    assert infer_type([1, "a"]) == list[Any]


def test_infer_type_set_of_none():
    # element_type is NoneType -> none_to_any converts to Any.
    assert infer_type({None}) == set[Any]


# ---------------------------------------------------------------------------
# dict_to_dataclass
# ---------------------------------------------------------------------------


def test_dict_to_dataclass_immutable_fields():
    obj = dict_to_dataclass({"a": 123, "name": "foo"})
    assert obj.a == 123
    assert obj.name == "foo"


def test_dict_to_dataclass_mutable_fields_use_factory():
    obj = dict_to_dataclass({"lst": [1, 2], "st": {1, 2}, "dd": {"x": 1}})
    assert obj.lst == [1, 2]
    assert obj.st == {1, 2}
    assert obj.dd == {"x": 1}


# ---------------------------------------------------------------------------
# DictToClassConverter
# ---------------------------------------------------------------------------


def test_dict_to_class_converter_sets_attributes():
    obj = DictToClassConverter({"x": 1, "y": "z"})
    assert obj.x == 1
    assert obj.y == "z"


# ---------------------------------------------------------------------------
# Admittance
# ---------------------------------------------------------------------------


def test_admittance_new_and_str():
    a = Admittance(1.0, 2.0)
    assert a.real == 1.0
    assert a.imag == 2.0
    assert str(a) == "1.0 + j2.0"


def test_admittance_default_imag():
    a = Admittance(3.0)
    assert a.imag == 0.0


def test_admittance_add():
    result = Admittance(1.0, 2.0) + Admittance(3.0, 4.0)
    assert isinstance(result, Admittance)
    assert str(result) == "4.0 + j6.0"


def test_admittance_sub():
    result = Admittance(5.0, 5.0) - Admittance(1.0, 2.0)
    assert isinstance(result, Admittance)
    assert str(result) == "4.0 + j3.0"


# ---------------------------------------------------------------------------
# Impedance
# ---------------------------------------------------------------------------


def test_impedance_new_and_str():
    z = Impedance(1.0, 2.0)
    assert z.real == 1.0
    assert z.imag == 2.0
    assert str(z) == "1.0 + j2.0"


def test_impedance_add():
    result = Impedance(1.0, 1.0) + Impedance(2.0, 3.0)
    assert isinstance(result, Impedance)
    assert str(result) == "3.0 + j4.0"


def test_impedance_sub():
    result = Impedance(5.0, 5.0) - Impedance(1.0, 1.0)
    assert isinstance(result, Impedance)
    assert str(result) == "4.0 + j4.0"


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", [0, 1])
def test_status_valid_values(value):
    s = Status(value)
    assert int(s) == value


def test_status_invalid_value_raises():
    with pytest.raises(ValueError, match="Status must be either 0 or 1"):
        Status(2)


def test_status_add_raises():
    s = Status(1)
    with pytest.raises(TypeError, match="Cannot perform arithmetic"):
        s + 1


def test_status_sub_raises():
    s = Status(1)
    with pytest.raises(TypeError, match="Cannot perform arithmetic"):
        s - 1
