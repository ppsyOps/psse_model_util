"""Smoke test for the standalone CLI script. Skips if the sibling repo isn't checked out."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

DATA_DIR = Path(__file__).resolve().parent / "data"
CLI_SCRIPT = (
    Path(__file__).resolve().parent.parent.parent / "key_facilities" / "key_facilities.py"
)


@pytest.mark.skipif(
    not CLI_SCRIPT.exists(),
    reason=f"CLI script not found at {CLI_SCRIPT}; skipping smoke test.",
)
def test_cli_writes_four_csvs(tmp_path):
    # PYTHONPATH must point at the src/ dir so the package is importable as
    # `psse_model_util.*` in the subprocess (src/ layout).
    src_dir = Path(__file__).resolve().parent.parent / "src"
    env = os.environ.copy()
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        str(src_dir) + (os.pathsep + existing_pp if existing_pp else "")
    )

    result = subprocess.run(
        [
            sys.executable,
            str(CLI_SCRIPT),
            "--mon", str(DATA_DIR / "synthetic_flowgates.mon"),
            "--raw", str(DATA_DIR / "Model_1.raw"),
            "--areas", "1", "2", "3",
            "--out-dir", str(tmp_path),
            "--sc", "SCA",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    assert result.returncode == 0, f"stderr:\n{result.stderr}\nstdout:\n{result.stdout}"
    for name in ["branches.csv", "generators.csv", "transformers_3w.csv", "unresolved.csv"]:
        assert (tmp_path / name).exists(), f"missing {name}"


@pytest.mark.skipif(
    not CLI_SCRIPT.exists(),
    reason=f"CLI script not found at {CLI_SCRIPT}; skipping smoke test.",
)
def test_cli_areas_filter_drops_out_of_scope_equipment(tmp_path):
    """Pass an empty-area set (--areas 9999) and confirm every SCA seed
    becomes unresolved; branches/generators/transformers come out empty."""
    package_root = Path(__file__).resolve().parent.parent
    grandparent = package_root.parent
    env = os.environ.copy()
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        str(grandparent) + (os.pathsep + existing_pp if existing_pp else "")
    )

    result = subprocess.run(
        [
            sys.executable,
            str(CLI_SCRIPT),
            "--mon", str(DATA_DIR / "synthetic_flowgates.mon"),
            "--raw", str(DATA_DIR / "Model_1.raw"),
            "--areas", "9999",  # no equipment in this area
            "--out-dir", str(tmp_path),
            "--sc", "SCA",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    assert result.returncode == 0, f"stderr:\n{result.stderr}\nstdout:\n{result.stdout}"
    # Branches/generators/3W are empty (header-only); unresolved has the seeds.
    import pandas as pd
    branches = pd.read_csv(tmp_path / "branches.csv")
    generators = pd.read_csv(tmp_path / "generators.csv")
    transformers_3w = pd.read_csv(tmp_path / "transformers_3w.csv")
    unresolved = pd.read_csv(tmp_path / "unresolved.csv")
    assert len(branches) == 0
    assert len(generators) == 0
    assert len(transformers_3w) == 0
    assert len(unresolved) > 0  # seeds all unresolvable
