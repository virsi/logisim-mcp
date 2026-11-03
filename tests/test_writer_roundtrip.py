from __future__ import annotations

from pathlib import Path

from logisim_mcp.circ.factory import empty_project
from logisim_mcp.circ.model import Wire
from logisim_mcp.circ.parser import parse
from logisim_mcp.circ.writer import dump


def _normalize(xml: str) -> str:
    """Drop whitespace-only differences for structural comparison."""
    return "\n".join(line.strip() for line in xml.splitlines() if line.strip())


def test_empty_fixture_roundtrip(fixtures_dir: Path) -> None:
    original = (fixtures_dir / "empty.circ").read_text(encoding="utf-8")
    project = parse(fixtures_dir / "empty.circ")
    written = dump(project)
    assert _normalize(original) == _normalize(written)


def test_empty_factory_roundtrip() -> None:
    project = empty_project()
    xml = dump(project)
    parsed = parse(xml)
    assert parsed.main == "main"
    assert len(parsed.circuits) == 1
    assert parsed.source == "5.0.0"
    assert parsed.circuits[0].attrs.get("simulationFrequency") == "1.0"
    assert [lib.desc for lib in parsed.libs] == [
        "#Wiring",
        "#Gates",
        "#Plexers",
        "#Arithmetic",
        "#FPArithmetic",
        "#Memory",
        "#I/O",
        "#TTL",
        "#TCL",
        "#Base",
        "#BFH-Praktika",
        "#Input/Output-Extra",
        "#Soc",
    ]


def test_wire_buswidth_roundtrip() -> None:
    xml = """<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<project source="5.0.0" version="1.0">
  <main name="main"/>
  <circuit name="main">
    <wire from="(10,10)" to="(40,10)" buswidthpos="center"/>
  </circuit>
</project>
"""
    project = parse(xml)
    wire = project.circuits[0].wires[0]
    assert wire == Wire(start=(10, 10), end=(40, 10), attrs={"buswidthpos": "center"})
    again = parse(dump(project))
    assert again.circuits[0].wires[0].attrs["buswidthpos"] == "center"


def test_duplicate_wire_keeps_a_later_attribute() -> None:
    project = empty_project()
    project.circuits[0].wires = [
        Wire(start=(10, 10), end=(40, 10)),
        Wire(start=(40, 10), end=(10, 10), attrs={"buswidthpos": "center"}),
    ]
    again = parse(dump(project))
    assert len(again.circuits[0].wires) == 1
    assert again.circuits[0].wires[0].attrs["buswidthpos"] == "center"
