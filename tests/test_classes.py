import pytest
from psse_model_util.common.classes import (ActivePower, Admittance, AreaId, BusId, Capacitance, Current,
                                            IdInt, IdStr, Impedance, Inductance, Name, OwnerId, OwnerFraction,
                                            PowerFactor, Rating, ReactivePower, Resistance, Status, Susceptance,
                                            Voltage, ZoneId, SwShID)


@pytest.mark.parametrize("cls, value", [
    (ActivePower, 100.5),
    (Admittance, (0.1, 0.2)),
    (AreaId, 1),
    (BusId, 1001),
    (Capacitance, 0.001),
    (Current, 500.0),
    (IdInt, 42),
    (IdStr, "ABC123"),
    (Impedance, (0.05, 0.1)),
    (Inductance, 0.1),
    (Name, "Test Name"),
    (OwnerId, 5),
    (OwnerFraction, 0.75),
    (PowerFactor, 0.95),
    (Rating, 1000.0),
    (ReactivePower, 50.5),
    (Resistance, 0.01),
    (Status, 1),
    (Susceptance, 0.005),
    (Voltage, 230.0),
    (ZoneId, 3),
    (SwShID, 10)
])
def test_class_initialization(cls, value):
    """
    Test initialization and string representation for various classes.
    """
    if cls in [Admittance, Impedance]:
        obj = cls(*value)
        assert str(obj) == f"{value[0]} + j{value[1]}"
    else:
        obj = cls(value)
        assert str(obj) == str(value)

    if cls not in [IdStr, Name]:
        if isinstance(value, tuple):
            assert complex(obj) == pytest.approx(complex(*value))
        else:
            assert float(obj) == pytest.approx(float(value))

def test_impedance_initialization():
    """Test the Impedance class initialization and properties."""
    z = Impedance(3, 4)
    assert z.real == 3
    assert z.imag == 4
    assert abs(z) == 5

def test_admittance_initialization():
    """Test the Admittance class initialization and properties."""
    y = Admittance(0.1, 0.2)
    assert y.real == 0.1
    assert y.imag == 0.2
    assert abs(y) == pytest.approx(0.22360679774997896)

@pytest.mark.parametrize("cls, value1, value2", [
    (ActivePower, 10, 5),
    (Admittance, (0.1, 0.2), (0.05, 0.1)),
    (AreaId, 10, 5),
    (BusId, 10, 5),
    (Capacitance, 10, 5),
    (Current, 10, 5),
    (IdInt, 10, 5),
    (Impedance, (0.1, 0.2), (0.05, 0.1)),
    (Inductance, 10, 5),
    (OwnerId, 10, 5),
    (OwnerFraction, 0.5, 0.25),
    (PowerFactor, 0.8, 0.4),
    (Rating, 10, 5),
    (ReactivePower, 10, 5),
    (Resistance, 10, 5),
    (Susceptance, 10, 5),
    (Voltage, 10, 5),
    (ZoneId, 10, 5),
    (SwShID, 10, 5)
])
def test_class_arithmetic(cls, value1, value2):
    """
    Test basic arithmetic operations for numeric classes.
    """
    if cls in [Admittance, Impedance]:
        obj1 = cls(*value1)
        obj2 = cls(*value2)
        result_add = obj1 + obj2
        result_sub = obj1 - obj2
        assert isinstance(result_add, cls)
        assert isinstance(result_sub, cls)
        assert result_add.real == pytest.approx(value1[0] + value2[0])
        assert result_add.imag == pytest.approx(value1[1] + value2[1])
        assert result_sub.real == pytest.approx(value1[0] - value2[0])
        assert result_sub.imag == pytest.approx(value1[1] - value2[1])
    else:
        obj1 = cls(value1)
        obj2 = cls(value2)
        assert obj1 + obj2 == cls(value1 + value2)
        assert obj1 - obj2 == cls(value1 - value2)

def test_status_arithmetic():
    """Test that Status class does not support arithmetic operations."""
    status1 = Status(1)
    status2 = Status(1)
    with pytest.raises(TypeError):
        _ = status1 + status2
    with pytest.raises(TypeError):
        _ = status1 - status2

# ... (rest of the test file remains the same)

def test_idstr_concatenation():
    """Test string concatenation for IdStr class."""
    id1 = IdStr("ABC")
    id2 = IdStr("123")
    assert id1 + id2 == IdStr("ABC123")

def test_name_concatenation():
    """Test string concatenation for Name class."""
    name1 = Name("John")
    name2 = Name("Doe")
    assert name1 + " " + name2 == Name("John Doe")

def test_swshid_inheritance():
    """Test that SwShID inherits from int and behaves like an integer."""
    swsh_id = SwShID(5)
    assert isinstance(swsh_id, int)
    assert swsh_id + 3 == 8
    assert swsh_id * 2 == 10
    assert SwShID(10) / SwShID(2) == 5

if __name__ == "__main__":
    pytest.main()
