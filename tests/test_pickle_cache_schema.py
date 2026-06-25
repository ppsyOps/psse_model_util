from pathlib import Path

import pytest

from psse_model_util.model import MODEL_CACHE_SCHEMA_VERSION, Model

DATA_DIR = Path(__file__).resolve().parent / "data"


def test_fresh_model_has_current_cache_version():
    m = Model(DATA_DIR / "Model_1.raw", force_recalculate=True)
    assert m._cache_schema_version == MODEL_CACHE_SCHEMA_VERSION


def test_pickle_round_trip_preserves_registry():
    import pickle
    m = Model(DATA_DIR / "Model_1.raw", force_recalculate=True)
    reloaded = pickle.loads(pickle.dumps(m))
    # registry survived the pickle and a registry-driven op still works
    assert reloaded.network.bus_cols("acline") == ("ibus", "jbus")
    filtered = reloaded.network.filter_by_area({1: "AREA"}, inplace=False)
    assert len(filtered.bus) <= len(reloaded.network.bus)


def test_stale_cache_is_ignored_and_rebuilt():
    raw = DATA_DIR / "Model_1.raw"
    m = Model(raw, force_recalculate=True)         # builds + writes cache at m.pickle_path
    assert m.pickle_path.exists()
    m._cache_schema_version = -1                   # simulate a legacy/stale cache
    m.to_pickle()                                  # overwrite cache with the stale-version object
    with pytest.warns(UserWarning, match="cache schema"):
        m2 = Model(raw)                            # reopen WITHOUT force: must ignore stale + rebuild
    assert m2._cache_schema_version == MODEL_CACHE_SCHEMA_VERSION
    assert m2.network.bus_cols("bus") == ("ibus",)
