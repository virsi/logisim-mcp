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
from logisim_mcp.tools.describe_tools import check_circuit_drc
from logisim_mcp.tools.sim_tools import simulate_sequential, verify_truth_table

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
                # Hex keeps the column radix stable. A later decimal such as
                # ``8`` is rejected once the first row locked the column to binary.
                rows.append([f"0x{a:X}", f"0x{b:X}", str(cin), f"0x{s:X}", str(co)])
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
        inputs=["Sel[2]"],
        outputs=["Q0", "Q1", "Q2", "Q3"],
        rows=[
            ["0x0", "1", "0", "0", "0"],
            ["0x1", "0", "1", "0", "0"],
            ["0x2", "0", "0", "1", "0"],
            ["0x3", "0", "0", "0", "1"],
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
            rows.append([f"0x{a:X}", f"0x{b:X}", gt, eq, lt])
    res = verify_truth_table(
        str(fresh), "comparator", ["A[4]", "B[4]"], ["Gt", "Eq", "Lt"], rows
    )
    assert res["ok"], res["failures"]


def test_build_from_truth_table_xor_synth(fresh: Path) -> None:
    """SOP synthesis must produce a file that parses. Logisim must accept
    the NOT gates (see the load test below)."""
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


@requires_logisim
def test_truth_table_not_gates_load(fresh: Path) -> None:
    """NOT gates must use size 30. size 50 is rejected and the gate vanishes."""
    from logisim_mcp.tools.sim_tools import count_components

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
    res = count_components(str(fresh), circuit="synthesized")
    assert res["ok"], res["stderr"]
    assert res["components"].get("NOT Gate", 0) == 2
    report = check_circuit_drc(str(fresh), circuit="synthesized", probe_errors=True)
    assert report["shorted_nets"] == []
    sim = simulate_sequential(
        str(fresh),
        "synthesized",
        ["A", "B"],
        ["Y"],
        [
            ["0", "0", "0"],
            ["0", "1", "1"],
            ["1", "0", "1"],
            ["1", "1", "0"],
        ],
    )
    assert sim["ok"], sim


@requires_logisim
def test_truth_table_keeps_every_minterm(fresh: Path) -> None:
    """A 3-input function with six 1s used to drop the sixth OR input."""
    rows = []
    for value in range(8):
        bits = [(value >> shift) & 1 for shift in (2, 1, 0)]
        output = "0" if tuple(bits) in ((0, 0, 0), (1, 1, 1)) else "1"
        rows.append([str(bit) for bit in bits] + [output])
    build_from_truth_table(str(fresh), ["A", "B", "C"], ["Y"], rows)
    report = check_circuit_drc(str(fresh), circuit="synthesized", probe_errors=True)
    assert report["shorted_nets"] == []
    sim = simulate_sequential(str(fresh), "synthesized", ["A", "B", "C"], ["Y"], rows)
    assert sim["ok"], sim
    nand = [
        ["0", "0", "1"],
        ["0", "1", "1"],
        ["1", "0", "1"],
        ["1", "1", "0"],
    ]
    build_from_truth_table(
        str(fresh), ["A", "B"], ["Y"], nand, circuit_name="nand"
    )
    nand_report = check_circuit_drc(str(fresh), circuit="nand", probe_errors=True)
    assert nand_report["shorted_nets"] == []
    nand_sim = simulate_sequential(str(fresh), "nand", ["A", "B"], ["Y"], nand)
    assert nand_sim["ok"], nand_sim


def test_truth_table_outputs_get_separate_gates_and_pins(fresh: Path) -> None:
    """Single-literal terms must not collapse two outputs onto one OR/pin."""
    from logisim_mcp.circ.parser import parse

    build_from_truth_table(
        str(fresh),
        inputs=["A", "B"],
        outputs=["Y", "Z"],
        rows=[
            ["1", "0", "1", "0"],
            ["0", "0", "0", "1"],
            ["-", "1", "1", "1"],
        ],
    )
    circuit = parse(fresh).require_circuit("synthesized")
    locations = [comp.loc for comp in circuit.components]
    assert len(locations) == len(set(locations))


@requires_logisim
def test_truth_table_multiple_outputs_simulate_independently(fresh: Path) -> None:
    build_from_truth_table(
        str(fresh),
        inputs=["A", "B"],
        outputs=["Y", "Z"],
        rows=[
            ["1", "0", "1", "0"],
            ["0", "0", "0", "1"],
            ["-", "1", "1", "1"],
        ],
    )
    report = check_circuit_drc(str(fresh), circuit="synthesized", probe_errors=True)
    assert report["shorted_nets"] == []
    assert report["error_wires"] == 0
    rows = [
        ["0", "0", "0", "1"],
        ["0", "1", "1", "1"],
        ["1", "0", "1", "0"],
        ["1", "1", "1", "1"],
    ]
    sim = simulate_sequential(str(fresh), "synthesized", ["A", "B"], ["Y", "Z"], rows)
    assert sim["ok"], sim


@requires_logisim
def test_register_sequential_vector(fresh: Path) -> None:
    """A rising edge on Clk captures D. ``<set>``/``<seq>`` keep state."""
    build_register(str(fresh), bits=1)
    res = verify_truth_table(
        str(fresh),
        "register",
        inputs=["D", "Clk", "En", "Rst"],
        outputs=["Q"],
        rows=[
            ["0", "0", "1", "1", "0"],
            ["1", "0", "1", "0", "0"],
            ["1", "1", "1", "0", "1"],
            ["0", "0", "1", "0", "1"],
            ["0", "1", "1", "0", "0"],
        ],
        sets=[1, 1, 1, 1, 1],
        steps=[1, 2, 3, 4, 5],
    )
    assert res["ok"], res


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
