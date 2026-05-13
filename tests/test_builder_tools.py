from __future__ import annotations

from pathlib import Path

import pytest

from logisim_mcp.circ.parser import parse
from logisim_mcp.tools.builder_tools import (
    add_component,
    add_gate,
    add_pin,
    add_tunnel,
    add_wire,
    connect,
    remove_component,
)
from logisim_mcp.tools.io_tools import create_circuit_file


@pytest.fixture()
def fresh(tmp_path: Path) -> Path:
    p = tmp_path / "lab.circ"
    create_circuit_file(str(p))
    return p


def test_add_input_and_output_pin(fresh: Path) -> None:
    a = add_pin(str(fresh), "main", "A", is_output=False, x=100, y=100)
    s = add_pin(str(fresh), "main", "Sum", is_output=True, x=300, y=100)
    project = parse(fresh)
    pins = project.circuits[0].components
    assert len(pins) == 2
    assert pins[0].attrs["label"] == "A"
    assert pins[1].attrs["label"] == "Sum"
    assert pins[1].attrs["output"] == "true"
    assert a["loc"] == (100, 100)
    assert s["loc"] == (300, 100)


def test_add_gate_and_connect(fresh: Path) -> None:
    a = add_pin(str(fresh), "main", "A", is_output=False, x=100, y=100)
    b = add_pin(str(fresh), "main", "B", is_output=False, x=100, y=140)
    g = add_gate(str(fresh), "main", "AND", x=260, y=120)
    out = add_pin(str(fresh), "main", "Y", is_output=True, x=400, y=120)
    connect(str(fresh), "main", a["id"], "tip", g["id"], "in0")
    connect(str(fresh), "main", b["id"], "tip", g["id"], "in1")
    connect(str(fresh), "main", g["id"], "out", out["id"], "tip")

    project = parse(fresh)
    main = project.circuits[0]
    assert len(main.components) == 4
    assert len(main.wires) >= 3  # may have L-bends, so >=


def test_auto_place_unique_locations(fresh: Path) -> None:
    g1 = add_gate(str(fresh), "main", "AND")
    g2 = add_gate(str(fresh), "main", "AND")
    g3 = add_gate(str(fresh), "main", "OR")
    assert {g1["id"], g2["id"], g3["id"]} == {g1["id"], g2["id"], g3["id"]}
    assert g1["id"] != g2["id"]
    assert g1["id"] != g3["id"]


def test_remove_component(fresh: Path) -> None:
    g = add_gate(str(fresh), "main", "AND", x=200, y=100)
    remove_component(str(fresh), "main", g["id"])
    project = parse(fresh)
    assert project.circuits[0].components == []


def test_tunnel(fresh: Path) -> None:
    t = add_tunnel(str(fresh), "main", "CLK", x=160, y=80)
    project = parse(fresh)
    [comp] = project.circuits[0].components
    assert comp.name == "Tunnel"
    assert comp.attrs["label"] == "CLK"
    assert comp.attrs["facing"] == "west"
    assert t["loc"] == (160, 80)


def test_add_component_multiplexer(fresh: Path) -> None:
    m = add_component(str(fresh), "main", "Multiplexer", select_bits=2, x=300, y=120)
    project = parse(fresh)
    [comp] = project.circuits[0].components
    assert comp.name == "Multiplexer"
    assert comp.attrs["select"] == "2"
    assert m["loc"] == (300, 120)


def test_add_wire_direct(fresh: Path) -> None:
    add_wire(str(fresh), "main", (100, 100), (200, 100))
    add_wire(str(fresh), "main", (100, 100), (100, 200))  # straight vertical
    project = parse(fresh)
    assert len(project.circuits[0].wires) == 2
