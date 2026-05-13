from __future__ import annotations

from pathlib import Path

from logisim_mcp.circ.parser import parse


def test_parse_empty_fixture(fixtures_dir: Path) -> None:
    project = parse(fixtures_dir / "empty.circ")
    assert project.source == "4.0.0"
    assert project.version == "1.0"
    assert project.main == "main"
    assert [lib.desc for lib in project.libs] == [
        "#Wiring",
        "#Gates",
        "#Plexers",
        "#Arithmetic",
        "#Memory",
        "#I/O",
        "#Base",
    ]
    assert project.libs[0].id == "0"
    assert project.libs[0].tools_raw_xml  # Pin appearance tool preserved.
    assert len(project.circuits) == 1
    main_circuit = project.circuits[0]
    assert main_circuit.name == "main"
    assert main_circuit.attrs.get("simulationFrequency") == "1.0"
    assert main_circuit.components == []
    assert main_circuit.wires == []
    # <options>, <mappings>, <toolbar> should survive as raw extras.
    joined = "\n".join(project.extras_raw_xml)
    assert "<options" in joined
    assert "<mappings" in joined
    assert "<toolbar" in joined


def test_parse_inline_xml_string() -> None:
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="no"?>'
        '<project source="4.0.0" version="1.0">'
        '<lib desc="#Wiring" name="0"/>'
        '<lib desc="#Gates" name="1"/>'
        '<main name="main"/>'
        '<circuit name="main">'
        '<a name="circuit" val="main"/>'
        '<comp lib="0" loc="(100,100)" name="Pin">'
        '<a name="label" val="A"/>'
        "</comp>"
        '<wire from="(100,100)" to="(200,100)"/>'
        "</circuit>"
        "</project>"
    )
    project = parse(xml)
    assert len(project.circuits) == 1
    main_circuit = project.circuits[0]
    assert len(main_circuit.components) == 1
    pin = main_circuit.components[0]
    assert pin.name == "Pin"
    assert pin.loc == (100, 100)
    assert pin.attrs == {"label": "A"}
    assert len(main_circuit.wires) == 1
    wire = main_circuit.wires[0]
    assert wire.start == (100, 100)
    assert wire.end == (200, 100)
