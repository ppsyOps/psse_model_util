"""One-shot generator for tests/data/synthetic_flowgates.mon, aligned with Model_1.raw.

Run with:  python tests/build_synthetic_mon.py
Output:    tests/data/synthetic_flowgates.mon  (commit it)

This script is intentionally NOT on the pytest path.
"""
import sys
from pathlib import Path

# Make `psse_model_util` importable when this script is run directly without an
# editable install (mirrors the fallback in tests/conftest.py).
_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if _SRC_DIR.is_dir() and str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from psse_model_util.model import Model  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent / "data"
RAW_FILE = DATA_DIR / "Model_1.raw"
OUT_FILE = DATA_DIR / "synthetic_flowgates.mon"

# Areas treated as native (SC "SCA") for the synthetic fixture. Hardcoded so the fixture is
# stable regardless of what psse_model_util.common.constants.NATIVE_AREAS is set
# to at any given time.
MODEL_1_SC_AREAS = {1, 2, 3}


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

    # Pick 4 native branches with both ends >= 160 kV in SCA areas
    sca_branches = ac[
        ac["ibus"].map(lambda b: bus_info.get(b, (None, 0, 0))[2]).isin(MODEL_1_SC_AREAS)
        & ac["jbus"].map(lambda b: bus_info.get(b, (None, 0, 0))[2]).isin(MODEL_1_SC_AREAS)
        & ac["ibus"].map(lambda b: bus_info.get(b, (None, 0, 0))[1] >= 160.0)
    ].head(4)

    if len(sca_branches) < 4:
        raise RuntimeError(
            f"Only found {len(sca_branches)} native branches in Model_1.raw; "
            f"need at least 4 to build the fixture."
        )

    # Pick one native generator for the REMOVE MACHINE flowgate
    sca_gen = gen[
        gen["ibus"].map(lambda b: bus_info.get(b, (None, 0, 0))[2]).isin(MODEL_1_SC_AREAS)
    ].head(1)
    if sca_gen.empty:
        raise RuntimeError("No native generators in Model_1.raw.")
    gen_row = sca_gen.iloc[0]
    gen_bus_name, gen_bus_kv, _ = bus_info[int(gen_row["ibus"])]
    gen_machid = str(gen_row["machid"]).strip()

    # Pick one external branch for the SC SCB flowgate
    other_branch = ac[
        ~ac["ibus"].map(lambda b: bus_info.get(b, (None, 0, 0))[2]).isin(MODEL_1_SC_AREAS)
    ].head(1)
    if other_branch.empty:
        raise RuntimeError("No external branches in Model_1.raw to use for SC SCB.")

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

    rows = sca_branches.reset_index(drop=True)
    # FG 1: branches[0] monitor, branches[1] contingency, SC SCA
    emit_branch_fg(1001, rows.iloc[0], rows.iloc[1], "SCA")
    # FG 2: branches[2] monitor, branches[3] contingency, SC SCA
    emit_branch_fg(1002, rows.iloc[2], rows.iloc[3], "SCA")

    # FG 3: REMOVE MACHINE contingency on a native generator
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
        "    SC SCA",
        "    TP SCA SCA",
        "END",
    ])

    # FG 4: SC SCB (must be dropped by filter_by_sc)
    other_branch_row = other_branch.iloc[0]
    ni_name, ni_kv, _ = bus_info[int(other_branch_row["ibus"])]
    nj_name, nj_kv, _ = bus_info[int(other_branch_row["jbus"])]
    lines.extend([
        "",
        "MONITOR FLOWGATE 9001  'synthetic SCB flowgate'",
        f"         BRANCH FROM BUS '{_bus_token(ni_name, ni_kv)}' TO BUS '{_bus_token(nj_name, nj_kv)}' CKT {str(other_branch_row['ckt']).strip()}",
        " CONTINGENCY 9001",
        f"    OPEN BRANCH FROM BUS '{_bus_token(ni_name, ni_kv)}' TO BUS '{_bus_token(nj_name, nj_kv)}' CKT {str(other_branch_row['ckt']).strip()}",
        " END",
        "    CA SYN SYN",
        "    SC SCB",
        "    TP SCB SCB",
        "END",
    ])

    OUT_FILE.write_text("\n".join(lines) + "\n")
    print(f"Wrote {OUT_FILE} ({len(lines)} lines)")


if __name__ == "__main__":
    main()
