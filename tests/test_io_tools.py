from __future__ import annotations

from pathlib import Path

import pytest

from logisim_mcp.tools.io_tools import (
    add_subcircuit,
    create_circuit_file,
    delete_circuit,
    list_circuits,
    read_circuit_file,
    rename_circuit,
    set_main_circuit,
)


@pytest.fixture()
def tmp_circ(tmp_path: Path) -> Path:
    return tmp_path / "lab.circ"


def test_create_and_read(tmp_circ: Path) -> None:
    res = create_circuit_file(str(tmp_circ))
    assert Path(res["path"]).exists()
    info = read_circuit_file(str(tmp_circ))
    assert info["main"] == "main"
    assert len(info["circuits"]) == 1
    assert info["circuits"][0]["name"] == "main"
    assert info["libraries"][0]["desc"] == "#Wiring"


def test_list_circuits(tmp_circ: Path) -> None:
    create_circuit_file(str(tmp_circ))
    add_subcircuit(str(tmp_circ), "helper")
    assert list_circuits(str(tmp_circ)) == ["main", "helper"]


def test_rename_main_updates_reference(tmp_circ: Path) -> None:
    create_circuit_file(str(tmp_circ))
    rename_circuit(str(tmp_circ), "main", "top")
    info = read_circuit_file(str(tmp_circ))
    assert info["main"] == "top"
    assert info["circuits"][0]["name"] == "top"


def test_cannot_delete_main(tmp_circ: Path) -> None:
    create_circuit_file(str(tmp_circ))
    with pytest.raises(ValueError):
        delete_circuit(str(tmp_circ), "main")


def test_set_main(tmp_circ: Path) -> None:
    create_circuit_file(str(tmp_circ))
    add_subcircuit(str(tmp_circ), "helper")
    set_main_circuit(str(tmp_circ), "helper")
    info = read_circuit_file(str(tmp_circ))
    assert info["main"] == "helper"
