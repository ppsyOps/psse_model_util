import copy
from collections import namedtuple
from dataclasses import field, make_dataclass
from types import NoneType
from typing import Any

TxNode = namedtuple('TxNode', ['i', 'j', 'k', 'ckt'])
Node = namedtuple('Node', ['i'])


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
