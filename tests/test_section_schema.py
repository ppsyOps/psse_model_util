import pytest

from psse_model_util.dataformat.classes import BusId, Name, Voltage
from psse_model_util.dataformat.section_schema import SectionSchema


def test_empty_schema_defaults():
    s = SectionSchema()
    assert s.id_cols == ()
    assert s.bus_cols == ()
    assert s.data_type == {}


def test_explicit_construction_coerces_to_tuples():
    s = SectionSchema(id_cols=["ibus", "loadid"], bus_cols=["ibus"], data_type={"ibus": int})
    assert s.id_cols == ("ibus", "loadid")
    assert s.bus_cols == ("ibus",)
    assert s.data_type == {"ibus": int}


def test_is_frozen():
    import dataclasses
    s = SectionSchema()
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.id_cols = ("x",)


def test_from_template_zips_data_type_list_to_fields():
    template = {
        "fields": ["ibus", "name", "baskv"],
        "data": [],
        "data_type": [BusId, Name, Voltage],
        "bus_cols": ["ibus"],
        "id_cols": ["ibus"],
    }
    s = SectionSchema.from_template(template, fields=["ibus", "name", "baskv"])
    assert s.bus_cols == ("ibus",)
    assert s.id_cols == ("ibus",)
    assert s.data_type == {"ibus": BusId, "name": Name, "baskv": Voltage}


def test_from_template_missing_keys_yield_empty():
    s = SectionSchema.from_template({"fields": ["iarea"], "data": []}, fields=["iarea"])
    assert s.id_cols == ()
    assert s.bus_cols == ()
    assert s.data_type == {}


def test_from_template_uses_actual_fields_for_zip_length():
    # data_type list longer than actual fields -> zip truncates to fields
    template = {"data_type": [int, float, str], "id_cols": ["a"]}
    s = SectionSchema.from_template(template, fields=["a"])
    assert s.data_type == {"a": int}
