from __future__ import annotations

from pathlib import Path

import pytest

from logisim_mcp.circ.factory import empty_project
from logisim_mcp.circ.model import Component, Wire
from logisim_mcp.circ.writer import save
from logisim_mcp.config import SETTINGS
from logisim_mcp.runner.java import _reject_diagonal_circs, run_java
from logisim_mcp.tools.describe_tools import _build_nets, static_drc


def test_static_drc_flags_shorts_floats_crossings_and_diagonals() -> None:
    project = empty_project()
    circuit = project.circuits[0]
    circuit.components.extend(
        [
            Component("0", "Pin", (0, 0), {"label": "A"}),
            Component("0", "Pin", (0, 40), {"label": "B"}),
            Component("0", "Pin", (200, 0), {"type": "output", "label": "Y"}),
            Component("0", "Pin", (50, 80), {"label": "C"}),
        ]
    )
    circuit.wires.extend(
        [
            Wire((0, 0), (0, 40)),
            Wire((0, 80), (100, 80)),
            Wire((0, 120), (40, 160)),
        ]
    )
    report = static_drc(project, circuit)
    assert len(report["shorted_nets"]) == 1
    assert {item["label"] for item in report["shorted_nets"][0]["outputs"]} == {"A", "B"}
    assert any(item["label"] == "Y" for item in report["floating_inputs"])
    assert any(item["port"]["label"] == "C" for item in report["unintended_pin_crossings"])
    assert report["diagonal_wires"] == [{"from": [0, 120], "to": [40, 160]}]

    point_to_net, _ = _build_nets(project, circuit)
    assert point_to_net[(0, 80)] == point_to_net[(50, 80)]
    assert (0, 120) not in point_to_net or point_to_net[(0, 120)] != point_to_net.get((40, 160))


def test_diagonal_file_is_refused_before_java(tmp_path: Path) -> None:
    path = tmp_path / "bad.circ"
    project = empty_project()
    project.circuits[0].wires.append(Wire((0, 0), (30, 40)))
    save(project, path)
    with pytest.raises(ValueError, match="diagonal"):
        _reject_diagonal_circs([str(path)])
    if SETTINGS.logisim_jar.exists():
        with pytest.raises(ValueError, match="diagonal"):
            run_java([str(path)])
