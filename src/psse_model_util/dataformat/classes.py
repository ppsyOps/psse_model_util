"""Domain data types and dict/dataclass helpers.

This module provides the building blocks used to give RAWX/RAW model data a typed,
self-describing shape:

* A family of small "newtype" domain classes (``Voltage``, ``Reactance``,
  ``Status``, ``Admittance``, etc.) that subclass a Python builtin and tag a value
  with its power-system meaning.
* Helper utilities for reflecting over and constructing objects from plain
  dictionaries: :func:`get_builtin_base_type`, :func:`infer_type`,
  :func:`dict_to_dataclass`, and :class:`DictToClassConverter`.
"""
from __future__ import annotations

import copy
from collections import namedtuple
from dataclasses import field, make_dataclass
from types import NoneType
from typing import Any

TxNode = namedtuple('TxNode', ['i', 'j', 'k', 'ckt'])
Node = namedtuple('Node', ['i'])


def get_builtin_base_type(cls):
    """Recursively determine the builtin Python type that a class inherits from.

    Args:
        cls: The class to check.

    Returns:
        The builtin base type, or ``None`` if no builtin base type is found.
    """
    # Check if the class is already a built-in type
    if cls.__module__ == 'builtins':
        return cls

    # Get the base classes
    bases = cls.__bases__

    # If there are no base classes, return None
    if not bases:
        return None

    # Check each base class
    for base in bases:
        # Recursively check the base class
        builtin_type = get_builtin_base_type(base)
        if builtin_type:
            return builtin_type

    # If no built-in type is found in any base class, return None
    return None


class DictToClassConverter:
    """A converter that sets instance attributes from a provided dictionary."""

    def __init__(self, input_dict: dict):
        """Initialize an instance with attributes from the input dictionary.

        Args:
            input_dict: A dictionary whose keys become attribute names and whose
                values become the corresponding attribute values.
        """
        for key, value in input_dict.items():
            setattr(self, key, value)


def infer_type(value):
    """Infer the Python type for a given value, with handling for collections.

    For collections such as lists, sets, and tuples, the function attempts to infer a
    more specific type based on the types of the contained elements; for example, a
    list containing only integers yields ``list[int]``. For simple types (int, float,
    str, bool) and other objects it returns the value's type directly. For ``None`` or
    when a specific type cannot be confidently inferred, it defaults to ``typing.Any``.

    Args:
        value: The value for which the type is to be inferred.

    Returns:
        The inferred Python type of the input value. For collections with uniform
        element types, returns a parametrized generic (e.g. ``list[int]``). Defaults
        to ``typing.Any`` for ``None`` or mixed-element collections.

    Note:
        The function assumes uniformity in the element types within collections. For
        mixed-type collections, ``list[Any]`` is returned.

    Examples:
        .. code-block:: python

            print(infer_type([1, 2, 3]))  # Output: typing.List[int]
            print(infer_type({"a", "b"}))  # Output: typing.Set[str]
            print(infer_type((1, 2)))  # Output: typing.Tuple[int, ...]
            print(infer_type(123))  # Output: <class 'int'>
            print(infer_type(datetime.datetime.now()))  # Output: <class 'datetime.datetime'>
    """
    def none_to_any(value):
        if value is None or value is NoneType or isinstance(value, type(None)):
            return Any
        return value

    # Basic type inference; extend this as needed
    if isinstance(value, type(None)):
        return Any
    if isinstance(value, (list, tuple, set)):
        # Assume all elements are of the same type for simplicity
        if not value:
            return type(value)[Any]
        element_type = type(list(value)[0])
        if all(isinstance(x, element_type) for x in value):
            if isinstance(value, list):
                return list[none_to_any(element_type)]  # type: ignore
            elif isinstance(value, set):
                return set[none_to_any(element_type)]  # type: ignore
            elif isinstance(value, tuple):
                return tuple[none_to_any(element_type), ...]  # type: ignore
            elif isinstance(value, tuple):
                return tuple[none_to_any(element_type), ...]  # type: ignore
        return list[Any]
    else:  # isinstance(value, (int, float, str, bool)):
        return type(value)
    # Default to Any for complex types or empty sequences
    return Any


def dict_to_dataclass(input_dict: dict) -> Any:
    """Convert a dictionary into a dynamically created dataclass instance.

    A dataclass is created with one field per key of the input dictionary. Field types
    are taken from the type of each value. For mutable types (lists, sets, and dicts) a
    ``default_factory`` is used so each instance gets a unique deep copy of the default;
    immutable types use the ``default`` parameter.

    Args:
        input_dict: A dictionary where each key-value pair becomes the name and default
            value of an attribute on the resulting dataclass. The key is the attribute
            name and the value provides both the field type and its default.

    Returns:
        An instance of the dynamically created dataclass, with attributes corresponding
        to the input dictionary's key-value pairs.

    Examples:
        .. code-block:: python

            my_dict = {
                "a": 123,
                "prop2": 456,
                "list_example": [1, 2, 3],
            }

            dataclass_obj = dict_to_dataclass(my_dict)
            print(dataclass_obj.a)  # Output: 123
            print(dataclass_obj.prop2)  # Output: 456
            print(dataclass_obj.list_example)  # Output: [1, 2, 3]
    """
    fields = []
    for key, value in input_dict.items():
        if isinstance(value, (list, set, dict)):
            # Use default_factory for mutable types
            fields.append((key, type(value), field(default_factory=lambda v=value: copy.deepcopy(v))))
        else:
            # Use default for immutable types
            fields.append((key, type(value), field(default=value)))

    DynamicDataClass = make_dataclass('DynamicDataClass', fields)
    return DynamicDataClass()


class ActivePower(float):
    """Active (real) power, P, in MW."""


class Admittance(complex):
    """Complex admittance, Y = G + jB, in per-unit."""

    def __new__(cls, real, imag=0.0):
        return super().__new__(cls, real, imag)

    def __str__(self):
        return f"{self.real} + j{self.imag}"

    def __add__(self, other):
        return Admittance(self.real + other.real, self.imag + other.imag)

    def __sub__(self, other):
        return Admittance(self.real - other.real, self.imag - other.imag)


class Impedance(complex):
    """Complex impedance, Z = R + jX, in per-unit."""

    def __new__(cls, real, imag=0.0):
        return super().__new__(cls, real, imag)

    def __str__(self):
        return f"{self.real} + j{self.imag}"

    def __add__(self, other):
        return Impedance(self.real + other.real, self.imag + other.imag)

    def __sub__(self, other):
        return Impedance(self.real - other.real, self.imag - other.imag)


class Status(int):
    """In-service status flag: 0 (out of service) or 1 (in service)."""

    def __new__(cls, value):
        if value not in (0, 1):
            raise ValueError("Status must be either 0 or 1")
        return super().__new__(cls, value)

    def __add__(self, other):
        raise TypeError("Cannot perform arithmetic operations on Status objects")

    def __sub__(self, other):
        raise TypeError("Cannot perform arithmetic operations on Status objects")


class Angle(float):
    """Angle, theta, in degrees."""


class AreaId(int):
    """Area identifier (area number)."""


class SwShID(int):
    """Switched shunt identifier."""


class BusId(int):
    """Bus number identifier (e.g. the I, J, K, IBUS, JBUS fields)."""


class Capacitance(float):
    """Capacitance, C, in farads."""


class Current(float):
    """Current, I, in amperes."""


class IdInt(int):
    """Generic integer identifier."""


class IdStr(str):
    """Generic string identifier (e.g. a circuit or equipment id)."""


class Inductance(float):
    """Inductance, L, in henries."""


class Name(str):
    """Equipment or entity name."""


class PowerFactor(float):
    """Power factor, PF, dimensionless."""


class Resistance(float):
    """Resistance, R, in per-unit."""


class Reactance(float):
    """Reactance, X, in per-unit."""


class OwnerFraction(float):
    """Ownership fraction, dimensionless (0.0-1.0)."""


class OwnerId(int):
    """Owner identifier (owner number)."""


class PerUnit(int):
    """A per-unit quantity (normalized to a base)."""


class Rating(float):
    """Equipment rating, in MVA."""


class ReactivePower(float):
    """Reactive power, Q, in MVAr."""


class Susceptance(float):
    """Susceptance, B, in per-unit."""


class Voltage(float):
    """Voltage, V, in kV or per-unit depending on the field."""


class ZoneId(int):
    """Zone identifier (zone number)."""


if __name__ == '__main__':
    t = infer_type({None,})
    print(t)

    # # Example usage
    # my_dict = {
    #     "a": 123,
    #     "prop2": 456,
    #     "list_example": [1, 2, 3],
    #     "set_example": {"a", "b"},
    #     "complex_example": {"nested": "dict"},
    #     "dtdt_example": datetime.datetime.now()
    # }
    #
    # # Example DictToClassConverter
    # class_obj = DictToClassConverter(my_dict)
    # print(class_obj, type(class_obj))
    # print(class_obj.a, type(class_obj.a))
    # print(class_obj.prop2, type(class_obj.prop2))
    # print(class_obj.list_example, type(class_obj.list_example))
    # print(class_obj.set_example, type(class_obj.set_example))
    # print(class_obj.dtdt_example, type(class_obj.dtdt_example))
    #
    # # Example dict_to_dataclass
    # dataclass_obj = dict_to_dataclass(my_dict)
    # print('\n\n')
    # print(dataclass_obj, type(dataclass_obj))
    # print(dataclass_obj.a, type(dataclass_obj.a))
    # print(dataclass_obj.prop2, type(dataclass_obj.prop2))
    # print(dataclass_obj.list_example, type(dataclass_obj.list_example))
    # print(dataclass_obj.set_example, type(dataclass_obj.set_example))
    # print(dataclass_obj.dtdt_example, type(dataclass_obj.dtdt_example))
