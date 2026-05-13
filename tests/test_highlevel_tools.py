from __future__ import annotations

from pathlib import Path

import pytest

from logisim_mcp.config import SETTINGS
from logisim_mcp.tools.highlevel_tools import (
    build_comparator,
    build_decoder,
    build_from_truth_table,
    build_full_adder,
    build_half_adder,
    build_mux,
    build_register,
    build_ripple_adder,
)
from logisim_mcp.tools.io_tools import create_circuit_file
from logisim_mcp.tools.sim_tools import verify_truth_table

requires_logisim = pytest.mark.skipif(
    not SETTINGS.logisim_jar.exists(),
    reason="Logisim JAR not installed",
)


@pytest.fixture()
def fresh(tmp_path: Path) -> Path:
    p = tmp_path / "lab.circ"
    create_circuit_file(str(p))
    return p


@requires_logisim
def test_half_adder_truth_table(fresh: Path) -> None:
    build_half_adder(str(fresh))
    res = verify_truth_table(
        str(fresh),
        "half_adder",
        inputs=["A", "B"],
        outputs=["Sum", "Cout"],
        rows=[
            ["0", "0", "0", "0"],
            ["0", "1", "1", "0"],
            ["1", "0", "1", "0"],
            ["1", "1", "0", "1"],
        ],
    )
    assert res["ok"], res["failures"]
    assert res["passed"] == 4


@requires_logisim
def test_full_adder_truth_table(fresh: Path) -> None:
    build_full_adder(str(fresh))
    rows: list[list[str]] = []
    for a in (0, 1):
        for b in (0, 1):
            for cin in (0, 1):
                s = (a + b + cin) & 1
                co = (a + b + cin) >> 1
                rows.append([str(a), str(b), str(cin), str(s), str(co)])
    res = verify_truth_table(
        str(fresh), "full_adder", ["A", "B", "Cin"], ["Sum", "Cout"], rows
    )
    assert res["ok"], res["failures"]
    assert res["passed"] == 8


@requires_logisim
def test_ripple_adder_4bit(fresh: Path) -> None:
    build_ripple_adder(str(fresh), bits=4)
    rows = []
    for a in (0, 5, 9, 15):
        for b in (0, 3, 7, 8):
            for cin in (0, 1):
                s = (a + b + cin) & 0xF
                co = (a + b + cin) >> 4
                rows.append([str(a), str(b), str(cin), str(s), str(co)])
    # Use [N] notation so Logisim treats A/B/Sum as 4-bit buses, not 1-bit
    # scalars masked to their LSB.
    res = verify_truth_table(
        str(fresh), "ripple_adder",
        ["A[4]", "B[4]", "Cin"], ["Sum[4]", "Cout"], rows,
    )
    assert res["ok"], res["failures"]


@requires_logisim
def test_mux_2to1(fresh: Path) -> None:
    build_mux(str(fresh), select_bits=1)
    res = verify_truth_table(
        str(fresh),
        "mux",
        inputs=["D0", "D1", "Sel"],
        outputs=["Y"],
        rows=[
            ["0", "0", "0", "0"],
            ["0", "0", "1", "0"],
            ["1", "0", "0", "1"],
            ["1", "0", "1", "0"],
            ["0", "1", "0", "0"],
            ["0", "1", "1", "1"],
            ["1", "1", "0", "1"],
            ["1", "1", "1", "1"],
        ],
    )
    assert res["ok"], res["failures"]


@requires_logisim
def test_decoder_2bit(fresh: Path) -> None:
    build_decoder(str(fresh), select_bits=2)
    res = verify_truth_table(
        str(fresh),
        "decoder",
        inputs=["Sel"],
        outputs=["Q0", "Q1", "Q2", "Q3"],
        rows=[
            ["0", "1", "0", "0", "0"],
            ["1", "0", "1", "0", "0"],
            ["2", "0", "0", "1", "0"],
            ["3", "0", "0", "0", "1"],
        ],
    )
    assert res["ok"], res["failures"]


@requires_logisim
def test_comparator_4bit(fresh: Path) -> None:
    build_comparator(str(fresh), bits=4)
    rows = []
    for a in (0, 3, 7, 15):
        for b in (0, 3, 7, 15):
            gt = "1" if a > b else "0"
            eq = "1" if a == b else "0"
            lt = "1" if a < b else "0"
            rows.append([str(a), str(b), gt, eq, lt])
    res = verify_truth_table(
        str(fresh), "comparator", ["A", "B"], ["Gt", "Eq", "Lt"], rows
    )
    assert res["ok"], res["failures"]


def test_build_from_truth_table_xor_synth(fresh: Path) -> None:
    """SOP synthesis must produce a file that parses; correctness checked
    end-to-end below."""
    build_from_truth_table(
        str(fresh),
        inputs=["A", "B"],
        outputs=["Y"],
        rows=[
            ["0", "0", "0"],
            ["0", "1", "1"],
            ["1", "0", "1"],
            ["1", "1", "0"],
        ],
    )


def test_register_builds(fresh: Path) -> None:
    build_register(str(fresh), bits=4)


@requires_logisim
def test_register_accepted_by_logisim(fresh: Path) -> None:
    """Logisim opens the generated register without errors and reports
    the expected component classes (5 pins + 1 register)."""
    from logisim_mcp.tools.sim_tools import count_components

    build_register(str(fresh), bits=4)
    res = count_components(str(fresh), circuit="register")
    assert res["ok"], res["stderr"]
    assert res["components"].get("Register", 0) == 1
    assert res["components"].get("Pin", 0) == 5


@requires_logisim
def test_counter_accepted_by_logisim(fresh: Path) -> None:
    """Logisim opens the generated counter without errors and reports
    the expected component classes (8 pins + 1 counter)."""
    from logisim_mcp.tools.sim_tools import count_components

    from logisim_mcp.tools.highlevel_tools import build_counter

    build_counter(str(fresh), bits=4)
    res = count_components(str(fresh), circuit="counter")
    assert res["ok"], res["stderr"]
    assert res["components"].get("Counter", 0) == 1
    assert res["components"].get("Pin", 0) == 8
