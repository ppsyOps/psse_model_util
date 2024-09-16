import pytest
import json
import tempfile
from pathlib import Path
from psse_model_util.common.json_util import load_and_clean_json

@pytest.fixture
def temp_json_file():
    """Fixture to create a temporary JSON file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as temp_file:
        yield temp_file.name
    Path(temp_file.name).unlink()  # Delete the file after the test

def test_load_and_clean_json_valid(temp_json_file):
    """Test load_and_clean_json with a valid JSON file."""
    json_content = '{"name": "John", "age": 30}'
    with open(temp_json_file, 'w') as f:
        f.write(json_content)

    result = load_and_clean_json(temp_json_file)
    assert result == {"name": "John", "age": 30}

def test_load_and_clean_json_with_control_chars(temp_json_file):
    """Test load_and_clean_json with a JSON file containing control characters."""
    json_content = '{"name": "John\u0000Doe", "age": 30}'
    with open(temp_json_file, 'w') as f:
        f.write(json_content)

    result = load_and_clean_json(temp_json_file)
    assert result == {"name": "John\u0000Doe", "age": 30}

def test_load_and_clean_json_with_float(temp_json_file):
    """Test load_and_clean_json with a JSON file containing a float ending with a period."""
    json_content = '{"price": 19.}'
    with open(temp_json_file, 'w') as f:
        f.write(json_content)

    result = load_and_clean_json(temp_json_file)
    assert result == {"price": 19.0}

def test_load_and_clean_json_invalid(temp_json_file):
    """Test load_and_clean_json with an invalid JSON file."""
    json_content = '{"name": "John", "age": }'  # Missing value for "age"
    with open(temp_json_file, 'w') as f:
        f.write(json_content)

    with pytest.raises(json.JSONDecodeError):
        load_and_clean_json(temp_json_file)

def test_load_and_clean_json_empty_file(temp_json_file):
    """Test load_and_clean_json with an empty file."""
    with open(temp_json_file, 'w') as f:
        f.write('')

    with pytest.raises(json.JSONDecodeError):
        load_and_clean_json(temp_json_file)

def test_load_and_clean_json_complex(temp_json_file):
    """Test load_and_clean_json with a more complex JSON structure."""
    json_content = '''{
        "name": "John Doe",
        "age": 30,
        "is_student": false,
        "grades": [95.5, 88., 92.0],
        "address": {
            "street": "123 Main St",
            "city": "Anytown",
            "zip": "12345"
        }
    }'''
    with open(temp_json_file, 'w') as f:
        f.write(json_content)

    result = load_and_clean_json(temp_json_file)
    expected = {
        "name": "John Doe",
        "age": 30,
        "is_student": False,
        "grades": [95.5, 88.0, 92.0],
        "address": {
            "street": "123 Main St",
            "city": "Anytown",
            "zip": "12345"
        }
    }
    assert result == expected

def test_load_and_clean_json_with_multiple_issues(temp_json_file):
    """Test load_and_clean_json with multiple issues that need cleaning."""
    json_content = '''{
        "name": "John\u0001Doe",
        "age": 30,
        "salary": 50000.,
        "notes": "Contains\\ttab and\\nnewline",
        "data": [1., 2., 3.]
    }'''
    with open(temp_json_file, 'w') as f:
        f.write(json_content)

    result = load_and_clean_json(temp_json_file)
    expected = {
        "name": "John\u0001Doe",
        "age": 30,
        "salary": 50000.0,
        "notes": "Contains\ttab and\nnewline",
        "data": [1.0, 2.0, 3.0]
    }
    assert result == expected

if __name__ == "__main__":
    pytest.main()