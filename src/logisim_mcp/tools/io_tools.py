"""MCP tools that operate on ``.circ`` files as a whole."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..circ.factory import empty_project
from ..circ.model import Circuit, Project
from ..circ.parser import parse
from ..circ.writer import save
from ..server import mcp


def _load(path: str) -> tuple[Path, Project]:
    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"no such file: {path}")
    return p, parse(p)


def _circuit_summary(c: Circuit) -> dict[str, Any]:
    return {
        "name": c.name,
        "component_count": len(c.components),
        "wire_count": len(c.wires),
    }


@mcp.tool()
def create_circuit_file(path: str, main_circuit: str = "main") -> dict[str, Any]:
    """Create a new empty Logisim ``.circ`` file at ``path``.

    The file contains a single circuit named ``main_circuit`` and the
    standard library list (Wiring, Gates, Plexers, Arithmetic, Memory,
    I/O, Base). Returns the absolute path of the created file.
    """
    project = empty_project(main_circuit=main_circuit)
    written = save(project, path)
    return {"path": str(written.resolve()), "main_circuit": main_circuit}


@mcp.tool()
def read_circuit_file(path: str) -> dict[str, Any]:
    """Read a ``.circ`` file and return a summary of its circuits.

    Use this before any other operation to verify the file is well-formed
    and to discover circuit names.
    """
    p, project = _load(path)
    return {
        "path": str(p.resolve()),
        "source": project.source,
        "version": project.version,
        "main": project.main,
        "libraries": [{"id": lib.id, "desc": lib.desc} for lib in project.libs],
        "circuits": [_circuit_summary(c) for c in project.circuits],
    }


@mcp.tool()
def list_circuits(path: str) -> list[str]:
    """Return only the circuit names in ``path`` (small, cheap call)."""
    _, project = _load(path)
    return [c.name for c in project.circuits]


@mcp.tool()
def add_subcircuit(path: str, name: str) -> dict[str, Any]:
    """Add a new empty circuit named ``name`` to the project."""
    p, project = _load(path)
    if project.find_circuit(name) is not None:
        raise ValueError(f"circuit {name!r} already exists")
    project.circuits.append(
        Circuit(
            name=name,
            attrs={"circuit": name, "simulationFrequency": "1.0"},
        )
    )
    save(project, p)
    return {"path": str(p.resolve()), "added": name}


@mcp.tool()
def rename_circuit(path: str, old_name: str, new_name: str) -> dict[str, Any]:
    """Rename a circuit. The ``main`` reference is updated too if needed."""
    p, project = _load(path)
    target = project.require_circuit(old_name)
    if project.find_circuit(new_name) is not None and new_name != old_name:
        raise ValueError(f"circuit {new_name!r} already exists")
    target.name = new_name
    if "circuit" in target.attrs:
        target.attrs["circuit"] = new_name
    if project.main == old_name:
        project.main = new_name
    save(project, p)
    return {"path": str(p.resolve()), "old": old_name, "new": new_name}


@mcp.tool()
def delete_circuit(path: str, name: str) -> dict[str, Any]:
    """Delete a circuit. Refuses to delete the main circuit."""
    p, project = _load(path)
    if name == project.main:
        raise ValueError(
            f"cannot delete the main circuit {name!r}; rename or set a new main first"
        )
    target = project.require_circuit(name)
    project.circuits.remove(target)
    save(project, p)
    return {"path": str(p.resolve()), "deleted": name}


@mcp.tool()
def set_main_circuit(path: str, name: str) -> dict[str, Any]:
    """Mark ``name`` as the project's main (top-level) circuit."""
    p, project = _load(path)
    project.require_circuit(name)
    project.main = name
    save(project, p)
    return {"path": str(p.resolve()), "main": name}
