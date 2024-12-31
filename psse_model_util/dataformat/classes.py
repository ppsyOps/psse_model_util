from collections import namedtuple
from dataclasses import make_dataclass, field
from types import NoneType
from typing import get_type_hints, List
from typing import Any, Type, List, Set, Tuple, Dict
import datetime  # Make sure to import datetime
import copy
import builtins
import inspect

import pandas as pd

TxNode = namedtuple('TxNode', ['i', 'j', 'k', 'ckt'])
Node = namedtuple('Node', ['i'])


class ModelDF(pd.DataFrame):
    def __init__(self, *args, meta: dict = None, **kwargs):
        raise NotImplementedError
        # TODO: Inherting from pd.DataFrame did not work well.
        #       Consider having a "df" argument instead.
        super().__init__(*args, **kwargs)
        self.meta: dict[str, Any] = meta or dict()

    @property
    def meta(self):
        return self._metadata

    @meta.setter
    def meta(self, new_dict):
        assert isinstance(new_dict, dict), f'new_dict must be a dict, not {type(new_dict)}.'
        if 'data_type' in new_dict and not isinstance(new_dict['data_type'], dict):
            assert 'fields' in new_dict, f'Cannot set new_dict["data_type"] in ModelDF unless it is a dict or new_dict["field"] exists.'
            assert len(new_dict['fields']) == len(new_dict['data_type'])
            new_dict['data_type'] = {k: v for k, v in zip(new_dict['fields'], new_dict['data_type'])}
        self._metadata = new_dict

    @property
    def _constructor(self):
        return ModelDF

    @property
    def bus_cols(self) -> List[str]:
        self.meta.setdefault('bus_cols', [])
        return self.meta['bus_cols']

    @bus_cols.setter
    def bus_cols(self, cols: List[str]):
        self.meta['bus_cols'] = cols

    @property
    def id_cols(self) -> List[str]:
        self.meta.setdefault('id_cols', [])
        return self.meta['id_cols']

    @id_cols.setter
    def id_cols(self, cols: List[str]):
        self.meta['id_cols'] = cols

    @property
    def data_type(self) -> dict[str, Any]:
        self.meta.setdefault('data_type', {})
        return self.meta['data_type']

    @data_type.setter
    def data_type(self, types: List[str] | dict[str, Any]):
        if not isinstance(types, dict):
            types = {k: v for k, v in zip(self.columns, types)}
        self.meta['data_type'] = types

    def copy(self, deep: bool = True) -> 'ModelDF':
        """Create a deep copy of the ModelDF instance, including meta data."""
        if deep:
            new_obj = ModelDF(super().copy(deep=True), meta=copy.deepcopy(self.meta))
        else:
            new_obj = ModelDF(super().copy(deep=False), meta=self.meta.copy())
        new_obj._metadata = copy.deepcopy(self._metadata)
        return new_obj

    def __getitem__(self, key):
        result = super().__getitem__(key)
        if isinstance(result, pd.DataFrame):
            result = self._constructor(result).__finalize__(self)
        return result

    def __finalize__(self, other, method=None, **kwargs):
        if isinstance(other, ModelDF):
            self.meta = copy.deepcopy(other.meta)
        return self

    def merge(self, *args, **kwargs):
        result = super().merge(*args, **kwargs)
        result = self._constructor(result).__finalize__(self)
        return result

    def query(self, expr, *args, **kwargs):
        result = super().query(expr, *args, **kwargs)
        result = self._constructor(result).__finalize__(self)
        return result

    def loc(self, *args, **kwargs):
        result = super().loc(*args, **kwargs)
        if isinstance(result, pd.DataFrame):
            result = self._constructor(result).__finalize__(self)
        return result

    def iloc(self, *args, **kwargs):
        result = super().iloc(*args, **kwargs)
        if isinstance(result, pd.DataFrame):
            result = self._constructor(result).__finalize__(self)
        return result

    def head(self, *args, **kwargs):
        result = super().head(*args, **kwargs)
        result = self._constructor(result).__finalize__(self)
        return result

    def tail(self, *args, **kwargs):
        result = super().tail(*args, **kwargs)
        result = self._constructor(result).__finalize__(self)
        return result

    def sample(self, *args, **kwargs):
        result = super().sample(*args, **kwargs)
        result = self._constructor(result).__finalize__(self)
        return result

    def drop(self, *args, **kwargs):
        result = super().drop(*args, **kwargs)
        result = self._constructor(result).__finalize__(self)
        return result

    def reset_index(self, *args, **kwargs):
        result = super().reset_index(*args, **kwargs)
        result = self._constructor(result).__finalize__(self)
        return result

    def sort_values(self, *args, **kwargs):
        result = super().sort_values(*args, **kwargs)
        result = self._constructor(result).__finalize__(self)
        return result

    def sort_index(self, *args, **kwargs):
        result = super().sort_index(*args, **kwargs)
        result = self._constructor(result).__finalize__(self)
        return result

    def filter(self, *args, **kwargs):
        result = super().filter(*args, **kwargs)
        result = self._constructor(result).__finalize__(self)
        return result

    def rename(self, *args, **kwargs):
        result = super().rename(*args, **kwargs)
        result = self._constructor(result).__finalize__(self)
        return result

    def join(self, *args, **kwargs):
        result = super().join(*args, **kwargs)
        result = self._constructor(result).__finalize__(self)
        return result

    def combine_first(self, other):
        result = super().combine_first(other)
        result = self._constructor(result).__finalize__(self)
        return result

    def update(self, other, *args, **kwargs):
        super().update(other, *args, **kwargs)
        self.meta.update(other.meta if isinstance(other, ModelDF) else {})
        return self

    def set_index(self, *args, **kwargs):
        result = super().set_index(*args, **kwargs)
        result = self._constructor(result).__finalize__(self)
        return result

    def reindex(self, *args, **kwargs):
        result = super().reindex(*args, **kwargs)
        result = self._constructor(result).__finalize__(self)
        return result


def get_builtin_base_type(cls):
    """
    Recursively determine the built-in Python type that a custom class inherits from.

    Args:
    cls: The class to check.

    Returns:
    The built-in base type, or None if no built-in base type is found.
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
    """
    A converter class that initializes itself with attributes based on a provided dictionary.
    """

    def __init__(self, input_dict: dict):
        """
        Initializes a new instance with attributes corresponding to the input dictionary's keys and values.

        :param input_dict: A dictionary where keys represent attribute names and values represent attribute values.
        """
        for key, value in input_dict.items():
            setattr(self, key, value)


def infer_type(value):
    """
    Infers the Python type for a given value, with specific handling for collections.

    This function examines the input value to determine its Python type. For collections
    such as lists, sets, and tuples, the function attempts to infer a more specific type
    based on the types of the elements contained within the collection. For example,
    a list containing only integers would result in the type `List[int]`. The function
    handles sets and tuples in a similar manner.

    For simple types (int, float, str, bool) and datetime objects, the function directly
    returns the type of the value. For more complex types or when a specific type cannot
    be confidently inferred, the function defaults to returning `typing.Any`.

    :param value: The value for which the type is to be inferred.
    :return: The inferred Python type of the input value. For collections with uniform
             element types, returns a generic type (e.g., `List[int]`). Defaults to
             `typing.Any` for complex types or mixed-element collections.
    :rtype: Type

    Example usage:

    .. code-block:: python

        print(infer_type([1, 2, 3]))  # Output: typing.List[int]
        print(infer_type({"a", "b"}))  # Output: typing.Set[str]
        print(infer_type((1, 2)))  # Output: typing.Tuple[int, ...]
        print(infer_type(123))  # Output: <class 'int'>
        print(infer_type(datetime.datetime.now()))  # Output: <class 'datetime.datetime'>

    Note:
    The function assumes uniformity in the types of elements within collections. For
    mixed-type collections, the specific collection type (List, Set, Tuple) without
    element type information is returned.
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
    """
    Converts a dictionary into a dynamically created dataclass instance.

    This function dynamically creates a dataclass with fields corresponding to the keys
    of the input dictionary. Field types are inferred based on the values associated
    with each key. For mutable types (lists, sets, tuples, and dicts), a `default_factory`
    is used to ensure unique default values for each instance. For immutable types and
    complex types where inference defaults to `typing.Any`, the `default` parameter is
    used.

    :param input_dict: A dictionary where each key-value pair represents the name and value
                       of an attribute in the resulting dataclass. The key is a string
                       representing the attribute name, and the value is used to infer
                       the attribute's type and initialize the attribute.
    :type input_dict: dict
    :return: An instance of the dynamically created dataclass, with attributes corresponding
             to the input dictionary's key-value pairs.
    :rtype: dataclasses.dataclass

    Example usage:

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

    Note:
    The function uses type inference for setting up dataclass fields. It defaults to `typing.Any`
    for complex types or where type inference is not feasible.
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
    pass


class Admittance(complex):
    def __new__(cls, real, imag=0.0):
        return super().__new__(cls, real, imag)

    def __str__(self):
        return f"{self.real} + j{self.imag}"

    def __add__(self, other):
        return Admittance(self.real + other.real, self.imag + other.imag)

    def __sub__(self, other):
        return Admittance(self.real - other.real, self.imag - other.imag)


class Impedance(complex):
    def __new__(cls, real, imag=0.0):
        return super().__new__(cls, real, imag)

    def __str__(self):
        return f"{self.real} + j{self.imag}"

    def __add__(self, other):
        return Impedance(self.real + other.real, self.imag + other.imag)

    def __sub__(self, other):
        return Impedance(self.real - other.real, self.imag - other.imag)


class Status(int):
    def __new__(cls, value):
        if value not in (0, 1):
            raise ValueError("Status must be either 0 or 1")
        return super().__new__(cls, value)

    def __add__(self, other):
        raise TypeError("Cannot perform arithmetic operations on Status objects")

    def __sub__(self, other):
        raise TypeError("Cannot perform arithmetic operations on Status objects")


class Angle(float):  # theta
    pass


class AreaId(int):
    pass


class SwShID(int):
    pass


class BusId(int):  # fields: I, J, K, IBUS, JBUS
    pass


class Capacitance(float):  # C
    pass


class Current(float):  # I
    pass


class IdInt(int):
    pass


class IdStr(str):
    pass


class Inductance(float):  # L
    pass


class Name(str):
    pass


class PowerFactor(float):  # PF
    pass


class Resistance(float):  # R
    pass


class Reactance(float):  # X
    pass


class OwnerFraction(float):
    pass


class OwnerId(int):
    pass


class PerUnit(int):
    pass


class Rating(float):
    pass


class ReactivePower(float):
    pass


class Susceptance(float):  # B
    pass


class Voltage(float):  # V
    pass


class ZoneId(int):
    pass


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