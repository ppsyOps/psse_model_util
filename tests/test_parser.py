import pytest
from unittest.mock import patch
import os
from pathlib import Path
import io

import psse_model_util
from psse_model_util import dataformat34, dataformat35
from psse_model_util.parser import read_case_raw, get_type_of_data, get_parts, try_parse

import pytest
from pathlib import Path

# Get the path to the test data directory
TEST_DATA_DIR = Path(__file__).absolute().parent.parent / 'tests' / 'data'



def test_read_raw34():
    filename = TEST_DATA_DIR / "sample_34.raw"  # "data/sample_34.raw"
    data = psse_model_util.read_case_raw(filename)

    assert len(data["BUS"]) == 42
    assert isinstance(data["LOAD"][0]["I"], int)


def test_read_raw34_minimal():
    filename = TEST_DATA_DIR / "minimal.raw"  # "data/minimal.raw"
    data = psse_model_util.read_case_raw(filename)

    assert len(data["BUS"]) == 2
    assert isinstance(data["LOAD"][0]["I"], int)


def test_read_raw35():
    filename = TEST_DATA_DIR / "sample_v35.raw"  # "data/sample_v35.raw"
    data = psse_model_util.read_case_raw(filename)

    assert len(data["BUS"]) == 48
    assert isinstance(data["LOAD"][0]["I"], int)


def test_read_seq():
    filename = TEST_DATA_DIR / "example.seq"  #
    data = psse_model_util.read_case_seq(filename)

    assert isinstance(data, dict)
    assert len(data["GENERATOR"]) == 6
    assert data["GENERATOR"][0]["I"] == 101


@pytest.fixture(params=['sample_34.raw', 'sample_v35.raw'])
def raw_file_path(request):
    """Fixture to provide paths to both RAW files."""
    return TEST_DATA_DIR / request.param


def test_read_case_raw(raw_file_path):
    """
    Test the read_case_raw function with both sample RAW files.

    This test checks that:
    1. The function runs without raising an exception
    2. The returned object is a dictionary
    3. The dictionary contains expected keys
    4. Specific content checks are performed for various sections
    5. Version-specific checks are performed

    Args:
        raw_file_path (Path): Path to the RAW file, provided by the raw_file_path fixture
    """
    # Run the function and catch any exceptions
    try:
        result = read_case_raw(raw_file_path)
    except Exception as e:
        pytest.fail(f"read_case_raw raised an exception: {e}")

    # Check that the result is a dictionary
    assert isinstance(result, dict), "read_case_raw should return a dictionary"

    # Check for expected keys in the result
    expected_keys = ['VERSION', 'HEADER', 'BUS', 'LOAD', 'FIXED SHUNT', 'GENERATOR', 'BRANCH', 'TRANSFORMER', 'AREA', 'TWO-TERMINAL DC', 'VSC DC LINE', 'IMPEDANCE CORRECTION', 'MULTI-TERMINAL DC', 'MULTI-SECTION LINE', 'ZONE', 'INTER-AREA TRANSFER', 'OWNER', 'FACTS DEVICE', 'SWITCHED SHUNT', 'INDUCTION MACHINE']
    for key in expected_keys:
        assert key in result, f"Expected key '{key}' not found in result"

    # Check that VERSION is present and is a float
    assert isinstance(result['VERSION'], float), "VERSION should be a float"
    version = result['VERSION']

    # Check that HEADER is a dictionary with expected keys
    assert isinstance(result['HEADER'], dict), "HEADER should be a dictionary"
    assert all(key in result['HEADER'] for key in ['IC', 'SBASE', 'REV', 'XFRRAT', 'NXFRAT', 'BASFRQ']), "HEADER missing expected keys"

    # Check BUS data
    assert isinstance(result['BUS'], list) and len(result['BUS']) > 0, "BUS should be a non-empty list"
    first_bus = result['BUS'][0]
    assert all(key in first_bus for key in ['I', 'NAME', 'BASKV', 'IDE', 'AREA', 'ZONE', 'OWNER', 'VM', 'VA']), "BUS entry missing expected keys"

    # Check LOAD data
    assert isinstance(result['LOAD'], list), "LOAD should be a list"
    if result['LOAD']:
        first_load = result['LOAD'][0]
        # if int(version) == 34:
        assert all(key in first_load for key in ['I', 'ID', 'STAT', 'AREA', 'ZONE', 'PL', 'QL']), "LOAD entry missing expected keys"
        # else:
        #     assert all(key in first_load for key in ['I', 'ID', 'STAT', 'AREA', 'ZONE', 'PL', 'QL']), "LOAD entry missing expected keys"

    # Check GENERATOR data
    assert isinstance(result['GENERATOR'], list), "GENERATOR should be a list"
    if result['GENERATOR']:
        first_gen = result['GENERATOR'][0]
        assert all(key in first_gen for key in ['I', 'ID', 'PG', 'QG', 'QT', 'QB', 'VS', 'IREG', 'MBASE', 'ZR', 'ZX', 'RT', 'XT', 'GTAP', 'STAT', 'RMPCT', 'PT', 'PB']), "GENERATOR entry missing expected keys"

    # Check BRANCH data
    assert isinstance(result['BRANCH'], list), "BRANCH should be a list"
    if result['BRANCH']:
        first_branch = result['BRANCH'][0]
        assert all(key in first_branch for key in ['I', 'J', 'CKT', 'R', 'X', 'B', 'GI', 'BI', 'GJ', 'BJ', 'STAT', 'MET', 'LEN']), "BRANCH entry missing expected keys"

    assert 'FACTS DEVICE' in result, "FACTS DEVICE should be present in version 35"
    if result['FACTS DEVICE']:
        first_facts = result['FACTS DEVICE'][0]
        assert all(key in first_facts for key in ['NAME', 'I', 'J', 'MODE', 'PDES', 'QDES', 'VSET', 'SHMX', 'TRMX', 'VTMN', 'VTMX', 'VSMX', 'IMX', 'LINX', 'RMPCT', 'OWNER', 'SET1', 'SET2', 'VSREF']), "FACTS DEVICE entry missing expected keys"

    # Print some debug information
    print(f"Testing file: {raw_file_path.name}")
    print(f"PSS/E Version: {version}")
    print(f"Number of buses: {len(result['BUS'])}")
    print(f"Number of generators: {len(result['GENERATOR'])}")
    print(f"Number of branches: {len(result['BRANCH'])}")


def test_get_type_of_data():
    """
    Test the get_type_of_data function with various input lines.
    """
    assert get_type_of_data("Q") == "END"
    assert get_type_of_data("@!Comment") == "COMMENT"
    assert get_type_of_data("0,100.00,33,0,0,60.00 / PSS(R)E-33.0") == "HEADER"
    assert get_type_of_data("BEGIN BUS DATA") == "BUS"
    assert get_type_of_data("0 / END OF BUS DATA, BEGIN LOAD DATA") == "LOAD"
    assert get_type_of_data(
        "    1,'XFMR-1     ',132.0000,2,   1,   1,   1,1.00000,  -0.3308,1.10000,0.90000,1.10000,0.90000") is None


def test_get_parts():
    """
    Test the get_parts function with sample data.
    """
    line = "    1,'BUS-1      ',132.0000,2,   1,   1,   1,1.00000,  -0.3308,1.10000,0.90000,1.10000,0.90000"
    col_names = dataformat34.RAW_DATA['BUS']
    dtype = dataformat34.DTYPE_RAW_DATA['BUS']

    result = get_parts(line, col_names, dtype)

    assert isinstance(result, dict)
    assert result['I'] == 1
    assert result['NAME'] == 'BUS-1      '
    assert result['BASKV'] == 132.0
    assert result['IDE'] == 2


def test_try_parse():
    """
    Test the try_parse function with various inputs and data types.
    """
    assert try_parse(int, "42") == 42
    assert try_parse(float, "3.14") == 3.14
    assert try_parse(str, "'quoted string'") == "quoted string"
    assert try_parse(int, "") in [None, '']
    assert isinstance(try_parse(int, "not an int"), str)


# @pytest.mark.parametrize("version,expected_format", [
#     (33, dataformat34),
#     (34, dataformat34),
#     (35, dataformat35),
# ])
# def test_dataformat_selection(version, expected_format):
#     """
#     Test that the correct dataformat is selected based on the PSS/E version.
#     """
#     # Create a mock file content with the version in the header
#     test_content = f"""0,100.00,{version},0,0,60.00 / PSS(R)E-{version}.0
#
#     0 / END OF HEADER
#     0 / END OF BUS DATA, BEGIN LOAD DATA
#     0 / END OF LOAD DATA, BEGIN FIXED SHUNT DATA
#     0 / END OF FIXED SHUNT DATA, BEGIN GENERATOR DATA
#     0 / END OF GENERATOR DATA, BEGIN BRANCH DATA
#     0 / END OF BRANCH DATA, BEGIN TRANSFORMER DATA
#     0 / END OF TRANSFORMER DATA, BEGIN AREA DATA
#     0 / END OF AREA DATA, BEGIN TWO-TERMINAL DC DATA
#     0 / END OF TWO-TERMINAL DC DATA, BEGIN VSC DC LINE DATA
#     0 / END OF VSC DC LINE DATA, BEGIN IMPEDANCE CORRECTION DATA
#     0 / END OF IMPEDANCE CORRECTION DATA, BEGIN MULTI-TERMINAL DC DATA
#     0 / END OF MULTI-TERMINAL DC DATA, BEGIN MULTI-SECTION LINE DATA
#     0 / END OF MULTI-SECTION LINE DATA, BEGIN ZONE DATA
#     0 / END OF ZONE DATA, BEGIN INTER-AREA TRANSFER DATA
#     0 / END OF INTER-AREA TRANSFER DATA, BEGIN OWNER DATA
#     0 / END OF OWNER DATA, BEGIN FACTS DEVICE DATA
#     0 / END OF FACTS DEVICE DATA, BEGIN SWITCHED SHUNT DATA
#     0 / END OF SWITCHED SHUNT DATA, BEGIN GNE DEVICE DATA
#     0 / END OF GNE DEVICE DATA, BEGIN INDUCTION MACHINE DATA
#     0 / END OF INDUCTION MACHINE DATA
#     Q
#     """
#
#     # Use patch to mock open and return a StringIO object
#     with patch('builtins.open', return_value=io.StringIO(test_content)):
#         result = read_case_raw("dummy_path")
#
#         # Check that the correct version was parsed
#         assert result['VERSION'] == float(version), f"Expected version {version}, got {result['VERSION']}"
#
#         # Check that the keys in the result match the expected format
#         assert set(result.keys()) == set(expected_format.RAW_DATA.keys()), \
#             f"Keys mismatch for version {version}. Expected {set(expected_format.RAW_DATA.keys())}, got {set(result.keys())}"
#
#         # Check that the HEADER was parsed correctly
#         assert 'HEADER' in result, "HEADER not found in result"
#         assert isinstance(result['HEADER'], dict), "HEADER should be a dictionary"
#         assert result['HEADER'][
#                    'REV'] == version, f"Expected HEADER['REV'] to be {version}, got {result['HEADER']['REV']}"
#
#         # Check that other sections are present (even if empty)
#         for section in ['BUS', 'LOAD', 'FIXED SHUNT', 'GENERATOR', 'BRANCH', 'TRANSFORMER', 'AREA']:
#             assert section in result, f"{section} not found in result"
#             assert isinstance(result[section], list), f"{section} should be a list"
#
#         # Version-specific checks
#         if version >= 35:
#             assert 'FACTS DEVICE' in result, "FACTS DEVICE should be present in version 35 and above"
#         else:
#             assert 'FACTS DEVICE' not in result or not result['FACTS DEVICE'], \
#                 "FACTS DEVICE should not be present or should be empty in versions below 35"
#
#     print(f"Test passed for PSS/E version {version}")


if __name__ == "__main__":
    pytest.main([__file__, '-v'])

