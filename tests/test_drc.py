from __future__ import annotations

from pathlib import Path

import pytest

from logisim_mcp.circ.factory import empty_project
from logisim_mcp.circ.model import Circuit, Component, Wire
from logisim_mcp.circ.writer import save
from logisim_mcp.config import HelperUnavailable, JavaTooOld, SETTINGS
from logisim_mcp.runner.java import _reject_diagonal_circs, run_java
from logisim_mcp.tools.describe_tools import _build_nets, check_circuit_drc, static_drc
from logisim_mcp.tools.io_tools import create_circuit_file


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


def test_drc_ignores_empty_tunnel_labels_and_trims_real_ones() -> None:
    project = empty_project()
    circuit = project.circuits[0]
    circuit.components.extend(
        [
            Component("0", "Pin", (0, 0), {"label": "A"}),
            Component("0", "Pin", (0, 40), {"label": "B"}),
            Component("0", "Tunnel", (100, 0), {"label": ""}),
            Component("0", "Tunnel", (100, 40), {"label": ""}),
            Component("0", "Pin", (0, 100), {"label": "C"}),
            Component("0", "Pin", (0, 140), {"label": "D"}),
            Component("0", "Tunnel", (100, 100), {"label": " X "}),
            Component("0", "Tunnel", (100, 140), {"label": "X"}),
        ]
    )
    circuit.wires.extend(
        [
            Wire((0, 0), (100, 0)),
            Wire((0, 40), (100, 40)),
            Wire((0, 100), (100, 100)),
            Wire((0, 140), (100, 140)),
        ]
    )
    report = static_drc(project, circuit)
    assert len(report["shorted_nets"]) == 1
    assert {item["label"] for item in report["shorted_nets"][0]["outputs"]} == {
        "C",
        "D",
    }


def test_check_circuit_drc_survives_missing_helper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "empty.circ"
    create_circuit_file(str(path))

    def no_helper(*_args, **_kwargs):
        raise HelperUnavailable("javac was not found")

    monkeypatch.setattr("logisim_mcp.runner.java.count_error_wires", no_helper)
    report = check_circuit_drc(str(path))
    assert report["error_wires"] is None


def test_check_circuit_drc_survives_old_java(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "empty.circ"
    create_circuit_file(str(path))

    def no_java() -> str:
        raise JavaTooOld("no Java 21")

    jar = tmp_path / "fake.jar"
    jar.write_bytes(b"jar")
    monkeypatch.setattr(SETTINGS, "_java_binary", None)
    monkeypatch.setattr("logisim_mcp.config._resolve_java", no_java)
    monkeypatch.setattr("logisim_mcp.runner.java._ensure_jar", lambda: jar)
    report = check_circuit_drc(str(path))
    assert report["error_wires"] is None


def test_check_circuit_drc_skips_probe_when_another_circuit_has_diagonals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "mixed.circ"
    project = empty_project()
    broken = Circuit(name="broken", attrs={"circuit": "broken"})
    broken.wires.append(Wire((0, 0), (30, 40)))
    project.circuits.append(broken)
    save(project, path)

    def must_not_probe(*_args, **_kwargs):
        raise AssertionError("must not run Java when any circuit has diagonals")

    monkeypatch.setattr("logisim_mcp.runner.java.count_error_wires", must_not_probe)
    report = check_circuit_drc(str(path))
    assert report["circuit"] == "main"
    assert report["diagonal_wires"] == []
    assert report["error_wires"] is None


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


def test_new_file_format_only_checks_the_input(tmp_path: Path) -> None:
    source = tmp_path / "source.circ"
    output = tmp_path / "existing-output.circ"
    save(empty_project(), source)
    bad = empty_project()
    bad.circuits[0].wires.append(Wire((0, 0), (30, 40)))
    save(bad, output)

    _reject_diagonal_circs(["--new-file-format", str(source), str(output)])
