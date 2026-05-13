from __future__ import annotations

from pathlib import Path

import pytest

from logisim_mcp.tools.describe_tools import describe_circuit
from logisim_mcp.tools.highlevel_tools import build_half_adder
from logisim_mcp.tools.io_tools import create_circuit_file


@pytest.fixture()
def fresh(tmp_path: Path) -> Path:
    p = tmp_path / "lab.circ"
    create_circuit_file(str(p))
    return p


def test_describe_half_adder(fresh: Path) -> None:
    build_half_adder(str(fresh))
    res = describe_circuit(str(fresh), "half_adder")
    txt = res["text"]
    assert 'Circuit "half_adder"' in txt
    assert "IN   A" in txt
    assert "IN   B" in txt
    assert "OUT  Sum" in txt
    assert "OUT  Cout" in txt
    assert "XOR" in txt
    assert "AND" in txt
    assert "Nets:" in txt


def test_describe_main_default(fresh: Path) -> None:
    res = describe_circuit(str(fresh))
    assert res["circuit"] == "main"
    assert "Circuit \"main\"" in res["text"]
