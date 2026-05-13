"""MCP tools that mutate the contents of a circuit.

Components are referenced by their **id**, which is the location string
``"(x,y)"`` Logisim itself uses. Every mutation re-saves the file so
parallel MCP calls always observe consistent state.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..circ.coords import (
    auto_place,
    bbox_corners,
    port_location,
    route_l,
    snap,
)
from ..circ.library import ComponentSpec, resolve
from ..circ.model import Component, Point, Project, Wire, fmt_loc, parse_loc
from ..circ.parser import parse
from ..circ.writer import save
from ..server import mcp


def _load(path: str) -> tuple[Path, Project]:
    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"no such file: {path}")
    return p, parse(p)


def _spec_for_component(project: Project, comp: Component) -> ComponentSpec:
    """Best-effort spec lookup for an existing component."""
    desc = project.lib_desc_for_id(comp.lib)
    if desc == "#Gates":
        inputs = int(comp.attrs.get("inputs", "2"))
        from ..circ.library import GATE_TYPES, gate_spec

        key = next((k for k, v in GATE_TYPES.items() if v == comp.name), None)
        if key is None:
            raise KeyError(f"unknown gate component name {comp.name!r}")
        return gate_spec(key, inputs=inputs)
    if desc == "#Wiring":
        if comp.name == "Pin":
            is_out = comp.attrs.get("output", "false") == "true"
            return resolve("OutputPin" if is_out else "InputPin")
        if comp.name == "Tunnel":
            return resolve("Tunnel")
        if comp.name == "Clock":
            return resolve("Clock")
        if comp.name == "Constant":
            return resolve("Constant")
    if desc == "#Plexers":
        if comp.name == "Multiplexer":
            sel = int(comp.attrs.get("select", "1"))
            return resolve("Multiplexer", select_bits=sel)
        if comp.name == "Demultiplexer":
            sel = int(comp.attrs.get("select", "1"))
            return resolve("Demultiplexer", select_bits=sel)
        if comp.name == "Decoder":
            sel = int(comp.attrs.get("select", "1"))
            return resolve("Decoder", select_bits=sel)
    if desc == "#Arithmetic":
        if comp.name == "Adder":
            return resolve("Adder", bits=int(comp.attrs.get("width", "1")))
        if comp.name == "Comparator":
            return resolve("Comparator", bits=int(comp.attrs.get("width", "1")))
    if desc == "#Memory":
        if comp.name == "Register":
            return resolve("Register", bits=int(comp.attrs.get("width", "1")))
        if comp.name == "Counter":
            return resolve("Counter", bits=int(comp.attrs.get("width", "1")))
    raise KeyError(
        f"no spec for {comp.name!r} from {desc!r}; "
        "use add_component with explicit attrs for unsupported types"
    )


def _occupied(project: Project, circuit_name: str) -> list[tuple[Point, Point]]:
    circuit = project.require_circuit(circuit_name)
    boxes: list[tuple[Point, Point]] = []
    for c in circuit.components:
        try:
            spec = _spec_for_component(project, c)
        except KeyError:
            continue
        boxes.append(bbox_corners(c, spec))
    return boxes


def _resolve_loc(project: Project, circuit_name: str, spec: ComponentSpec,
                 x: int | None, y: int | None) -> Point:
    if x is not None and y is not None:
        return snap((x, y))
    return auto_place(_occupied(project, circuit_name), spec)


def _ensure_lib(project: Project, desc: str) -> str:
    return project.lib_id_for_desc(desc)


def _attach(
    project: Project,
    circuit_name: str,
    spec: ComponentSpec,
    loc: Point,
    extra_attrs: dict[str, str] | None = None,
) -> Component:
    circuit = project.require_circuit(circuit_name)
    attrs = dict(spec.default_attrs)
    if extra_attrs:
        attrs.update(extra_attrs)
    component = Component(
        lib=_ensure_lib(project, spec.lib_desc),
        name=spec.logisim_name,
        loc=loc,
        attrs=attrs,
    )
    circuit.components.append(component)
    return component


# ---------------------------------------------------------------- tools


@mcp.tool()
def add_pin(
    path: str,
    circuit: str,
    label: str,
    is_output: bool = False,
    bit_width: int = 1,
    x: int | None = None,
    y: int | None = None,
) -> dict[str, Any]:
    """Add an input or output Pin to ``circuit`` with the given label.

    Inputs face east (data flows out of the pin into the circuit); outputs
    face west. ``bit_width`` is the bus width (1 for a single wire).
    """
    p, project = _load(path)
    spec = resolve("OutputPin" if is_output else "InputPin")
    loc = _resolve_loc(project, circuit, spec, x, y)
    extra = {"label": label}
    if bit_width != 1:
        extra["width"] = str(bit_width)
    component = _attach(project, circuit, spec, loc, extra)
    save(project, p)
    return {"id": fmt_loc(loc), "loc": loc, "label": label, "is_output": is_output}


@mcp.tool()
def add_gate(
    path: str,
    circuit: str,
    gate_type: str,
    inputs: int = 2,
    bit_width: int = 1,
    x: int | None = None,
    y: int | None = None,
    label: str | None = None,
) -> dict[str, Any]:
    """Add a logic gate (AND/OR/NAND/NOR/XOR/XNOR/NOT/BUF).

    Returns the component id (its location string) and the resolved
    location so the caller can wire it up.
    """
    from ..circ.library import gate_spec

    p, project = _load(path)
    spec = gate_spec(gate_type, inputs=inputs)
    loc = _resolve_loc(project, circuit, spec, x, y)
    extra: dict[str, str] = {}
    if bit_width != 1:
        extra["width"] = str(bit_width)
    if label:
        extra["label"] = label
    component = _attach(project, circuit, spec, loc, extra)
    save(project, p)
    return {
        "id": fmt_loc(loc),
        "loc": loc,
        "gate_type": gate_type.upper(),
        "inputs": inputs,
    }


@mcp.tool()
def add_component(
    path: str,
    circuit: str,
    type_key: str,
    attrs: dict[str, str] | None = None,
    bits: int = 1,
    select_bits: int = 1,
    x: int | None = None,
    y: int | None = None,
) -> dict[str, Any]:
    """Generic component placer.

    ``type_key`` is one of the keys in
    :data:`logisim_mcp.circ.library.SPEC_FACTORIES` — e.g. ``"Multiplexer"``,
    ``"Adder"``, ``"Register"``, ``"Counter"``, ``"Constant"``, ``"Clock"``.
    """
    p, project = _load(path)
    spec = resolve(type_key, bits=bits, select_bits=select_bits)
    loc = _resolve_loc(project, circuit, spec, x, y)
    component = _attach(project, circuit, spec, loc, attrs or {})
    save(project, p)
    return {"id": fmt_loc(loc), "loc": loc, "type": type_key}


@mcp.tool()
def add_wire(
    path: str,
    circuit: str,
    from_xy: tuple[int, int],
    to_xy: tuple[int, int],
) -> dict[str, Any]:
    """Add a wire segment (or an L-shaped pair) between two grid points."""
    p, project = _load(path)
    c = project.require_circuit(circuit)
    wires = route_l(tuple(from_xy), tuple(to_xy))
    c.wires.extend(wires)
    save(project, p)
    return {"wires_added": len(wires)}


@mcp.tool()
def connect(
    path: str,
    circuit: str,
    from_id: str,
    from_port: str,
    to_id: str,
    to_port: str,
) -> dict[str, Any]:
    """High-level connect — looks up port coordinates and routes an L-wire.

    ``from_id`` / ``to_id`` are component ids (``"(x,y)"`` strings as
    returned by ``add_gate`` / ``add_component``). ``from_port`` and
    ``to_port`` are port labels listed in ``library.ComponentSpec.ports``
    (e.g. ``"in0"``, ``"in1"``, ``"out"``, ``"sum"``, ``"cin"``, ``"D"``,
    ``"clk"``).
    """
    p, project = _load(path)
    c = project.require_circuit(circuit)
    src = c.find_component(parse_loc(from_id))
    if src is None:
        raise KeyError(f"no component at {from_id!r}")
    dst = c.find_component(parse_loc(to_id))
    if dst is None:
        raise KeyError(f"no component at {to_id!r}")
    src_spec = _spec_for_component(project, src)
    dst_spec = _spec_for_component(project, dst)
    a = port_location(src, src_spec, from_port)
    b = port_location(dst, dst_spec, to_port)
    wires = route_l(a, b)
    c.wires.extend(wires)
    save(project, p)
    return {"from": a, "to": b, "wires_added": len(wires)}


@mcp.tool()
def add_tunnel(
    path: str,
    circuit: str,
    label: str,
    x: int,
    y: int,
    facing: str = "west",
) -> dict[str, Any]:
    """Add a named tunnel (wireless connection node).

    Two tunnels with the same label in the same circuit are electrically
    one net. Great for clean schematics with many crossings.
    """
    p, project = _load(path)
    spec = resolve("Tunnel")
    loc = snap((x, y))
    extra = {"label": label, "facing": facing}
    _attach(project, circuit, spec, loc, extra)
    save(project, p)
    return {"id": fmt_loc(loc), "loc": loc, "label": label}


@mcp.tool()
def remove_component(path: str, circuit: str, component_id: str) -> dict[str, Any]:
    """Remove the component whose location string matches ``component_id``."""
    p, project = _load(path)
    c = project.require_circuit(circuit)
    target = c.find_component(parse_loc(component_id))
    if target is None:
        raise KeyError(f"no component at {component_id!r}")
    c.components.remove(target)
    save(project, p)
    return {"removed": component_id}
