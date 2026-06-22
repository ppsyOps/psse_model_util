"""
test_common_utils_coverage.py — characterization tests for small
``psse_model_util.common`` helpers.

Targets previously-uncovered branches:

* ``common.json_util.load_and_clean_json`` — the JSONDecodeError handler
  (prints diagnostics, then re-raises) and the success/cleaning path.
* ``common.logging_config.get_log_file_path`` — the handler-scan loop that
  returns a file handler's path, and the "no file handler" None path.
* ``common.__init__.multi_replace`` — the replacement loop.

Expected values were derived by running the code (characterization).
No ``src/`` files are modified.
"""
from __future__ import annotations

import json
import logging

import pytest

from psse_model_util.common import multi_replace
from psse_model_util.common.json_util import (
    clean_invalid_json_characters,
    load_and_clean_json,
)
from psse_model_util.common.logging_config import get_log_file_path


# ---------------------------------------------------------------------------
# common.__init__.multi_replace
# ---------------------------------------------------------------------------

def test_multi_replace_applies_all():
    assert multi_replace("hello world", {"hello": "hi", "world": "earth"}) == "hi earth"


def test_multi_replace_empty_dict_is_identity():
    assert multi_replace("unchanged", {}) == "unchanged"


def test_multi_replace_sequential_order():
    # replacements apply sequentially; a later key can act on an earlier result
    assert multi_replace("a", {"a": "b", "b": "c"}) == "c"


# ---------------------------------------------------------------------------
# common.json_util
# ---------------------------------------------------------------------------

def test_clean_invalid_json_characters_escapes_control():
    cleaned = clean_invalid_json_characters('{"k": "a\x01b"}')
    assert "\\u0001" in cleaned
    assert "\x01" not in cleaned


def test_clean_invalid_json_characters_fixes_trailing_dot_float():
    assert clean_invalid_json_characters('{"x": 5.}') == '{"x": 5.0}'


def test_load_and_clean_json_success(tmp_path):
    """A valid JSON file (with a control char) loads and cleans correctly."""
    p = tmp_path / "good.json"
    # embed a raw control character that the cleaner must escape before parsing
    p.write_text('{"name": "a\x01b", "n": 5.}', encoding="utf-8")
    data = load_and_clean_json(p)
    assert data["name"] == "a\x01b"
    assert data["n"] == 5.0


def test_load_and_clean_json_invalid_raises_and_prints(tmp_path, capsys):
    """Malformed JSON triggers the except branch: prints diagnostics, re-raises."""
    p = tmp_path / "bad.json"
    p.write_text('{"unterminated": ', encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        load_and_clean_json(p)
    out = capsys.readouterr().out
    assert "JSON decoding error" in out
    assert "Error occurred near" in out


# ---------------------------------------------------------------------------
# common.logging_config.get_log_file_path
# ---------------------------------------------------------------------------

def test_get_log_file_path_returns_file_handler_path(tmp_path):
    """A logger with a FileHandler yields that handler's baseFilename as a Path."""
    log_file = tmp_path / "test.log"
    logger = logging.getLogger("psse_test_logger_with_file")
    logger.handlers.clear()
    handler = logging.FileHandler(log_file)
    logger.addHandler(handler)
    try:
        result = get_log_file_path(logger)
        assert result is not None
        assert result.name == "test.log"
        assert result.resolve() == log_file.resolve()
    finally:
        handler.close()
        logger.handlers.clear()


def test_get_log_file_path_none_when_no_file_handler():
    """A logger with only a stream handler returns None."""
    logger = logging.getLogger("psse_test_logger_stream_only")
    logger.handlers.clear()
    logger.addHandler(logging.StreamHandler())
    try:
        assert get_log_file_path(logger) is None
    finally:
        logger.handlers.clear()


def test_get_log_file_path_skips_stream_finds_file(tmp_path):
    """With both a stream and a file handler, the file handler path wins."""
    log_file = tmp_path / "mixed.log"
    logger = logging.getLogger("psse_test_logger_mixed")
    logger.handlers.clear()
    logger.addHandler(logging.StreamHandler())
    fh = logging.FileHandler(log_file)
    logger.addHandler(fh)
    try:
        result = get_log_file_path(logger)
        assert result is not None and result.name == "mixed.log"
    finally:
        fh.close()
        logger.handlers.clear()
