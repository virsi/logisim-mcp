"""High-level circuit builders.

Each builder emits a self-contained sub-circuit named by the caller.
Builders use **tunnels** for fan-out (a signal that drives more than one
gate input) so the resulting schematic is clean and electrically correct.
Hand-routed L-wires can short-circuit two distinct nets at a shared
midpoint; tunnels sidestep that entirely.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from ..circ.coords import RouteBlocked, on_segment, port_location, route_l, snap
from ..circ.library import (
    ComponentSpec,
    circuit_port_points,
    gate_spec,
    input_pin_spec,
    output_pin_spec,
    resolve,
    tunnel_spec,
)
from ..circ.model import Circuit, Component, Point, Project, Wire, fmt_loc
from ..circ.parser import parse
from ..circ.writer import save
from ..server import mcp


# ---------- shared helpers ---------------------------------------------------


def _load(path: str) -> tuple[Path, Project]:
    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"no such file: {path}")
    return p, parse(p)


def _ensure_circuit(project: Project, name: str) -> Circuit:
    existing = project.find_circuit(name)
    if existing is not None:
        return existing
    circuit = Circuit(
        name=name,
        attrs={"circuit": name, "simulationFrequency": "1.0"},
    )
    project.circuits.append(circuit)
    return circuit


def _place(
    project: Project,
    circuit: Circuit,
    spec: ComponentSpec,
    loc: Point,
    extra: dict[str, str] | None = None,
) -> Component:
    attrs = dict(spec.default_attrs)
    if extra:
        attrs.update(extra)
    component = Component(
        lib=project.lib_id_for_desc(spec.lib_desc),
        name=spec.logisim_name,
        loc=snap(loc),
        attrs=attrs,
    )
    circuit.components.append(component)
    return component


def _add_tunnel(
    project: Project,
    circuit: Circuit,
    label: str,
    loc: Point,
    facing: str = "west",
    width: int = 1,
) -> Component:
    attrs = {"label": label, "facing": facing}
    if width != 1:
        attrs["width"] = str(width)
    return _place(project, circuit, tunnel_spec(), loc, attrs)


def _route(project: Project, circuit: Circuit, a: Point, b: Point) -> None:
    circuit.wires.extend(
        route_l(a, b, circuit_port_points(project, circuit), circuit.wires)
    )


def _add_input_pin(
    project: Project, circuit: Circuit, label: str, loc: Point, bit_width: int = 1
) -> Component:
    extra: dict[str, str] = {"label": label}
    if bit_width != 1:
        extra["width"] = str(bit_width)
    return _place(project, circuit, input_pin_spec(), loc, extra)


def _add_output_pin(
    project: Project, circuit: Circuit, label: str, loc: Point, bit_width: int = 1
) -> Component:
    extra: dict[str, str] = {"label": label}
    if bit_width != 1:
        extra["width"] = str(bit_width)
    return _place(project, circuit, output_pin_spec(), loc, extra)


def _existing_tunnel(circuit: Circuit, label: str, loc: Point) -> bool:
    for c in circuit.components:
        if c.name == "Tunnel" and c.attrs.get("label") == label and c.loc == loc:
            return True
    return False


def _route_direct(project: Project, circuit: Circuit, source: Point, target: Point) -> None:
    """Plain wire (or L-pair) from ``source`` to ``target``.

    Use when there is no fan-out — drops the tunnel pair and avoids the
    risk of nearby target-tunnels colliding through a shared grid point.
    """
    _route(project, circuit, source, target)


def _port_at(comp: Component, spec: ComponentSpec, port_label: str) -> Point:
    port = spec.port_by_label(port_label)
    return (comp.loc[0] + port.dx, comp.loc[1] + port.dy)


def _link_via_tunnel(
    project: Project,
    circuit: Circuit,
    label: str,
    source: Point,
    target: Point,
    width: int = 1,
) -> None:
    """Route ``source`` and ``target`` to identically-labeled tunnels.

    Tunnels with the same label are electrically one net regardless of
    position, so this both removes wires-crossing-wires and prevents
    the multi-driver shorts that a naive L-router would produce on fan-out.

    The source-side tunnel is placed only once per ``label`` — repeat
    calls for the same source act as additional fan-out branches.
    """
    src_tunnel = snap((source[0] + 30, source[1]))
    dst_tunnel = snap((target[0] - 30, target[1]))
    if not _existing_tunnel(circuit, label, src_tunnel):
        _add_tunnel(project, circuit, label, src_tunnel, facing="west", width=width)
        _route(project, circuit, source, src_tunnel)
    if not _existing_tunnel(circuit, label, dst_tunnel):
        _add_tunnel(project, circuit, label, dst_tunnel, facing="east", width=width)
        _route(project, circuit, dst_tunnel, target)


def _summary(circuit: Circuit) -> dict[str, Any]:
    return {
        "components": len(circuit.components),
        "wires": len(circuit.wires),
    }


# ---------- half / full / ripple adder --------------------------------------


@mcp.tool()
def build_half_adder(path: str, circuit_name: str = "half_adder") -> dict[str, Any]:
    """Build a 1-bit half-adder (A, B → Sum, Cout) inside ``circuit_name``.

    Layout: pins on the left, XOR/AND on the right, output pins on the
    far right. Fan-out from A/B uses tunnels.
    """
    p, project = _load(path)
    c = _ensure_circuit(project, circuit_name)
    if c.components or c.wires:
        raise ValueError(
            f"circuit {circuit_name!r} is not empty; "
            "create a fresh circuit or pick a new name"
        )

    a_pin = _add_input_pin(project, c, "A", (100, 100))
    b_pin = _add_input_pin(project, c, "B", (100, 200))
    xor = _place(project, c, gate_spec("XOR"), (320, 110))
    and_ = _place(project, c, gate_spec("AND"), (320, 210))
    sum_pin = _add_output_pin(project, c, "Sum", (440, 110))
    cout_pin = _add_output_pin(project, c, "Cout", (440, 210))

    # XOR.in0 = (320-60, 110-20) = (260, 90), XOR.in1 = (260, 130).
    # AND.in0 = (320-50, 210-20) = (270, 190), AND.in1 = (270, 230).
    _link_via_tunnel(project, c, "A", a_pin.loc, (260, 90))
    _link_via_tunnel(project, c, "A", a_pin.loc, (270, 190))
    _link_via_tunnel(project, c, "B", b_pin.loc, (260, 130))
    _link_via_tunnel(project, c, "B", b_pin.loc, (270, 230))
    _route(project, c, xor.loc, sum_pin.loc)
    _route(project, c, and_.loc, cout_pin.loc)

    save(project, p)
    return {"circuit": circuit_name, **_summary(c)}


@mcp.tool()
def build_full_adder(path: str, circuit_name: str = "full_adder") -> dict[str, Any]:
    """Build a 1-bit full-adder (A, B, Cin → Sum, Cout)."""
    p, project = _load(path)
    c = _ensure_circuit(project, circuit_name)
    if c.components or c.wires:
        raise ValueError(f"circuit {circuit_name!r} is not empty")

    a_pin = _add_input_pin(project, c, "A", (100, 100))
    b_pin = _add_input_pin(project, c, "B", (100, 200))
    cin_pin = _add_input_pin(project, c, "Cin", (100, 300))

    # X1: A xor B; A2: A and B; X2: X1 xor Cin (=Sum); A3: X1 and Cin;
    # OR_g: A2 or A3 (=Cout).
    x1 = _place(project, c, gate_spec("XOR"), (320, 110))   # A xor B
    a2 = _place(project, c, gate_spec("AND"), (320, 220))   # A and B
    x2 = _place(project, c, gate_spec("XOR"), (520, 110))   # Sum
    a3 = _place(project, c, gate_spec("AND"), (520, 220))   # X1 and Cin
    or_g = _place(project, c, gate_spec("OR"), (720, 220))  # Cout

    sum_pin = _add_output_pin(project, c, "Sum", (640, 110))
    cout_pin = _add_output_pin(project, c, "Cout", (840, 220))

    # A fan-out via tunnels
    _link_via_tunnel(project, c, "A", a_pin.loc, (260, 90))   # X1.in0
    _link_via_tunnel(project, c, "A", a_pin.loc, (270, 200))  # A2.in0
    # B fan-out
    _link_via_tunnel(project, c, "B", b_pin.loc, (260, 130))  # X1.in1
    _link_via_tunnel(project, c, "B", b_pin.loc, (270, 240))  # A2.in1
    # Cin fan-out (to X2.in1 and A3.in1)
    _link_via_tunnel(project, c, "Cin", cin_pin.loc, (460, 130))
    _link_via_tunnel(project, c, "Cin", cin_pin.loc, (470, 240))
    # X1.out fan-out to X2.in0 and A3.in0 (use tunnel "X1")
    _link_via_tunnel(project, c, "X1", x1.loc, (460, 90))   # X2.in0
    _link_via_tunnel(project, c, "X1", x1.loc, (470, 200))  # A3.in0
    # Sum: X2.out -> Sum pin
    _route(project, c, x2.loc, sum_pin.loc)
    # OR_g.in0 <= A2.out, OR_g.in1 <= A3.out, OR_g.out -> Cout.
    or_spec = gate_spec("OR")
    or_in0 = (or_g.loc[0] + or_spec.input_port(0).dx, or_g.loc[1] + or_spec.input_port(0).dy)
    or_in1 = (or_g.loc[0] + or_spec.input_port(1).dx, or_g.loc[1] + or_spec.input_port(1).dy)
    _link_via_tunnel(project, c, "P1", a2.loc, or_in0)
    _link_via_tunnel(project, c, "P2", a3.loc, or_in1)
    _route(project, c, or_g.loc, cout_pin.loc)

    save(project, p)
    return {"circuit": circuit_name, **_summary(c)}


@mcp.tool()
def build_ripple_adder(
    path: str, bits: int, circuit_name: str = "ripple_adder"
) -> dict[str, Any]:
    """Build an N-bit ripple-carry adder using the built-in ``Adder`` component.

    Inputs are buses ``A`` and ``B`` of width ``bits``; outputs are
    ``Sum`` (``bits`` wide) and ``Cout``. This is much faster than
    chaining individual full-adders and matches what students typically
    use in coursework.
    """
    if bits < 1 or bits > 32:
        raise ValueError("bits must be in [1, 32]")
    p, project = _load(path)
    c = _ensure_circuit(project, circuit_name)
    if c.components or c.wires:
        raise ValueError(f"circuit {circuit_name!r} is not empty")

    spec = resolve("Adder", bits=bits)
    adder = _place(project, c, spec, (320, 140), {"width": str(bits)})

    # Pins arranged so their L-routes avoid every adder port:
    #   adder ports are at x∈{280, 300, 320}; choose pin y-coords that are
    #   different from each port's y, so the vertical legs don't graze them.
    a_pin = _add_input_pin(project, c, "A", (100, 130), bit_width=bits)
    b_pin = _add_input_pin(project, c, "B", (100, 200), bit_width=bits)
    cin_pin = _add_input_pin(project, c, "Cin", (100, 60))
    sum_pin = _add_output_pin(project, c, "Sum", (500, 140), bit_width=bits)
    cout_pin = _add_output_pin(project, c, "Cout", (500, 240))

    _route_direct(project, c, a_pin.loc, _port_at(adder, spec, "a"))
    _route_direct(project, c, b_pin.loc, _port_at(adder, spec, "b"))
    # Cin pin sits above; route up the left of the adder.
    _route(project, c, cin_pin.loc, (280, 60))
    _route(project, c, (280, 60), (280, 120))
    _route(project, c, (280, 120), _port_at(adder, spec, "cin"))
    _route_direct(project, c, adder.loc, sum_pin.loc)
    # Cout pin sits below; route around the right.
    _route(project, c, _port_at(adder, spec, "cout"), (340, 160))
    _route(project, c, (340, 160), (340, 240))
    _route(project, c, (340, 240), cout_pin.loc)

    save(project, p)
    return {"circuit": circuit_name, "bits": bits, **_summary(c)}


# ---------- mux / decoder / comparator --------------------------------------


@mcp.tool()
def build_mux(
    path: str,
    select_bits: int = 1,
    data_bits: int = 1,
    circuit_name: str = "mux",
) -> dict[str, Any]:
    """Build a multiplexer with ``2**select_bits`` data inputs.

    Each data input is named ``D0``, ``D1``, …; the select bus is ``Sel``;
    output is ``Y``.
    """
    if select_bits < 1 or select_bits > 5:
        raise ValueError("select_bits must be in [1, 5]")
    p, project = _load(path)
    c = _ensure_circuit(project, circuit_name)
    if c.components or c.wires:
        raise ValueError(f"circuit {circuit_name!r} is not empty")

    spec = resolve("Multiplexer", select_bits=select_bits)
    n_data = 1 << select_bits
    mux = _place(
        project,
        c,
        spec,
        (480, 200),
        {"select": str(select_bits), "width": str(data_bits)},
    )

    # Lay out data input pins on the left, one per row.
    for i in range(n_data):
        pin = _add_input_pin(
            project, c, f"D{i}", (100, 100 + i * 40), bit_width=data_bits
        )
        port = spec.port_by_label(f"d{i}")
        target = (mux.loc[0] + port.dx, mux.loc[1] + port.dy)
        _link_via_tunnel(project, c, f"D{i}", pin.loc, target, width=data_bits)

    sel_pin = _add_input_pin(project, c, "Sel", (320, 100 + n_data * 40), bit_width=select_bits)
    sel_port = spec.port_by_label("sel")
    sel_target = (mux.loc[0] + sel_port.dx, mux.loc[1] + sel_port.dy)
    _link_via_tunnel(project, c, "Sel", sel_pin.loc, sel_target, width=select_bits)

    y_pin = _add_output_pin(project, c, "Y", (640, mux.loc[1]), bit_width=data_bits)
    _route(project, c, mux.loc, y_pin.loc)

    save(project, p)
    return {
        "circuit": circuit_name,
        "select_bits": select_bits,
        "data_bits": data_bits,
        **_summary(c),
    }


@mcp.tool()
def build_decoder(
    path: str, select_bits: int = 1, circuit_name: str = "decoder"
) -> dict[str, Any]:
    """Build an n-to-2^n decoder."""
    if select_bits < 1 or select_bits > 5:
        raise ValueError("select_bits must be in [1, 5]")
    p, project = _load(path)
    c = _ensure_circuit(project, circuit_name)
    if c.components or c.wires:
        raise ValueError(f"circuit {circuit_name!r} is not empty")

    spec = resolve("Decoder", select_bits=select_bits)
    n_out = 1 << select_bits
    dec = _place(project, c, spec, (380, 200), {"select": str(select_bits)})

    sel_pin = _add_input_pin(project, c, "Sel", (100, 200), bit_width=select_bits)
    sel_port = spec.port_by_label("sel")
    _link_via_tunnel(
        project,
        c,
        "Sel",
        sel_pin.loc,
        (dec.loc[0] + sel_port.dx, dec.loc[1] + sel_port.dy),
        width=select_bits,
    )

    for i in range(n_out):
        port = spec.port_by_label(f"q{i}")
        target_pin = _add_output_pin(project, c, f"Q{i}", (560, dec.loc[1] + port.dy))
        _route(project, c, (dec.loc[0] + port.dx, dec.loc[1] + port.dy), target_pin.loc)

    save(project, p)
    return {"circuit": circuit_name, "select_bits": select_bits, **_summary(c)}


@mcp.tool()
def build_comparator(
    path: str, bits: int = 1, circuit_name: str = "comparator"
) -> dict[str, Any]:
    """Build an N-bit magnitude comparator (A>B, A==B, A<B)."""
    if bits < 1 or bits > 32:
        raise ValueError("bits must be in [1, 32]")
    p, project = _load(path)
    c = _ensure_circuit(project, circuit_name)
    if c.components or c.wires:
        raise ValueError(f"circuit {circuit_name!r} is not empty")

    spec = resolve("Comparator", bits=bits)
    # Logisim's built-in default is two's complement. A magnitude comparator
    # compares the bit patterns as unsigned.
    cmp = _place(
        project, c, spec, (380, 200), {"width": str(bits), "mode": "unsigned"}
    )

    a_pin = _add_input_pin(project, c, "A", (100, 180), bit_width=bits)
    b_pin = _add_input_pin(project, c, "B", (100, 220), bit_width=bits)
    _link_via_tunnel(project, c, "A", a_pin.loc, (cmp.loc[0] - 40, cmp.loc[1] - 10), width=bits)
    _link_via_tunnel(project, c, "B", b_pin.loc, (cmp.loc[0] - 40, cmp.loc[1] + 10), width=bits)

    for label, port_label, dy in (("Gt", "gt", -10), ("Eq", "eq", 0), ("Lt", "lt", 10)):
        pin = _add_output_pin(project, c, label, (520, cmp.loc[1] + dy))
        _route(project, c, (cmp.loc[0], cmp.loc[1] + dy), pin.loc)

    save(project, p)
    return {"circuit": circuit_name, "bits": bits, **_summary(c)}


# ---------- sequential: register / counter ----------------------------------


@mcp.tool()
def build_register(
    path: str, bits: int = 1, circuit_name: str = "register"
) -> dict[str, Any]:
    """Build a single rising-edge register.

    Exposed pins (all surfaced so the LLM can drive them in test vectors):
    ``D``, ``Clk``, ``En``, ``Rst``, ``Q``.
    """
    if bits < 1 or bits > 32:
        raise ValueError("bits must be in [1, 32]")
    p, project = _load(path)
    c = _ensure_circuit(project, circuit_name)
    if c.components or c.wires:
        raise ValueError(f"circuit {circuit_name!r} is not empty")

    spec = resolve("Register", bits=bits)
    # Register evolution: top-left anchor at (300, 100). Ports:
    #   D@(300,130) en@(300,150) clk@(300,170) rst@(330,190) Q@(360,130).
    reg = _place(project, c, spec, (300, 100), {"width": str(bits)})

    d_port = _port_at(reg, spec, "D")
    clk_port = _port_at(reg, spec, "clk")
    en_port = _port_at(reg, spec, "en")
    rst_port = _port_at(reg, spec, "rst")
    q_port = _port_at(reg, spec, "Q")

    d_pin = _add_input_pin(project, c, "D", (180, 130), bit_width=bits)
    en_pin = _add_input_pin(project, c, "En", (180, 150))
    clk_pin = _add_input_pin(project, c, "Clk", (180, 170))
    rst_pin = _add_input_pin(project, c, "Rst", (330, 280))
    q_pin = _add_output_pin(project, c, "Q", (460, 130), bit_width=bits)

    _route_direct(project, c, d_pin.loc, d_port)
    _route_direct(project, c, en_pin.loc, en_port)
    _route_direct(project, c, clk_pin.loc, clk_port)
    # Rst comes from below (the rst port is on the *bottom* edge).
    _route(project, c, rst_pin.loc, (330, 230))
    _route(project, c, (330, 230), rst_port)
    _route_direct(project, c, q_port, q_pin.loc)

    save(project, p)
    return {"circuit": circuit_name, "bits": bits, **_summary(c)}


@mcp.tool()
def build_counter(
    path: str, bits: int = 1, circuit_name: str = "counter"
) -> dict[str, Any]:
    """Build an N-bit synchronous counter (rising-edge).

    Exposed pins: ``D``, ``Clk``, ``Load``, ``Clr``, ``En``, ``UD``,
    ``Q``, ``Carry``. Drive ``UD`` high to count up, low to count down.
    Drive ``En`` high to allow counting.
    """
    if bits < 1 or bits > 32:
        raise ValueError("bits must be in [1, 32]")
    p, project = _load(path)
    c = _ensure_circuit(project, circuit_name)
    if c.components or c.wires:
        raise ValueError(f"circuit {circuit_name!r} is not empty")

    spec = resolve("Counter", bits=bits)
    ctr = _place(project, c, spec, (300, 100), {"width": str(bits)})

    clr_port = _port_at(ctr, spec, "clr")
    ld_port = _port_at(ctr, spec, "ld")
    ud_port = _port_at(ctr, spec, "ud")
    en_port = _port_at(ctr, spec, "en")
    clk_port = _port_at(ctr, spec, "clk")
    d_port = _port_at(ctr, spec, "D")
    q_port = _port_at(ctr, spec, "Q")
    carry_port = _port_at(ctr, spec, "carry")

    clr_pin = _add_input_pin(project, c, "Clr", (180, clr_port[1]))
    ld_pin = _add_input_pin(project, c, "Load", (180, ld_port[1]))
    ud_pin = _add_input_pin(project, c, "UD", (180, ud_port[1]))
    en_pin = _add_input_pin(project, c, "En", (180, en_port[1]))
    clk_pin = _add_input_pin(project, c, "Clk", (180, clk_port[1]))
    d_pin = _add_input_pin(project, c, "D", (180, d_port[1]), bit_width=bits)
    q_pin = _add_output_pin(project, c, "Q", (q_port[0] + 100, q_port[1]), bit_width=bits)
    carry_pin = _add_output_pin(project, c, "Carry", (carry_port[0] + 100, carry_port[1]))

    _route_direct(project, c, clr_pin.loc, clr_port)
    _route_direct(project, c, ld_pin.loc, ld_port)
    _route_direct(project, c, ud_pin.loc, ud_port)
    _route_direct(project, c, en_pin.loc, en_port)
    _route_direct(project, c, clk_pin.loc, clk_port)
    _route_direct(project, c, d_pin.loc, d_port)
    _route_direct(project, c, q_port, q_pin.loc)
    _route_direct(project, c, carry_port, carry_pin.loc)

    save(project, p)
    return {"circuit": circuit_name, "bits": bits, **_summary(c)}


# ---------- build_from_truth_table (SOP synthesis) --------------------------

_OR_FANIN = 5


def _wire_points(wire: Wire) -> list[Point]:
    x1, y1 = wire.start
    x2, y2 = wire.end
    if x1 == x2:
        step = 10 if y2 >= y1 else -10
        return [(x1, y) for y in range(y1, y2 + step, step)]
    if y1 == y2:
        step = 10 if x2 >= x1 else -10
        return [(x, y1) for x in range(x1, x2 + step, step)]
    return [wire.start, wire.end]


def _busy_points(project: Project, circuit: Circuit) -> set[Point]:
    points = set(circuit_port_points(project, circuit))
    points.update(comp.loc for comp in circuit.components)
    for wire in circuit.wires:
        points.update(_wire_points(wire))
    return points


def _tunnel_spots(near: Point) -> Iterable[Point]:
    """Grid points around ``near``, axis-aligned neighbors first."""
    px, py = near
    for radius in range(1, 30):
        ring: list[Point] = []
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if max(abs(dx), abs(dy)) != radius:
                    continue
                ring.append((px + dx * 10, py + dy * 10))
        ring.sort(
            key=lambda point: (
                0 if point[0] == px or point[1] == py else 1,
                abs(point[0] - px) + abs(point[1] - py),
            )
        )
        yield from ring


def _hop(
    project: Project,
    circuit: Circuit,
    label: str,
    end: Point,
    toward: Point,
    facing: str,
) -> None:
    """Put one tunnel near ``toward`` and wire it to ``end``.

    The spot is rejected when it already carries a port or wire, or when
    the short wire would have to cross another net.
    """
    busy = _busy_points(project, circuit)
    for spot in _tunnel_spots(toward):
        if spot in busy or spot == end:
            continue
        if any(on_segment(spot, wire.start, wire.end) for wire in circuit.wires):
            continue
        tunnel = _add_tunnel(project, circuit, label, spot, facing=facing)
        kept = len(circuit.wires)
        try:
            _route(project, circuit, end, spot)
            return
        except RouteBlocked:
            circuit.components.remove(tunnel)
            del circuit.wires[kept:]
    raise RuntimeError(f"no free tunnel for {label} near {toward}")


def _tap(project: Project, circuit: Circuit, label: str, source: Point, target: Point) -> None:
    """Connect ``source`` to ``target`` through a uniquely placed tunnel pair.

    The west-facing tunnel is the source and is created once per label, so
    later taps are extra fan-out. Destination tunnels are searched for a
    free coordinate, which is what keeps two nets from landing on one point.
    """
    has_source = any(
        comp.name == "Tunnel"
        and comp.attrs.get("label") == label
        and comp.attrs.get("facing") == "west"
        for comp in circuit.components
    )
    if not has_source:
        _hop(project, circuit, label, source, (source[0] + 20, source[1]), "west")
    _hop(project, circuit, label, target, (target[0] - 20, target[1]), "east")


def _or_tree(
    project: Project,
    circuit: Circuit,
    points: list[Point],
    tag: str,
    origin_x: int,
    origin_y: int,
    label_prefix: str,
) -> tuple[Point, Point]:
    """Combine ``points`` with a tree of at most 5-input OR gates.

    Returns the final signal point and a dedicated output-pin location.
    Each output owns a distinct ``origin_y`` band, and gates within a band
    are stacked by group so separate truth-table outputs never share a
    gate or pin even when a term is just an input pin.
    """
    layer = list(points)
    level = 0
    while len(layer) > 1:
        nxt: list[Point] = []
        groups = [layer[i : i + _OR_FANIN] for i in range(0, len(layer), _OR_FANIN)]
        for index, group in enumerate(groups):
            if len(group) == 1:
                nxt.append(group[0])
                continue
            spec = gate_spec("OR", inputs=len(group))
            or_loc = (origin_x + level * 220, origin_y + index * 80)
            _place(project, circuit, spec, or_loc, {"inputs": str(len(group))})
            for slot, src in enumerate(group):
                port = spec.input_port(slot)
                _tap(
                    project,
                    circuit,
                    f"{label_prefix}or_{tag}_{level}_{index}_{slot}",
                    src,
                    (or_loc[0] + port.dx, or_loc[1] + port.dy),
                )
            nxt.append(or_loc)
        layer = nxt
        level += 1
    pin_loc = (origin_x + level * 220 + 160, origin_y)
    return layer[0], pin_loc


@mcp.tool()
def build_from_truth_table(
    path: str,
    inputs: list[str],
    outputs: list[str],
    rows: list[list[str]],
    circuit_name: str = "synthesized",
) -> dict[str, Any]:
    """Synthesize a combinational circuit from a truth table (SOP form).

    ``rows`` is a list of ``[in0, in1, …, out0, out1, …]``. ``"-"`` /
    ``"x"`` in inputs means don't-care (the row covers all values of
    that variable). Each output gets its own sum-of-products tree.
    Every minterm is connected. An OR wider than five inputs becomes a
    tree of 5-input gates rather than a gate that drops the extra terms.

    Inputs and outputs are 1-bit. At most 8 inputs.
    """
    if not inputs or not outputs:
        raise ValueError("inputs and outputs must be non-empty")
    if len(inputs) > 8:
        raise ValueError("at most 8 inputs supported")
    expected = len(inputs) + len(outputs)
    for i, row in enumerate(rows):
        if len(row) != expected:
            raise ValueError(
                f"row {i} has {len(row)} values; expected {expected}"
            )

    p, project = _load(path)
    c = _ensure_circuit(project, circuit_name)
    if c.components or c.wires:
        raise ValueError(f"circuit {circuit_name!r} is not empty")

    reserved = set(inputs) | set(outputs)
    reserved.update(
        comp.attrs.get("label", "")
        for comp in c.components
        if comp.attrs.get("label")
    )
    label_prefix = "__logisim_mcp_"
    while any(label.startswith(label_prefix) for label in reserved):
        label_prefix += "_"

    def literals_of(pattern: list[str]) -> list[tuple[str, bool]]:
        found: list[tuple[str, bool]] = []
        for in_name, val in zip(inputs, pattern):
            token = val.strip().lower()
            if token in ("0", "l"):
                found.append((in_name, True))
            elif token in ("1", "h"):
                found.append((in_name, False))
        return found

    negated = {
        name
        for row in rows
        for name, inverted in (
            literals_of(row[: len(inputs)])
        )
        if inverted
    }
    pin_y = {name: 80 + 120 * index for index, name in enumerate(inputs)}
    input_pins = {
        name: _add_input_pin(project, c, name, (80, pin_y[name]))
        for name in inputs
    }
    inverted_out: dict[str, Point] = {}
    for name in inputs:
        if name not in negated:
            continue
        not_loc = (280, pin_y[name])
        not_gate = _place(project, c, gate_spec("NOT"), not_loc)
        not_in = (not_loc[0] + gate_spec("NOT").input_port(0).dx, not_loc[1])
        _route(project, c, input_pins[name].loc, not_in)
        inverted_out[name] = not_gate.loc

    def signal_source(name: str, inverted: bool) -> Point:
        if inverted:
            return inverted_out[name]
        return input_pins[name].loc

    def tie(value: str, y: int, label: str) -> None:
        const = _place(project, c, resolve("Constant"), (720, y), {"value": value})
        pin = _add_output_pin(project, c, label, (860, y))
        _route(project, c, const.loc, pin.loc)

    cursor_y = 80
    for out_idx, out_name in enumerate(outputs):
        block_top = cursor_y
        minterms = [
            row[: len(inputs)]
            for row in rows
            if row[len(inputs) + out_idx].strip() in ("1", "H", "h")
        ]
        if not minterms:
            tie("0x0", cursor_y, out_name)
            cursor_y += 120
            continue
        if any(not literals_of(pattern) for pattern in minterms):
            tie("0x1", cursor_y, out_name)
            cursor_y += 120
            continue

        terms: list[Point] = []
        for m_idx, pattern in enumerate(minterms):
            literals = literals_of(pattern)
            row_y = block_top + m_idx * 160
            if len(literals) == 1:
                name, inverted = literals[0]
                terms.append(signal_source(name, inverted))
                continue
            and_loc = (640, row_y)
            spec = gate_spec("AND", inputs=len(literals))
            _place(project, c, spec, and_loc, {"inputs": str(len(literals))})
            for slot, (name, inverted) in enumerate(literals):
                port = spec.input_port(slot)
                label = f"not_{name}" if inverted else f"in_{name}"
                _tap(
                    project,
                    c,
                    f"{label_prefix}{label}",
                    signal_source(name, inverted),
                    (and_loc[0] + port.dx, and_loc[1] + port.dy),
                )
            terms.append(and_loc)
        combined, out_loc = _or_tree(
            project, c, terms, str(out_idx), 980, block_top, label_prefix
        )
        out_pin = _add_output_pin(project, c, out_name, out_loc)
        _tap(
            project,
            c,
            f"{label_prefix}out_{out_idx}",
            combined,
            out_pin.loc,
        )
        cursor_y += max(len(minterms), 1) * 160 + 80

    save(project, p)
    return {
        "circuit": circuit_name,
        "inputs": inputs,
        "outputs": outputs,
        "rows": len(rows),
        **_summary(c),
    }
