"""Render a circuit as a compact, human-readable netlist.

The output is the primary "view" an LLM has of the schematic — it cannot
see the GUI, so this text must convey enough structure to reason about
correctness: pins, components, port-to-port connectivity.

Connectivity is computed via union-find over all wire endpoints and
tunnel-label equivalences. Each connected set is reported as one net,
listing the ports that drive or read it.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from ..circ.library import ComponentSpec, resolve, gate_spec, GATE_TYPES
from ..circ.model import Circuit, Component, Point, Project, fmt_loc
from ..circ.parser import parse
from ..server import mcp


# ----- spec lookup ----------------------------------------------------------


def _spec_for(project: Project, comp: Component) -> ComponentSpec | None:
    try:
        desc = project.lib_desc_for_id(comp.lib)
    except KeyError:
        return None
    name = comp.name
    if desc == "#Gates":
        for key, label in GATE_TYPES.items():
            if label == name:
                inputs = int(comp.attrs.get("inputs", "2"))
                return gate_spec(key, inputs=inputs)
        return None
    if desc == "#Wiring":
        if name == "Pin":
            is_out = comp.attrs.get("output", "false") == "true"
            return resolve("OutputPin" if is_out else "InputPin")
        if name == "Tunnel":
            return resolve("Tunnel")
        if name == "Clock":
            return resolve("Clock")
        if name == "Constant":
            return resolve("Constant")
    if desc == "#Plexers" and name in ("Multiplexer", "Demultiplexer", "Decoder"):
        sel = int(comp.attrs.get("select", "1"))
        return resolve(name, select_bits=sel)
    if desc == "#Arithmetic":
        if name == "Adder":
            return resolve("Adder", bits=int(comp.attrs.get("width", "1")))
        if name == "Comparator":
            return resolve("Comparator", bits=int(comp.attrs.get("width", "1")))
    if desc == "#Memory":
        if name == "Register":
            return resolve("Register", bits=int(comp.attrs.get("width", "1")))
        if name == "Counter":
            return resolve("Counter", bits=int(comp.attrs.get("width", "1")))
    return None


# ----- union-find ----------------------------------------------------------


class _UF:
    def __init__(self) -> None:
        self.parent: dict[Any, Any] = {}

    def find(self, x: Any) -> Any:
        if x not in self.parent:
            self.parent[x] = x
            return x
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: Any, b: Any) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def _wire_segments_along(start: Point, end: Point) -> list[Point]:
    """Return every grid-aligned point on a horizontal or vertical wire."""
    if start[0] == end[0]:
        a, b = sorted((start[1], end[1]))
        return [(start[0], y) for y in range(a, b + 1, 10)]
    if start[1] == end[1]:
        a, b = sorted((start[0], end[0]))
        return [(x, start[1]) for x in range(a, b + 1, 10)]
    return [start, end]  # diagonal — preserve endpoints only


def _build_nets(project: Project, circuit: Circuit) -> tuple[dict[Point, int], dict[str, int]]:
    uf = _UF()
    for wire in circuit.wires:
        pts = _wire_segments_along(wire.start, wire.end)
        anchor = pts[0]
        for q in pts[1:]:
            uf.union(anchor, q)

    # Tunnel labels create equivalences across the whole circuit.
    tunnels_by_label: dict[str, list[Point]] = defaultdict(list)
    for c in circuit.components:
        if c.name == "Tunnel":
            tunnels_by_label[c.attrs.get("label", "")].append(c.loc)
    for label, locs in tunnels_by_label.items():
        if len(locs) <= 1:
            continue
        anchor = locs[0]
        for q in locs[1:]:
            uf.union(anchor, q)

    # Ensure every component port participates in a net (even if isolated).
    for c in circuit.components:
        spec = _spec_for(project, c)
        if spec is None:
            continue
        for port in spec.ports:
            uf.find((c.loc[0] + port.dx, c.loc[1] + port.dy))
        uf.find(c.loc)

    # Assign a stable integer id to each net.
    net_ids: dict[Any, int] = {}
    point_to_net: dict[Point, int] = {}
    for key in list(uf.parent.keys()):
        root = uf.find(key)
        if root not in net_ids:
            net_ids[root] = len(net_ids)
        nid = net_ids[root]
        if isinstance(key, tuple) and len(key) == 2 and all(isinstance(v, int) for v in key):
            point_to_net[key] = nid

    label_to_net: dict[str, int] = {}
    for label, locs in tunnels_by_label.items():
        if locs:
            label_to_net[label] = net_ids[uf.find(locs[0])]

    return point_to_net, label_to_net


# ----- rendering -----------------------------------------------------------


def _component_label(c: Component, spec: ComponentSpec | None) -> str:
    label = c.attrs.get("label")
    base = spec.type_key if spec else c.name
    if label:
        return f"{base} {label!r}"
    return base


def _describe(project: Project, circuit: Circuit) -> str:
    point_to_net, _ = _build_nets(project, circuit)
    lines: list[str] = [f'Circuit "{circuit.name}"']

    # Inputs / outputs first.
    input_pins: list[Component] = []
    output_pins: list[Component] = []
    other: list[Component] = []
    for c in circuit.components:
        if c.name == "Pin":
            if c.attrs.get("output", "false") == "true":
                output_pins.append(c)
            else:
                input_pins.append(c)
        elif c.name == "Tunnel":
            continue
        else:
            other.append(c)

    if input_pins or output_pins:
        lines.append("  Pins:")
        for c in input_pins:
            w = c.attrs.get("width", "1")
            lines.append(
                f"    IN   {c.attrs.get('label', '?'):<10} @ {fmt_loc(c.loc)}  {w}-bit"
            )
        for c in output_pins:
            w = c.attrs.get("width", "1")
            lines.append(
                f"    OUT  {c.attrs.get('label', '?'):<10} @ {fmt_loc(c.loc)}  {w}-bit"
            )

    if other:
        lines.append("  Components:")
        for c in other:
            spec = _spec_for(project, c)
            extras = []
            for k in ("inputs", "select", "width", "value"):
                if k in c.attrs:
                    extras.append(f"{k}={c.attrs[k]}")
            extras_str = f"  ({', '.join(extras)})" if extras else ""
            lines.append(
                f"    {_component_label(c, spec):<28} @ {fmt_loc(c.loc)}{extras_str}"
            )

    # Group ports by net. Skip tunnels — their job is to forge equivalences,
    # not to be reported as endpoints.
    net_members: dict[int, list[str]] = defaultdict(list)
    net_tunnel_labels: dict[int, set[str]] = defaultdict(set)
    for c in circuit.components:
        if c.name == "Tunnel":
            spec = _spec_for(project, c)
            if spec is None:
                continue
            pt = (c.loc[0] + spec.ports[0].dx, c.loc[1] + spec.ports[0].dy)
            nid = point_to_net.get(pt)
            if nid is not None and (lbl := c.attrs.get("label")):
                net_tunnel_labels[nid].add(lbl)
            continue
        spec = _spec_for(project, c)
        if spec is None:
            continue
        comp_name = c.attrs.get("label") or spec.type_key
        for port in spec.ports:
            pt = (c.loc[0] + port.dx, c.loc[1] + port.dy)
            nid = point_to_net.get(pt)
            if nid is None:
                continue
            arrow = "->" if port.direction == "out" else "<-"
            net_members[nid].append(f"{comp_name}.{port.label} {arrow}")

    if net_members:
        lines.append("  Nets:")
        for nid in sorted(net_members):
            members = net_members[nid]
            if len(members) <= 1:
                continue
            label_tag = ""
            if labels := net_tunnel_labels.get(nid):
                label_tag = f" [tunnel: {','.join(sorted(labels))}]"
            lines.append(
                f"    net{nid}{label_tag}: " + ", ".join(sorted(set(members)))
            )

    return "\n".join(lines)


# ----- MCP tools -----------------------------------------------------------


@mcp.tool()
def describe_circuit(path: str, circuit: str | None = None) -> dict[str, Any]:
    """Return a text netlist of a circuit (or the project's main circuit).

    Use this to introspect a circuit before editing it: you'll see every
    pin, every component, and every net (with the ports it connects).
    """
    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"no such file: {path}")
    project = parse(p)
    name = circuit or project.main
    c = project.require_circuit(name)
    text = _describe(project, c)
    return {
        "circuit": name,
        "text": text,
        "component_count": len(c.components),
        "wire_count": len(c.wires),
    }


@mcp.tool()
def describe_project(path: str) -> dict[str, Any]:
    """Describe every circuit in a project (concise)."""
    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"no such file: {path}")
    project = parse(p)
    return {
        "path": str(p.resolve()),
        "main": project.main,
        "circuits": [
            {
                "name": c.name,
                "components": len(c.components),
                "wires": len(c.wires),
                "text": _describe(project, c),
            }
            for c in project.circuits
        ],
    }
