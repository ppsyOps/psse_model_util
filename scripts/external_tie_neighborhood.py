"""
external_tie_neighborhood.py

Find all external buses (and connected equipment) within 4 bus-hops of any
tie line, using the native areas defined in common.constants.INCLUDE_AREAS.

Usage:
    pdm run python scripts/external_tie_neighborhood.py <model_file> [output.xlsx]

Arguments:
    model_file   Path to a .raw or .rawx PSS/E model file.
    output.xlsx  Optional output path (default: external_tie_neighborhood.xlsx
                 in the same directory as the model file).
"""

# Bootstrap: make 'psse_model_util' importable whether the script is run from a
# canonical checkout (project dir named psse_model_util), a git worktree (dir
# has a generated name), or a proper package installation.
import importlib.machinery
import sys
import types
from pathlib import Path

_project_dir = Path(__file__).resolve().parent.parent
_parent_dir = _project_dir.parent

if "psse_model_util" not in sys.modules:
    if (_parent_dir / "psse_model_util").is_dir():
        if str(_parent_dir) not in sys.path:
            sys.path.insert(0, str(_parent_dir))
    else:
        if str(_project_dir) not in sys.path:
            sys.path.insert(0, str(_project_dir))
        _pkg = types.ModuleType("psse_model_util")
        _pkg.__path__ = [str(_project_dir)]
        _pkg.__package__ = "psse_model_util"
        _pkg.__spec__ = importlib.machinery.ModuleSpec(
            "psse_model_util", loader=None, origin=str(_project_dir)
        )
        sys.modules["psse_model_util"] = _pkg

from psse_model_util.common.constants import INCLUDE_AREAS  # noqa: E402
from psse_model_util.model import Model  # noqa: E402


def main(model_path: Path, output_path: Path) -> None:
    print(f"Loading model: {model_path}")
    model = Model(file_path_or_json=model_path)

    print(f"Finding external buses within 4 hops of tie lines "
          f"({len(INCLUDE_AREAS)} native areas)...")
    df = model.network.tie_line_neighborhood(
        n=4,
        native_areas=INCLUDE_AREAS,
        side="external",
        output="dataframe",
    )

    if df.empty:
        print("No external buses found within 4 hops. Check that INCLUDE_AREAS "
              "matches the area numbers in your model.")
        return

    section_counts = df["section"].value_counts().to_dict()
    print(f"Found {len(df)} rows across {df['section'].nunique()} sections:")
    for section, count in sorted(section_counts.items()):
        print(f"  {section}: {count} rows")

    print(f"Writing: {output_path}")
    df.to_excel(output_path, index=False)
    print("Done.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    model_file = Path(sys.argv[1])
    if not model_file.exists():
        print(f"Error: file not found: {model_file}")
        sys.exit(1)

    out_file = (
        Path(sys.argv[2])
        if len(sys.argv) >= 3
        else model_file.with_name("external_tie_neighborhood.xlsx")
    )

    main(model_file, out_file)
