"""
test_phase_1_4.py — Phase 1.4 baseline unit tests.

Coverage targets:
  - raw_to_rawx.split_csv_line
  - raw_to_rawx._get_section_map
  - raw_to_rawx._raw_to_rawx_section_name
  - raw_to_rawx.raw_file_to_rawx_dict  (integration — uses real RAW files)
  - model.General._auto_dtype
  - common.dataframe_util.convert_df_column_dtypes
  - common.dirs  (smoke — all exported paths are Path objects)
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).resolve().parent / "data"


def _raw(name: str) -> Path:
    """Resolve a filename inside tests/data/."""
    return DATA_DIR / name


# ---------------------------------------------------------------------------
# split_csv_line
# ---------------------------------------------------------------------------

class TestSplitCsvLine:
    """Unit tests for raw_to_rawx.split_csv_line."""

    @pytest.fixture(autouse=True)
    def _import(self):
        from psse_model_util.raw_to_rawx import split_csv_line
        self.fn = split_csv_line

    def test_simple_integers(self):
        result = self.fn("1, 2, 3")
        assert result == ["1", "2", "3"]

    def test_quoted_string_with_comma(self):
        """Commas inside quotes must NOT be used as delimiters."""
        result = self.fn("101, 'NUC-A, UNIT 1', 21.6")
        assert result == ["101", "NUC-A, UNIT 1", "21.6"]

    def test_double_quotes_treated_as_single(self):
        """Double quotes are normalised to single quotes before parsing."""
        result = self.fn('101, "NUC-B", 21.6')
        assert result == ["101", "NUC-B", "21.6"]

    def test_strip_whitespace_and_newlines(self):
        result = self.fn("  10,  20,  30\n")
        assert result == ["10", "20", "30"]

    def test_strip_chars_none_preserves_whitespace(self):
        result = self.fn("  10,  20 ", strip_chars="")
        # With strip_chars="" spaces are preserved (csv.reader still trims
        # via skipinitialspace, but trailing spaces remain)
        assert result[0].strip() == "10"

    def test_empty_string(self):
        """split_csv_line raises StopIteration on empty string (csv.reader quirk).

        This documents the current behaviour as a known edge case.  If the
        function is hardened in a future PR the test should be updated to
        assert result == [].
        """
        with pytest.raises(StopIteration):
            self.fn("")

    def test_single_value(self):
        result = self.fn("42")
        assert result == ["42"]

    def test_carriage_return_stripped(self):
        result = self.fn("1, 2\r\n")
        assert result == ["1", "2"]

    def test_realistic_bus_line(self):
        """Parse a real-ish bus data line from a v34 RAW file."""
        line = "   101,'NUC-A       ',  21.6000,2,   1,   1,   1,1.01000, -19.0142,1.10000,0.90000,1.10000,0.90000"
        result = self.fn(line)
        assert result[0] == "101"
        assert result[1] == "NUC-A"
        assert result[2] == "21.6000"

    def test_float_values(self):
        result = self.fn("1.5, 2.7, 3.14159")
        assert result == ["1.5", "2.7", "3.14159"]

    def test_slash_comment_field(self):
        """Lines ending with / comment marker should survive splitting."""
        line = "0,   100.00, 34,     0,     1, 60.00     / PSS comment"
        result = self.fn(line)
        assert result[0] == "0"
        assert result[1] == "100.00"


# ---------------------------------------------------------------------------
# _get_section_map
# ---------------------------------------------------------------------------

class TestGetSectionMap:
    """Tests for raw_to_rawx._get_section_map."""

    @pytest.fixture(autouse=True)
    def _import(self):
        # Reset global cache so tests get a fresh DataFrame
        import psse_model_util.raw_to_rawx as rtr
        rtr._section_map_df = pd.DataFrame()
        from psse_model_util.raw_to_rawx import _get_section_map
        self.fn = _get_section_map

    def test_returns_dataframe(self):
        df = self.fn()
        assert isinstance(df, pd.DataFrame)

    def test_has_required_columns(self):
        df = self.fn()
        assert set(["section_raw", "subsection_raw", "section_rawx"]).issubset(df.columns)

    def test_no_all_nan_rows(self):
        """Rows where both section_raw AND subsection_raw are NaN should be dropped."""
        df = self.fn()
        both_nan = df["section_raw"].isna() & df["subsection_raw"].isna()
        assert not both_nan.any()

    def test_no_duplicate_triples(self):
        """section_raw / subsection_raw / section_rawx should be unique after dedup."""
        df = self.fn()
        duped = df.duplicated(subset=["section_raw", "subsection_raw", "section_rawx"])
        assert not duped.any()

    def test_subsection_raw_not_equal_section_raw(self):
        """Where subsection_raw == section_raw it should have been set to NaN."""
        df = self.fn()
        mask = df["subsection_raw"].notna()
        equal = df.loc[mask, "section_raw"] == df.loc[mask, "subsection_raw"]
        assert not equal.any()

    def test_well_known_bus_section_present(self):
        """'BUS DATA' section (raw v34 name) must map to rawx 'bus'."""
        df = self.fn()
        assert "BUS DATA" in df["section_raw"].values

    def test_bus_data_maps_to_rawx_bus(self):
        """'BUS DATA' maps to rawx name 'bus'."""
        df = self.fn()
        row = df[df["section_raw"] == "BUS DATA"]
        assert row.iloc[0]["section_rawx"] == "bus"

    def test_result_is_cached(self):
        """Second call should return the same object (cached)."""
        df1 = self.fn()
        df2 = self.fn()
        assert df1 is df2


# ---------------------------------------------------------------------------
# _raw_to_rawx_section_name
# ---------------------------------------------------------------------------

class TestRawToRawxSectionName:
    """Tests for raw_to_rawx._raw_to_rawx_section_name."""

    @pytest.fixture(autouse=True)
    def _import(self):
        import psse_model_util.raw_to_rawx as rtr
        rtr._section_map_df = pd.DataFrame()  # clear cache
        from psse_model_util.raw_to_rawx import _raw_to_rawx_section_name
        self.fn = _raw_to_rawx_section_name

    def test_bus_data_maps_to_bus(self):
        """'BUS DATA' (v34 raw name) maps to rawx section 'bus'."""
        result = self.fn("BUS DATA")
        assert result == "bus"

    def test_case_insensitive_input(self):
        assert self.fn("bus data") == self.fn("BUS DATA")

    def test_unknown_section_returns_none(self):
        result = self.fn("NONEXISTENT_SECTION_XYZ")
        assert result is None

    def test_none_section_raw_returns_none(self):
        result = self.fn(None)
        assert result is None

    def test_load_section(self):
        result = self.fn("LOAD DATA")
        assert result == "load"

    def test_generator_section(self):
        result = self.fn("GENERATOR DATA")
        assert result == "generator"

    def test_branch_section(self):
        result = self.fn("BRANCH DATA")
        assert result == "acline"

    def test_transformer_section(self):
        result = self.fn("TRANSFORMER DATA")
        assert result == "transformer"

    def test_general_section(self):
        result = self.fn("GENERAL")
        assert result == "general"


# ---------------------------------------------------------------------------
# raw_file_to_rawx_dict  (integration — uses real RAW files)
# ---------------------------------------------------------------------------

class TestRawFileToRawxDict:
    """Integration tests exercising raw_file_to_rawx_dict with real RAW data."""

    @pytest.fixture(autouse=True)
    def _import(self):
        from psse_model_util.raw_to_rawx import raw_file_to_rawx_dict
        self.fn = raw_file_to_rawx_dict

    def test_minimal_raw_returns_dict(self):
        result = self.fn(_raw("minimal.raw"))
        assert isinstance(result, dict)

    def test_result_has_network_key(self):
        result = self.fn(_raw("minimal.raw"))
        assert "network" in result

    def test_sample_34_returns_dict(self):
        result = self.fn(_raw("sample_34.raw"))
        assert isinstance(result, dict)
        assert "network" in result

    def test_sample_34_has_bus_data(self):
        result = self.fn(_raw("sample_34.raw"))
        network = result["network"]
        bus_keys = [k for k in network if "bus" in k.lower()]
        assert len(bus_keys) > 0, "Expected at least one 'bus' key in network"

    def test_minimal_raw_bus_section(self):
        """minimal.raw has exactly 2 buses; verify bus data count."""
        result = self.fn(_raw("minimal.raw"), return_dataframes=True)
        network = result["network"]
        bus_keys = [k for k in network if "bus" in k.lower()]
        assert len(bus_keys) > 0
        # At least one bus entry should exist
        bus_section = network[bus_keys[0]]
        if isinstance(bus_section, pd.DataFrame):
            assert len(bus_section) >= 2
        else:
            # dict mode: has 'data' key
            assert len(bus_section.get("data", [])) >= 2

    def test_model_1_raw_parses(self):
        result = self.fn(_raw("Model_1.raw"))
        assert isinstance(result, dict)

    def test_model_2_raw_parses(self):
        result = self.fn(_raw("Model_2.raw"))
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# General._auto_dtype
# ---------------------------------------------------------------------------

class TestGeneralAutoDtype:
    """Unit tests for model.General._auto_dtype static method.

    ``model.py`` imports ``common.file_util``, which in turn does
    ``import msvcrt`` (a Windows-only stdlib module).  We stub it out at the
    ``sys.modules`` level so the import chain succeeds on Linux/macOS.
    """

    @pytest.fixture(autouse=True)
    def _import(self):
        import sys
        import types
        # Stub msvcrt before any import of file_util triggers it.
        if "msvcrt" not in sys.modules:
            sys.modules["msvcrt"] = types.ModuleType("msvcrt")
        from psse_model_util.model import General
        self.fn = General._auto_dtype

    # Default try_dtypes is (float, int, str) — float is tried FIRST.
    # Only if float conversion fails does the method try int, then str.

    def test_integer_string_returns_float_by_default(self):
        """Default order is (float, int, str). '42' succeeds as float(42.0)."""
        result = self.fn("42")
        assert result == 42
        assert isinstance(result, float)   # float wins before int

    def test_integer_string_returns_int_when_order_overridden(self):
        """Explicitly pass (int, float, str) to get int result."""
        result = self.fn("42", try_dtypes=(int, float, str))
        assert result == 42
        assert isinstance(result, int)

    def test_float_string_converts_to_float(self):
        result = self.fn("3.14")
        assert isinstance(result, float)
        assert abs(result - 3.14) < 1e-9

    def test_plain_string_stays_string(self):
        result = self.fn("hello")
        assert result == "hello"
        assert isinstance(result, str)

    def test_whole_float_string_becomes_float(self):
        """'100.0' → float(100.0) wins with the default (float, int, str) order."""
        result = self.fn("100.0")
        assert result == 100.0
        assert isinstance(result, float)

    def test_whole_float_string_becomes_int_with_int_first(self):
        """With (int, float, str) order, '100.0' → int path checks .is_integer() → 100."""
        result = self.fn("100.0", try_dtypes=(int, float, str))
        assert result == 100
        assert isinstance(result, int)

    def test_fractional_float_stays_float(self):
        result = self.fn("1.5")
        assert isinstance(result, float)

    def test_actual_int_passthrough(self):
        """Already-int value: float(7) = 7.0 succeeds, so result is float."""
        result = self.fn(7)
        assert result == 7

    def test_actual_float_passthrough(self):
        result = self.fn(3.14)
        assert isinstance(result, float)

    def test_none_becomes_string_none(self):
        """float(None) and int(None) raise TypeError; str(None) = 'None'."""
        result = self.fn(None)
        assert result == "None"

    def test_empty_string_returns_empty_string(self):
        # float("") raises ValueError, int("") raises ValueError → stays str
        result = self.fn("")
        assert result == ""

    def test_negative_integer_string_returns_float(self):
        """'-5' → float(-5.0) with default order."""
        result = self.fn("-5")
        assert result == -5
        assert isinstance(result, float)

    def test_negative_integer_string_returns_int_when_int_first(self):
        result = self.fn("-5", try_dtypes=(int, float, str))
        assert result == -5
        assert isinstance(result, int)

    def test_scientific_notation(self):
        result = self.fn("1.0E-4")
        assert isinstance(result, float)
        assert abs(result - 1e-4) < 1e-10


# ---------------------------------------------------------------------------
# convert_df_column_dtypes
# ---------------------------------------------------------------------------

class TestConvertDfColumnDtypes:
    """Unit tests for common.dataframe_util.convert_df_column_dtypes."""

    @pytest.fixture(autouse=True)
    def _import(self):
        from psse_model_util.common.dataframe_util import convert_df_column_dtypes
        self.fn = convert_df_column_dtypes

    def _df(self, **kwargs) -> pd.DataFrame:
        return pd.DataFrame(kwargs)

    def test_integer_column_from_str(self):
        df = self._df(a=["1", "2", "3"])
        result = self.fn(df, default_types=(int, float))
        assert result["a"].dtype in (np.int64, np.int32, int)

    def test_float_column_from_str(self):
        df = self._df(a=["1.1", "2.2", "3.3"])
        result = self.fn(df, default_types=(int, float))
        assert result["a"].dtype == float

    def test_string_column_stays_string_dtype(self):
        """Pandas 3+ uses StringDtype for string columns (not object).
        We check with is_string_dtype to be version-agnostic.
        """
        df = self._df(a=["foo", "bar", "baz"])
        result = self.fn(df, default_types=(int, float))
        assert pd.api.types.is_string_dtype(result["a"])

    def test_inplace_false_does_not_mutate_original(self):
        df = self._df(a=["1", "2"])
        orig_dtype = df["a"].dtype
        result = self.fn(df, inplace=False, default_types=(int, float))
        assert df["a"].dtype == orig_dtype
        assert result["a"].dtype in (np.int64, np.int32, int)

    def test_inplace_true_mutates_original(self):
        df = self._df(a=["1", "2"])
        self.fn(df, inplace=True, default_types=(int, float))
        assert df["a"].dtype in (np.int64, np.int32, int)

    def test_non_dataframe_raises(self):
        with pytest.raises(AssertionError):
            self.fn([1, 2, 3])

    def test_specific_column_dtype_override(self):
        """new_dtypes lets you pin a specific column's conversion chain."""
        df = self._df(a=["1", "2", "3"], b=["1.5", "2.5", "3.5"])
        result = self.fn(df,
                         new_dtypes={"a": [int], "b": [float]},
                         convert_all_columns=False)
        assert result["a"].dtype in (np.int64, np.int32, int)
        assert result["b"].dtype == float

    def test_convert_all_columns_false_skips_unspecified(self):
        df = self._df(a=["1", "2"], b=["hello", "world"])
        result = self.fn(df,
                         new_dtypes={"a": [int]},
                         convert_all_columns=False)
        # 'b' should be untouched — string dtype (object or StringDtype in pandas 3+)
        assert pd.api.types.is_string_dtype(result["b"])

    def test_mixed_column_falls_back_to_string(self):
        """Column with mixed int + non-numeric strings can't convert to int/float
        and should stay a string-compatible dtype (object or StringDtype)."""
        df = self._df(a=["1", "abc", "3"])
        result = self.fn(df, default_types=(int, float))
        assert pd.api.types.is_string_dtype(result["a"])

    def test_empty_dataframe_ok(self):
        df = pd.DataFrame({"a": pd.Series([], dtype=str)})
        result = self.fn(df, default_types=(int, float))
        assert isinstance(result, pd.DataFrame)


# ---------------------------------------------------------------------------
# common.dirs — smoke tests
# ---------------------------------------------------------------------------

class TestDirs:
    """Smoke tests: all exported paths in common.dirs are Path objects."""

    @pytest.fixture(autouse=True)
    def _import(self):
        from psse_model_util.common import dirs
        self.dirs = dirs

    def test_user_config_dir_is_path(self):
        assert isinstance(self.dirs.user_config_dir, Path)

    def test_user_log_dir_is_path(self):
        assert isinstance(self.dirs.user_log_dir, Path)

    def test_user_data_dir_is_path(self):
        assert isinstance(self.dirs.user_data_dir, Path)

    def test_user_cache_dir_is_path(self):
        assert isinstance(self.dirs.user_cache_dir, Path)

    def test_user_state_dir_is_path(self):
        assert isinstance(self.dirs.user_state_dir, Path)

    def test_user_temp_dir_is_path(self):
        assert isinstance(self.dirs.user_temp_dir, Path)

    def test_site_config_dir_is_path(self):
        assert isinstance(self.dirs.site_config_dir, Path)

    def test_site_log_dir_is_path(self):
        assert isinstance(self.dirs.site_log_dir, Path)

    def test_site_data_dir_is_path(self):
        assert isinstance(self.dirs.site_data_dir, Path)

    def test_site_cache_dir_is_path(self):
        assert isinstance(self.dirs.site_cache_dir, Path)

    def test_site_temp_dir_is_path(self):
        assert isinstance(self.dirs.site_temp_dir, Path)

    def test_get_app_dirs_returns_all_path_values(self):
        result = self.dirs.get_app_dirs()
        assert isinstance(result, dict)
        assert len(result) > 0
        for key, val in result.items():
            assert isinstance(val, Path), f"dirs.{key} is not a Path: {type(val)}"

    def test_app_name_constant(self):
        assert self.dirs.APP_NAME == "psse_model_util"
