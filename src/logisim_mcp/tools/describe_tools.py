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

from ..circ.coords import on_segment
from ..circ.library import ComponentSpec, is_output_pin, spec_for_component
from ..circ.model import Circuit, Component, Point, Project, fmt_loc
from ..circ.parser import is_diagonal, parse
from ..server import mcp


# ----- spec lookup ----------------------------------------------------------


def _spec_for(project: Project, comp: Component) -> ComponentSpec | None:
    return spec_for_component(project, comp)


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
    return []  # diagonal — not a conducting segment; Logisim refuses these


def _build_nets(project: Project, circuit: Circuit) -> tuple[dict[Point, int], dict[str, int]]:
    uf = _UF()
    for wire in circuit.wires:
        if is_diagonal(wire):
            continue
        pts = _wire_segments_along(wire.start, wire.end)
        for endpoint in (wire.start, wire.end):
            if endpoint not in pts:
                pts.append(endpoint)
        anchor = pts[0]
        for q in pts[1:]:
            uf.union(anchor, q)

    # A port or wire end sitting on a segment interior is connected, even
    # when the wire was not split at that grid point (Logisim T-junctions).
    extras: list[Point] = []
    for comp in circuit.components:
        spec = _spec_for(project, comp)
        if spec is None:
            continue
        for port in spec.ports:
            extras.append((comp.loc[0] + port.dx, comp.loc[1] + port.dy))
    for wire in circuit.wires:
        extras.append(wire.start)
        extras.append(wire.end)
    for wire in circuit.wires:
        if is_diagonal(wire):
            continue
        for point in extras:
            if on_segment(point, wire.start, wire.end):
                uf.union(wire.start, point)

    # Tunnel labels create equivalences across the whole circuit. Logisim
    # trims surrounding whitespace and ignores an empty label.
    tunnels_by_label: dict[str, list[Point]] = defaultdict(list)
    for c in circuit.components:
        if c.name == "Tunnel":
            label = c.attrs.get("label", "").strip()
            if label:
                tunnels_by_label[label].append(c.loc)
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
            if is_output_pin(c.attrs):
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
            if nid is not None and (lbl := c.attrs.get("label", "").strip()):
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


def _public_port(port: dict[str, Any]) -> dict[str, Any]:
    return {
        "component": port["component"],
        "type": port["type"],
        "label": port["label"],
        "port": port["port"],
        "direction": port["direction"],
        "at": [port["at"][0], port["at"][1]],
    }


def static_drc(project: Project, circuit: Circuit) -> dict[str, Any]:
    """Shorts, floating inputs, pin crossings, and diagonal wires.

    ``error_wires`` is filled in by the Java probe, not here.
    """
    point_to_net, _ = _build_nets(project, circuit)
    ports: list[dict[str, Any]] = []
    for comp in circuit.components:
        spec = _spec_for(project, comp)
        if spec is None:
            continue
        for port in spec.ports:
            at = (comp.loc[0] + port.dx, comp.loc[1] + port.dy)
            ports.append(
                {
                    "component": fmt_loc(comp.loc),
                    "type": spec.type_key,
                    "label": comp.attrs.get("label", ""),
                    "port": port.label,
                    "direction": port.direction,
                    "at": at,
                    "net": point_to_net.get(at),
                }
            )

    grouped: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for port in ports:
        grouped[port["net"]].append(port)

    shorted_nets: list[dict[str, Any]] = []
    floating_inputs: list[dict[str, Any]] = []
    for net_id, members in grouped.items():
        drivers = [item for item in members if item["direction"] == "out"]
        if len(drivers) > 1:
            shorted_nets.append(
                {"net": net_id, "outputs": [_public_port(item) for item in drivers]}
            )
        if not drivers:
            floating_inputs.extend(
                _public_port(item) for item in members if item["direction"] == "in"
            )

    crossings: list[dict[str, Any]] = []
    diagonals: list[dict[str, Any]] = []
    for wire in circuit.wires:
        if is_diagonal(wire):
            diagonals.append({"from": list(wire.start), "to": list(wire.end)})
            continue
        for port in ports:
            if on_segment(port["at"], wire.start, wire.end, interior=True):
                crossings.append(
                    {
                        "from": list(wire.start),
                        "to": list(wire.end),
                        "port": _public_port(port),
                    }
                )
    return {
        "shorted_nets": shorted_nets,
        "floating_inputs": floating_inputs,
        "unintended_pin_crossings": crossings,
        "diagonal_wires": diagonals,
    }


@mcp.tool()
def check_circuit_drc(
    path: str, circuit: str | None = None, probe_errors: bool = True
) -> dict[str, Any]:
    """Static design-rule check, plus a headless count of error-valued wires.

    ``shorted_nets`` have more than one driving port. ``floating_inputs``
    are inputs whose net has no driver. ``unintended_pin_crossings`` are
    wires that pass across a component port without ending on it.
    ``diagonal_wires`` are segments Logisim will reject. ``error_wires``
    is how many wires carry ``Value.ERROR`` after a synchronous propagate;
    it is ``None`` when the Logisim JAR or a JDK is not available.
    """
    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"no such file: {path}")
    project = parse(p)
    name = circuit or project.main
    c = project.require_circuit(name)
    report = static_drc(project, c)
    report["circuit"] = name
    report["error_wires"] = None
    if probe_errors and not report["diagonal_wires"]:
        from ..config import HelperUnavailable, JavaTooOld
        from ..runner.java import LogisimNotFound, count_error_wires

        try:
            report["error_wires"] = count_error_wires(str(p), name)
        except (LogisimNotFound, HelperUnavailable, JavaTooOld, OSError):
            # The static report is still useful on a JRE-only install or
            # when the optional helper cannot be compiled.
            report["error_wires"] = None
    return report
