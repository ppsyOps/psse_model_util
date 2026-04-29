

def multi_replace(string: str, replacements: dict[str, str]):
    """
    Replace occurrences of substrings in `string` based on a dictionary of
    replacements.

    This function iterates over each key-value pair in the `replacements`
     dictionary. Each key represents a substring in `string` that should be
     replaced by its corresponding value. The function applies these
     replacements sequentially and returns the modified string.

    :param string: The original string to perform replacements on.
    :type string: str
    :param replacements: A dictionary where each key-value pair represents a
    substring to be replaced (key) and the string to replace it with (value).
    :type replacements: dict[str, str]
    :return: A new string with all specified replacements applied.
    :rtype: str

    Example:
        >>> multi_replace("hello world", {"hello": "goodbye", "world": "universe"})
        'goodbye universe'
    """
    # reduce(lambda result, substring: result.replace(substring, replacement), substrings, string)
    result = string
    for orig, repl in replacements.items():
        result = result.replace(orig, repl)
    return result

