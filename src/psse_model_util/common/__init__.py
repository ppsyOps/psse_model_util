"""Common package utilities for psse_model_util.

Provides shared helpers used across the package, including ``multi_replace``
for applying multiple string substitutions in sequence.
"""

from __future__ import annotations


def multi_replace(string: str, replacements: dict[str, str]):
    """Replace occurrences of substrings in a string based on a dict of replacements.

    Iterates over each key-value pair in ``replacements``. Each key is a
    substring of ``string`` that should be replaced by its corresponding value.
    Replacements are applied sequentially and the modified string is returned.

    Args:
        string: The original string to perform replacements on.
        replacements: A dictionary where each key is a substring to be replaced
            and each value is the string to replace it with.

    Returns:
        str: A new string with all specified replacements applied.

    Examples:
        >>> multi_replace("hello world", {"hello": "goodbye", "world": "universe"})
        'goodbye universe'
    """
    # reduce(lambda result, substring: result.replace(substring, replacement), substrings, string)
    result = string
    for orig, repl in replacements.items():
        result = result.replace(orig, repl)
    return result

