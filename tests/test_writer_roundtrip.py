from __future__ import annotations

from pathlib import Path

from logisim_mcp.circ.factory import empty_project
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
    assert parsed.circuits[0].attrs.get("simulationFrequency") == "1.0"
    assert [lib.desc for lib in parsed.libs] == [
        "#Wiring",
        "#Gates",
        "#Plexers",
        "#Arithmetic",
        "#Memory",
        "#I/O",
        "#Base",
    ]
