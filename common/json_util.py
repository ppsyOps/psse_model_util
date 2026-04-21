import json
import re


def clean_invalid_json_characters(json_string):
    """
    Cleans the JSON string by escaping invalid control characters and fixing floating-point numbers.

    Args:
        json_string (str): The original JSON string.

    Returns:
        str: Cleaned JSON string.
    """
    # Escape all control characters except for \t, \n, and \r
    json_string = re.sub(
        r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]',
        lambda match: f"\\u{ord(match.group()):04x}",
        json_string
    )

    # Fix floating-point numbers ending with a period
    json_string = re.sub(r'(\d+)\.\s*([,\]\}])', r'\1.0\2', json_string)

    return json_string


def load_and_clean_json(file_path):
    """
    Loads and cleans the JSON file before parsing.

    Args:
        file_path (str): Path to the JSON file.

    Returns:
        dict: Parsed JSON data.

    Raises:
        json.JSONDecodeError: If the JSON is invalid after cleaning.
    """
    with open(file_path, 'r', encoding='utf-8') as file:
        raw_data = file.read()
        clean_data = clean_invalid_json_characters(raw_data)

    try:
        data = json.loads(clean_data)
    except json.JSONDecodeError as e:
        print(f"JSON decoding error: {e}")
        print(f"Error occurred near: {clean_data[max(0, e.pos - 50):e.pos + 50]}")
        raise

    return data