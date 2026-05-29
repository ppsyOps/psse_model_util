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
    # PYTHONPATH must point at the grandparent of psse_model_util so the
    # flat-layout package is importable as `psse_model_util.*` in the subprocess.
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
            "--mon", str(DATA_DIR / "synthetic_pjm.mon"),
            "--raw", str(DATA_DIR / "Model_1.raw"),
            "--out-dir", str(tmp_path),
            "--sc", "PJM",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    assert result.returncode == 0, f"stderr:\n{result.stderr}\nstdout:\n{result.stdout}"
    for name in ["branches.csv", "generators.csv", "transformers_3w.csv", "unresolved.csv"]:
        assert (tmp_path / name).exists(), f"missing {name}"
