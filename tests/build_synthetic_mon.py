"""One-shot generator for tests/data/synthetic_pjm.mon, aligned with Model_1.raw.

Run with:  python tests/build_synthetic_mon.py
Output:    tests/data/synthetic_pjm.mon  (commit it)

This script is intentionally NOT on the pytest path.
"""
import importlib.machinery
import sys
import types
from pathlib import Path

# Make `psse_model_util` importable when this script is run directly
# (mirrors the logic in tests/conftest.py).
_PROJECT_DIR = Path(__file__).resolve().parent.parent
_PARENT_DIR = _PROJECT_DIR.parent
if (_PARENT_DIR / "psse_model_util").is_dir():
    if str(_PARENT_DIR) not in sys.path:
        sys.path.insert(0, str(_PARENT_DIR))
elif "psse_model_util" not in sys.modules:
    if str(_PROJECT_DIR) not in sys.path:
        sys.path.insert(0, str(_PROJECT_DIR))
    _pkg = types.ModuleType("psse_model_util")
    _pkg.__path__ = [str(_PROJECT_DIR)]
    _pkg.__package__ = "psse_model_util"
    _pkg.__spec__ = importlib.machinery.ModuleSpec(
        "psse_model_util", loader=None, origin=str(_PROJECT_DIR)
    )
    sys.modules["psse_model_util"] = _pkg

from psse_model_util.model import Model  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent / "data"
RAW_FILE = DATA_DIR / "Model_1.raw"
OUT_FILE = DATA_DIR / "synthetic_pjm.mon"

# Areas treated as "PJM" for the synthetic fixture. Hardcoded so the fixture is
# stable regardless of what psse_model_util.common.constants.NATIVE_AREAS is set
# to at any given time.
MODEL_1_PJM_AREAS = {1, 2, 3}


def _bus_token(name: str, baskv: float) -> str:
    """Build an 18-char PSS/E bus token: 12-char left-padded name + 6-char kV."""
    name_part = f"{name:<12}"[:12]
    kv_part = f"{baskv:<6.2f}"[:6]
    return f"{name_part}{kv_part}"


def main() -> None:
    model = Model(RAW_FILE, force_recalculate=True)
    bus = model.network.bus
    ac = model.network.acline.reset_index()
    gen = model.network.generator.reset_index()

    # Build bus lookup: ibus -> (name, baskv, area)
    bus_info = {
        ibus: (str(row["name"]).strip(), float(row["baskv"]), int(row["area"]))
        for ibus, row in bus.iterrows()
    }

    # Pick 4 PJM branches with both ends >= 160 kV in PJM areas
    pjm_branches = ac[
        ac["ibus"].map(lambda b: bus_info.get(b, (None, 0, 0))[2]).isin(MODEL_1_PJM_AREAS)
        & ac["jbus"].map(lambda b: bus_info.get(b, (None, 0, 0))[2]).isin(MODEL_1_PJM_AREAS)
        & ac["ibus"].map(lambda b: bus_info.get(b, (None, 0, 0))[1] >= 160.0)
    ].head(4)

    if len(pjm_branches) < 4:
        raise RuntimeError(
            f"Only found {len(pjm_branches)} PJM branches in Model_1.raw; "
            f"need at least 4 to build the fixture."
        )

    # Pick one PJM generator for the REMOVE MACHINE flowgate
    pjm_gen = gen[
        gen["ibus"].map(lambda b: bus_info.get(b, (None, 0, 0))[2]).isin(MODEL_1_PJM_AREAS)
    ].head(1)
    if pjm_gen.empty:
        raise RuntimeError("No PJM generators in Model_1.raw.")
    gen_row = pjm_gen.iloc[0]
    gen_bus_name, gen_bus_kv, _ = bus_info[int(gen_row["ibus"])]
    gen_machid = str(gen_row["machid"]).strip()

    # Pick one non-PJM branch for the SC OTHER flowgate
    non_pjm = ac[
        ~ac["ibus"].map(lambda b: bus_info.get(b, (None, 0, 0))[2]).isin(MODEL_1_PJM_AREAS)
    ].head(1)
    if non_pjm.empty:
        raise RuntimeError("No non-PJM branches in Model_1.raw to use for SC OTHER.")

    lines: list[str] = ["BUSNAMES"]

    def emit_branch_fg(fg_id, mon_row, con_row, sc):
        i_name, i_kv, _ = bus_info[int(mon_row["ibus"])]
        j_name, j_kv, _ = bus_info[int(mon_row["jbus"])]
        ci_name, ci_kv, _ = bus_info[int(con_row["ibus"])]
        cj_name, cj_kv, _ = bus_info[int(con_row["jbus"])]
        lines.extend([
            "",
            f"MONITOR FLOWGATE {fg_id}  'synthetic FG {fg_id}'",
            f"         BRANCH FROM BUS '{_bus_token(i_name, i_kv)}' TO BUS '{_bus_token(j_name, j_kv)}' CKT {str(mon_row['ckt']).strip()}",
            f" CONTINGENCY {fg_id}",
            f"    OPEN BRANCH FROM BUS '{_bus_token(ci_name, ci_kv)}' TO BUS '{_bus_token(cj_name, cj_kv)}' CKT {str(con_row['ckt']).strip()}",
            " END",
            "    CA SYN SYN",
            f"    SC {sc}",
            f"    TP {sc} {sc}",
            "END",
        ])

    rows = pjm_branches.reset_index(drop=True)
    # FG 1: branches[0] monitor, branches[1] contingency, SC PJM
    emit_branch_fg(1001, rows.iloc[0], rows.iloc[1], "PJM")
    # FG 2: branches[2] monitor, branches[3] contingency, SC PJM
    emit_branch_fg(1002, rows.iloc[2], rows.iloc[3], "PJM")

    # FG 3: REMOVE MACHINE contingency on a PJM generator
    i_name, i_kv, _ = bus_info[int(rows.iloc[0]["ibus"])]
    j_name, j_kv, _ = bus_info[int(rows.iloc[0]["jbus"])]
    lines.extend([
        "",
        "MONITOR FLOWGATE 1003  'synthetic FG 1003 gen contingency'",
        f"         BRANCH FROM BUS '{_bus_token(i_name, i_kv)}' TO BUS '{_bus_token(j_name, j_kv)}' CKT {str(rows.iloc[0]['ckt']).strip()}",
        " CONTINGENCY 1003",
        f"    REMOVE MACHINE {gen_machid} FROM BUS '{_bus_token(gen_bus_name, gen_bus_kv)}'",
        " END",
        "    CA SYN SYN",
        "    SC PJM",
        "    TP PJM PJM",
        "END",
    ])

    # FG 4: SC OTHER (must be dropped by filter_by_sc)
    non_pjm_row = non_pjm.iloc[0]
    ni_name, ni_kv, _ = bus_info[int(non_pjm_row["ibus"])]
    nj_name, nj_kv, _ = bus_info[int(non_pjm_row["jbus"])]
    lines.extend([
        "",
        "MONITOR FLOWGATE 9001  'synthetic non-PJM'",
        f"         BRANCH FROM BUS '{_bus_token(ni_name, ni_kv)}' TO BUS '{_bus_token(nj_name, nj_kv)}' CKT {str(non_pjm_row['ckt']).strip()}",
        " CONTINGENCY 9001",
        f"    OPEN BRANCH FROM BUS '{_bus_token(ni_name, ni_kv)}' TO BUS '{_bus_token(nj_name, nj_kv)}' CKT {str(non_pjm_row['ckt']).strip()}",
        " END",
        "    CA SYN SYN",
        "    SC OTHER",
        "    TP OTHER OTHER",
        "END",
    ])

    OUT_FILE.write_text("\n".join(lines) + "\n")
    print(f"Wrote {OUT_FILE} ({len(lines)} lines)")


if __name__ == "__main__":
    main()
