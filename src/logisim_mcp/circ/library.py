"""Component catalogue: maps a friendly type name to the Logisim
``<comp lib="…" name="…">`` identity plus port geometry and default
attributes.

Coordinates use Logisim's *output-anchored* convention: ``loc`` is the
component's output pin location (for gates), or the pin tip (for ``Pin``).
Port offsets are expressed relative to ``loc`` when the component faces
**east** (the Logisim default). ``with_facing`` rotates those offsets
the same way ``AbstractGate.getInputOffset`` does.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .model import Circuit, Component, Project

Point = tuple[int, int]


# --- Libraries referenced by generated circuits (Logisim Evolution 5.0.0) ----
# The ``name`` attribute is a file-local id; Logisim resolves ``desc``.
# Order matches a file saved by the 5.0.0 GUI (not Builtin.java's in-memory
# order, which also includes HDL-IP). Parsers keep whatever ids a file
# already has; these ids are only for projects we create.
STANDARD_LIBS: list[tuple[str, str]] = [
    ("0", "#Wiring"),
    ("1", "#Gates"),
    ("2", "#Plexers"),
    ("3", "#Arithmetic"),
    ("4", "#FPArithmetic"),
    ("5", "#Memory"),
    ("6", "#I/O"),
    ("7", "#TTL"),
    ("8", "#TCL"),
    ("9", "#Base"),
    ("10", "#BFH-Praktika"),
    ("11", "#Input/Output-Extra"),
    ("12", "#Soc"),
]


@dataclass(frozen=True)
class PortSpec:
    """A port on a component, relative to its ``loc`` anchor (east-facing)."""

    label: str
    dx: int
    dy: int
    direction: str  # "in" | "out"


@dataclass(frozen=True)
class ComponentSpec:
    """Catalogue entry describing how to emit a Logisim component."""

    type_key: str
    lib_desc: str
    logisim_name: str
    bbox: tuple[int, int]  # (width, height) in px, east-facing
    # Output anchor offset inside the bbox — usually the right-middle.
    anchor: tuple[int, int]
    default_attrs: dict[str, str] = field(default_factory=dict)
    # Ports relative to ``loc`` (the anchor point).
    ports: tuple[PortSpec, ...] = ()

    def output_port(self) -> PortSpec:
        for p in self.ports:
            if p.direction == "out":
                return p
        raise LookupError(f"{self.type_key} has no output port")

    def input_port(self, index: int) -> PortSpec:
        ins = [p for p in self.ports if p.direction == "in"]
        if not ins:
            raise LookupError(f"{self.type_key} has no input ports")
        if index < 0 or index >= len(ins):
            raise IndexError(
                f"{self.type_key}: input port {index} out of range "
                f"(have {len(ins)})"
            )
        return ins[index]

    def port_by_label(self, label: str) -> PortSpec:
        for p in self.ports:
            if p.label == label:
                return p
        raise LookupError(f"{self.type_key} has no port {label!r}")


# --- Gate port geometry -----------------------------------------------------
# Mirrors Logisim's ``AbstractGate.getInputOffset`` (5.0.0).
# axis_length = size + bonusWidth + (negate_output ? 10 : 0).
#   bonusWidth: 0 for AND/OR/NAND/NOR, 10 for XOR/XNOR.
#   negate_output: true for NAND/NOR/XNOR.
# For size == 50 (Logisim "medium", default) and inputs <= 3:
#   inputs == 2:  ports at dy = -20, +20.
#   inputs == 3:  ports at dy = -20, 0, +20.
# The wider spacing (-30, 0, +30) starts at size >= 60.
# For inputs == 4 and size < 60: ports at dy = -20, -10, +10, +20.

_GATE_GEOMETRY = {
    "AND":  {"bonus": 0,  "negate_out": False},
    "OR":   {"bonus": 0,  "negate_out": False},
    "NAND": {"bonus": 0,  "negate_out": True},
    "NOR":  {"bonus": 0,  "negate_out": True},
    "XOR":  {"bonus": 10, "negate_out": False},
    "XNOR": {"bonus": 10, "negate_out": True},
    "NOT":  {"bonus": 0,  "negate_out": True,  "axis_override": 30, "single_input": True},
    "BUF":  {"bonus": 0,  "negate_out": False, "axis_override": 20, "single_input": True},
}


def _input_offsets(inputs: int, size: int = 50) -> list[int]:
    """Per-input ``dy`` offsets from the gate anchor (east-facing)."""
    if inputs == 1:
        return [0]
    if inputs <= 3:
        if size < 40:
            skip_start, skip_dist, skip_lower_even = -5, 10, 10
        elif size < 60 or inputs <= 2:
            skip_start, skip_dist, skip_lower_even = -10, 20, 20
        else:
            skip_start, skip_dist, skip_lower_even = -15, 30, 30
    elif inputs == 4 and size >= 60:
        skip_start, skip_dist, skip_lower_even = -5, 20, 0
    else:
        skip_start, skip_dist, skip_lower_even = -5, 10, 10
    out: list[int] = []
    for i in range(inputs):
        if inputs & 1:
            dy = skip_start * (inputs - 1) + skip_dist * i
        else:
            dy = skip_start * inputs + skip_dist * i
            if i >= inputs // 2:
                dy += skip_lower_even
            if inputs == 4 and size >= 60:
                dy -= 10
        out.append(dy)
    return out


def _gate_axis_length(type_key: str, size: int) -> int:
    g = _GATE_GEOMETRY[type_key]
    if "axis_override" in g:
        return g["axis_override"]
    return size + g["bonus"] + (10 if g["negate_out"] else 0)


def _gate_ports(type_key: str, inputs: int, size: int = 50) -> tuple[PortSpec, ...]:
    if inputs < 1:
        raise ValueError("gate must have >=1 inputs")
    if _GATE_GEOMETRY[type_key].get("single_input"):
        inputs = 1
    # NOT's ``size`` option is the input-to-output distance itself
    # (20 narrow, 30 wide). Other gates add the bonus / bubble.
    axis = size if type_key == "NOT" else _gate_axis_length(type_key, size)
    offsets = _input_offsets(inputs, size)
    ports = [
        PortSpec(label=f"in{i}", dx=-axis, dy=offsets[i], direction="in")
        for i in range(inputs)
    ]
    ports.append(PortSpec(label="out", dx=0, dy=0, direction="out"))
    return tuple(ports)


def _gate_spec(
    type_key: str,
    logisim_name: str,
    inputs: int = 2,
    size: int | None = None,
) -> ComponentSpec:
    # AND/OR/XOR use an integer ``size`` (medium is 50). NOT's ``size`` is
    # an option, 20 or 30; "50" is rejected and the gate is dropped on load.
    # Buffer has no size attribute; its input sits 20 px west of the output.
    attrs: dict[str, str] = {}
    if type_key == "NOT":
        chosen = 30 if size is None else size
        attrs["size"] = str(chosen)
    elif _GATE_GEOMETRY[type_key].get("single_input"):
        chosen = 20
    else:
        chosen = 50 if size is None else size
        attrs["size"] = str(chosen)
        attrs["inputs"] = str(inputs)
    ports = _gate_ports(type_key, inputs, size=chosen)
    axis = abs(ports[0].dx)
    return ComponentSpec(
        type_key=type_key,
        lib_desc="#Gates",
        logisim_name=logisim_name,
        bbox=(axis, 50),
        anchor=(axis, 25),
        default_attrs=attrs,
        ports=ports,
    )


# --- Pin (Wiring) -----------------------------------------------------------
# Pin's ``loc`` is the tip where wires connect.
# East-facing input  Pin: tip is the output of the component (data flows out).
# West-facing output Pin: tip is the input.
def _pin_spec(is_output: bool) -> ComponentSpec:
    if is_output:
        return ComponentSpec(
            type_key="OutputPin",
            lib_desc="#Wiring",
            logisim_name="Pin",
            bbox=(20, 20),
            anchor=(0, 0),
            default_attrs={
                "facing": "west",
                "output": "true",
                "type": "output",
            },
            ports=(PortSpec(label="tip", dx=0, dy=0, direction="in"),),
        )
    return ComponentSpec(
        type_key="InputPin",
        lib_desc="#Wiring",
        logisim_name="Pin",
        bbox=(20, 20),
        anchor=(0, 0),
        default_attrs={
            "facing": "east",
        },
        ports=(PortSpec(label="tip", dx=0, dy=0, direction="out"),),
    )


# --- Tunnel (named wireless node) -------------------------------------------
def _tunnel_spec() -> ComponentSpec:
    return ComponentSpec(
        type_key="Tunnel",
        lib_desc="#Wiring",
        logisim_name="Tunnel",
        bbox=(40, 20),
        anchor=(0, 0),
        default_attrs={"facing": "west"},
        ports=(PortSpec(label="tip", dx=0, dy=0, direction="in"),),
    )


# --- Constant ---------------------------------------------------------------
def _constant_spec() -> ComponentSpec:
    return ComponentSpec(
        type_key="Constant",
        lib_desc="#Wiring",
        logisim_name="Constant",
        bbox=(20, 20),
        anchor=(0, 0),
        default_attrs={"facing": "east", "width": "1", "value": "0x1"},
        ports=(PortSpec(label="tip", dx=0, dy=0, direction="out"),),
    )


# --- Clock ------------------------------------------------------------------
def _clock_spec() -> ComponentSpec:
    return ComponentSpec(
        type_key="Clock",
        lib_desc="#Wiring",
        logisim_name="Clock",
        bbox=(30, 30),
        anchor=(30, 15),
        default_attrs={"facing": "east"},
        ports=(PortSpec(label="out", dx=0, dy=0, direction="out"),),
    )


# --- Plexers ----------------------------------------------------------------
# Port math is Multiplexer.updatePorts / Demultiplexer.updatePorts /
# Decoder.updatePorts in logisim-evolution 5.0.0. ``loc`` is the output
# for a mux and the data input for a demux. North and south do not match
# a generic gate rotation, and a mux's narrow size is 20 (30 wide when
# there are two data inputs, 40 otherwise).


def _facing_translate(x: int, y: int, facing: str, dist: int) -> tuple[int, int]:
    """``Location.translate(facing, dist)`` with a zero sideways offset."""
    name = (facing or "east").lower()
    if name == "east":
        return x + dist, y
    if name == "west":
        return x - dist, y
    if name == "north":
        return x, y - dist
    if name == "south":
        return x, y + dist
    raise ValueError(f"unknown facing {facing!r}")


def _port_bbox(ports: list[PortSpec], fallback: tuple[tuple[int, int], tuple[int, int]]) -> tuple[tuple[int, int], tuple[int, int]]:
    if not ports:
        return fallback
    xs = [0] + [port.dx for port in ports]
    ys = [0] + [port.dy for port in ports]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    width = max(max_x - min_x, 10)
    height = max(max_y - min_y, 10)
    return (width, height), (-min_x, -min_y)


def _mux_ports(
    select_bits: int,
    facing: str = "east",
    narrow: bool = False,
    selloc: str = "bl",
    enable: bool = False,
) -> list[PortSpec]:
    inputs = 1 << select_bits
    direction = (facing or "east").lower()
    bottom_left = selloc != "tr"
    select_sign = 1 if bottom_left else -1
    wide = not narrow
    if inputs == 2:
        depth = 20 if narrow else 30
        select_inset = 10 if narrow else 20
        if direction == "west":
            data = [(depth, -10), (depth, 10)]
            select = (select_inset, select_sign * 20)
        elif direction == "north":
            data = [(-10, depth), (10, depth)]
            select = (select_sign * -20, select_inset)
        elif direction == "south":
            data = [(-10, -depth), (10, -depth)]
            select = (select_sign * -20, -select_inset)
        else:
            data = [(-depth, -10), (-depth, 10)]
            select = (-select_inset, select_sign * 20)
    else:
        depth = 20 if narrow else 40
        select_inset = 10 if narrow else 20
        dx = -(inputs // 2) * 10
        ddx = 10
        dy = -(inputs // 2) * 10
        ddy = 10
        if direction == "west":
            dx = depth
            ddx = 0
            select = (select_inset, select_sign * (dy + 10 * inputs))
        elif direction == "north":
            dy = depth
            ddy = 0
            select = (select_sign * dx, select_inset)
        elif direction == "south":
            dy = -depth
            ddy = 0
            select = (select_sign * dx, -select_inset)
        else:
            dx = -depth
            ddx = 0
            select = (-select_inset, select_sign * (dy + 10 * inputs))
        data = []
        for _ in range(inputs):
            data.append((dx, dy))
            dx += ddx
            dy += ddy
        vertical = direction not in ("north", "south")
        if not wide and not vertical and bottom_left and inputs > 2:
            select = (select[0] - 10, select[1])
        elif not wide and vertical and not bottom_left and inputs > 2:
            select = (select[0], select[1] - 10)
    ports = [
        PortSpec(label=f"d{i}", dx=x, dy=y, direction="in")
        for i, (x, y) in enumerate(data)
    ]
    ports.append(PortSpec(label="sel", dx=select[0], dy=select[1], direction="in"))
    if enable:
        ex, ey = _facing_translate(select[0], select[1], direction, 10)
        ports.append(PortSpec(label="en", dx=ex, dy=ey, direction="in"))
    ports.append(PortSpec(label="out", dx=0, dy=0, direction="out"))
    return ports


def _demux_ports(
    select_bits: int,
    facing: str = "east",
    selloc: str = "bl",
    enable: bool = False,
) -> list[PortSpec]:
    outputs = 1 << select_bits
    direction = (facing or "east").lower()
    select_sign = 1 if selloc != "tr" else -1
    if outputs == 2:
        if direction == "west":
            data = [(-30, -10), (-30, 10)]
            select = (-20, select_sign * 20)
        elif direction == "north":
            data = [(-10, -30), (10, -30)]
            select = (select_sign * -20, -20)
        elif direction == "south":
            data = [(-10, 30), (10, 30)]
            select = (select_sign * -20, 20)
        else:
            data = [(30, -10), (30, 10)]
            select = (20, select_sign * 20)
    else:
        dx = -(outputs // 2) * 10
        ddx = 10
        dy = dx
        ddy = 10
        if direction == "west":
            dx = -40
            ddx = 0
            select = (-20, select_sign * (dy + 10 * outputs))
        elif direction == "north":
            dy = -40
            ddy = 0
            select = (select_sign * dx, -20)
        elif direction == "south":
            dy = 40
            ddy = 0
            select = (select_sign * dx, 20)
        else:
            dx = 40
            ddx = 0
            select = (20, select_sign * (dy + 10 * outputs))
        data = []
        for _ in range(outputs):
            data.append((dx, dy))
            dx += ddx
            dy += ddy
    ports = [
        PortSpec(label=f"q{i}", dx=x, dy=y, direction="out")
        for i, (x, y) in enumerate(data)
    ]
    ports.append(PortSpec(label="sel", dx=select[0], dy=select[1], direction="in"))
    if enable:
        ex, ey = _facing_translate(select[0], select[1], direction, -10)
        ports.append(PortSpec(label="en", dx=ex, dy=ey, direction="in"))
    ports.append(PortSpec(label="in", dx=0, dy=0, direction="in"))
    return ports


def _decoder_ports(
    select_bits: int,
    facing: str = "east",
    selloc: str = "bl",
    enable: bool = False,
) -> list[PortSpec]:
    outputs = 1 << select_bits
    direction = (facing or "east").lower()
    top_right = selloc == "tr"
    if outputs == 2:
        if direction in ("north", "south"):
            y = -10 if direction == "north" else 10
            data = [(-30, y), (-10, y)] if top_right else [(10, y), (30, y)]
        else:
            x = -10 if direction == "west" else 10
            data = [(x, 10), (x, 30)] if top_right else [(x, -30), (x, -10)]
    else:
        if direction in ("north", "south"):
            dy = -20 if direction == "north" else 20
            ddy = 0
            dx = -10 * outputs if top_right else 0
            ddx = 10
        else:
            dx = -20 if direction == "west" else 20
            ddx = 0
            dy = 0 if top_right else -10 * outputs
            ddy = 10
        data = []
        for _ in range(outputs):
            data.append((dx, dy))
            dx += ddx
            dy += ddy
    ports = [
        PortSpec(label=f"q{i}", dx=x, dy=y, direction="out")
        for i, (x, y) in enumerate(data)
    ]
    ports.append(PortSpec(label="sel", dx=0, dy=0, direction="in"))
    if enable:
        ex, ey = _facing_translate(0, 0, direction, -10)
        ports.append(PortSpec(label="en", dx=ex, dy=ey, direction="in"))
    return ports


def _mux_spec(
    select_bits: int,
    *,
    facing: str = "east",
    narrow: bool = False,
    selloc: str = "bl",
    enable: bool = False,
) -> ComponentSpec:
    ports = _mux_ports(select_bits, facing, narrow, selloc, enable)
    inputs = 1 << select_bits
    default_box = facing == "east" and not narrow and selloc == "bl" and not enable
    if default_box and inputs == 2:
        bbox, anchor = (30, 40), (30, 20)
    elif default_box:
        height = inputs * 10 + 20
        top = -(inputs // 2) * 10 - 10
        bbox, anchor = (40, height), (40, -top)
    else:
        bbox, anchor = _port_bbox(ports, ((40, 40), (20, 20)))
    attrs: dict[str, str] = {"facing": facing, "select": str(select_bits)}
    if narrow:
        attrs["size"] = "20"
    if selloc != "bl":
        attrs["selloc"] = selloc
    if enable:
        attrs["enable"] = "true"
    return ComponentSpec(
        type_key=f"Multiplexer_{select_bits}",
        lib_desc="#Plexers",
        logisim_name="Multiplexer",
        bbox=bbox,
        anchor=anchor,
        default_attrs=attrs,
        ports=tuple(ports),
    )


def _demux_spec(
    select_bits: int,
    *,
    facing: str = "east",
    selloc: str = "bl",
    enable: bool = False,
) -> ComponentSpec:
    ports = _demux_ports(select_bits, facing, selloc, enable)
    outputs = 1 << select_bits
    default_box = facing == "east" and selloc == "bl" and not enable
    if default_box and outputs == 2:
        bbox, anchor = (30, 50), (0, 25)
    elif default_box:
        height = outputs * 10 + 20
        top = -(outputs // 2) * 10 - 10
        bbox, anchor = (40, height), (0, -top)
    else:
        bbox, anchor = _port_bbox(ports, ((40, 40), (0, 20)))
    attrs: dict[str, str] = {"facing": facing, "select": str(select_bits)}
    if selloc != "bl":
        attrs["selloc"] = selloc
    if enable:
        attrs["enable"] = "true"
    return ComponentSpec(
        type_key=f"Demultiplexer_{select_bits}",
        lib_desc="#Plexers",
        logisim_name="Demultiplexer",
        bbox=bbox,
        anchor=anchor,
        default_attrs=attrs,
        ports=tuple(ports),
    )


def _decoder_spec(
    select_bits: int,
    *,
    facing: str = "east",
    selloc: str = "bl",
    enable: bool = False,
) -> ComponentSpec:
    # The 5.0 factory default is enable=true. Builders turn it off so the
    # only pins are select and the outputs. A file that omits the attribute
    # still has the enable pin; spec_for_component passes enable=True then.
    ports = _decoder_ports(select_bits, facing, selloc, enable)
    outputs = 1 << select_bits
    default_box = facing == "east" and selloc == "bl" and not enable
    if default_box and outputs == 2:
        bbox, anchor = (30, 50), (20, 45)
    elif default_box:
        height = outputs * 10 + 20
        top = -(outputs * 10 + 10)
        bbox, anchor = (40, height), (20, -top)
    else:
        bbox, anchor = _port_bbox(ports, ((40, 40), (20, 20)))
    attrs: dict[str, str] = {
        "facing": facing,
        "select": str(select_bits),
        "enable": "true" if enable else "false",
    }
    if selloc != "bl":
        attrs["selloc"] = selloc
    return ComponentSpec(
        type_key=f"Decoder_{select_bits}",
        lib_desc="#Plexers",
        logisim_name="Decoder",
        bbox=bbox,
        anchor=anchor,
        default_attrs=attrs,
        ports=tuple(ports),
    )


# --- Arithmetic -------------------------------------------------------------
def _adder_spec(bits: int) -> ComponentSpec:
    # Decompiled from Logisim's Adder.class: A and B inputs at dy=±10,
    # cin at (-20, -20) (top), cout at (-20, +20) (bottom), sum at output.
    return ComponentSpec(
        type_key=f"Adder_{bits}",
        lib_desc="#Arithmetic",
        logisim_name="Adder",
        bbox=(40, 40),
        anchor=(40, 20),
        default_attrs={"width": str(bits)},
        ports=(
            PortSpec(label="a", dx=-40, dy=-10, direction="in"),
            PortSpec(label="b", dx=-40, dy=10, direction="in"),
            PortSpec(label="cin", dx=-20, dy=-20, direction="in"),
            PortSpec(label="sum", dx=0, dy=0, direction="out"),
            PortSpec(label="cout", dx=-20, dy=20, direction="out"),
        ),
    )


def _comparator_spec(bits: int) -> ComponentSpec:
    return ComponentSpec(
        type_key=f"Comparator_{bits}",
        lib_desc="#Arithmetic",
        logisim_name="Comparator",
        bbox=(40, 40),
        anchor=(40, 20),
        default_attrs={"width": str(bits)},
        ports=(
            PortSpec(label="a", dx=-40, dy=-10, direction="in"),
            PortSpec(label="b", dx=-40, dy=10, direction="in"),
            PortSpec(label="gt", dx=0, dy=-10, direction="out"),
            PortSpec(label="eq", dx=0, dy=0, direction="out"),
            PortSpec(label="lt", dx=0, dy=10, direction="out"),
        ),
    )


# --- Memory -----------------------------------------------------------------
# Register and Counter use Logisim's evolution appearance.
# Register.updatePorts and Counter.configurePorts in 5.0.0:
#   Register: bounds (0,0)..(60,90); ports
#     Q@(60,30), D@(0,30), clk@(0,70), reset@(30,90), enable@(0,50).
#   Counter: bounds (0,0)..(sym+40, height); ports
#     Q@(sym+40, q_y), D@(0, q_y), clk@(0,80), clr@(0,20), ld@(0,30),
#     ud@(0,50), en@(0,70), carry@(sym+40, 50);
#     q_y = 120 if width==1 else 110.
# Wide counters (width > 8) pack data rows, so the body is shorter than
# one row per bit. Port Y coordinates are unchanged.
def _trunc_div(n: int, d: int) -> int:
    """Integer division that truncates toward zero, matching Java."""
    return int(n / d)


def _counter_symbol_width(width: int) -> int:
    # Counter.getSymbolWidth: 150 + ((width - 8) / 5) * 10
    return 150 + _trunc_div(width - 8, 5) * 10


def _counter_height(width: int) -> int:
    # CONTROL_HEIGHT 110 + 20 * grouped data rows.
    if width <= 8:
        bits_per_row = 1
    elif width <= 32:
        bits_per_row = 4
    else:
        bits_per_row = 8
    rows = (width + bits_per_row - 1) // bits_per_row
    return 110 + 20 * rows


def _register_spec(bits: int) -> ComponentSpec:
    return ComponentSpec(
        type_key=f"Register_{bits}",
        lib_desc="#Memory",
        logisim_name="Register",
        bbox=(60, 90),
        anchor=(0, 0),
        default_attrs={
            "width": str(bits),
            "trigger": "rising",
            "appearance": "logisim_evolution",
        },
        ports=(
            PortSpec(label="Q", dx=60, dy=30, direction="out"),
            PortSpec(label="D", dx=0, dy=30, direction="in"),
            PortSpec(label="clk", dx=0, dy=70, direction="in"),
            PortSpec(label="rst", dx=30, dy=90, direction="in"),
            PortSpec(label="en", dx=0, dy=50, direction="in"),
        ),
    )


def _counter_spec(bits: int) -> ComponentSpec:
    sym = _counter_symbol_width(bits)
    q_y = 120 if bits == 1 else 110
    height = _counter_height(bits)
    return ComponentSpec(
        type_key=f"Counter_{bits}",
        lib_desc="#Memory",
        logisim_name="Counter",
        bbox=(sym + 40, height),
        anchor=(0, 0),
        default_attrs={
            "width": str(bits),
            "trigger": "rising",
            "appearance": "logisim_evolution",
        },
        ports=(
            PortSpec(label="Q", dx=sym + 40, dy=q_y, direction="out"),
            PortSpec(label="D", dx=0, dy=q_y, direction="in"),
            PortSpec(label="clk", dx=0, dy=80, direction="in"),
            PortSpec(label="clr", dx=0, dy=20, direction="in"),
            PortSpec(label="ld", dx=0, dy=30, direction="in"),
            PortSpec(label="ud", dx=0, dy=50, direction="in"),
            PortSpec(label="en", dx=0, dy=70, direction="in"),
            PortSpec(label="carry", dx=sym + 40, dy=50, direction="out"),
        ),
    )


# --- Catalogue --------------------------------------------------------------

GATE_TYPES = {
    "AND": "AND Gate",
    "OR": "OR Gate",
    "NAND": "NAND Gate",
    "NOR": "NOR Gate",
    "XOR": "XOR Gate",
    "XNOR": "XNOR Gate",
    "NOT": "NOT Gate",
    "BUF": "Buffer",
}


def gate_spec(gate: str, inputs: int = 2, size: int | None = None) -> ComponentSpec:
    name = gate.upper()
    if name not in GATE_TYPES:
        raise KeyError(f"unknown gate type {gate!r}; supported: {sorted(GATE_TYPES)}")
    logisim_name = GATE_TYPES[name]
    if name in ("NOT", "BUF"):
        inputs = 1
    return _gate_spec(name, logisim_name, inputs, size=size)


def is_output_pin(attrs: dict[str, str]) -> bool:
    """True for a Pin that drives out of the circuit.

    Logisim 5.0.0 writes ``<a name="type" val="output"/>``. Older files,
    and the loader's compatibility repair, use ``output="true"``.
    """
    return attrs.get("output", "false") == "true" or attrs.get("type") == "output"


def rotate_offset(dx: int, dy: int, facing: str) -> tuple[int, int]:
    """Rotate an east-facing ``(dx, dy)`` the way Logisim rotates a gate.

    East ``(-axis, dy)`` becomes west ``(axis, dy)``, north ``(dy, axis)``,
    south ``(dy, -axis)``.
    """
    name = (facing or "east").lower()
    if name == "east":
        return dx, dy
    if name == "west":
        return -dx, dy
    if name == "north":
        return dy, -dx
    if name == "south":
        return dy, dx
    raise ValueError(f"unknown facing {facing!r}")


def with_facing(spec: ComponentSpec, facing: str) -> ComponentSpec:
    """Return ``spec`` with port offsets rotated to ``facing``."""
    if not facing or facing.lower() == "east":
        return spec
    ports = tuple(
        PortSpec(
            label=port.label,
            dx=rotate_offset(port.dx, port.dy, facing)[0],
            dy=rotate_offset(port.dx, port.dy, facing)[1],
            direction=port.direction,
        )
        for port in spec.ports
    )
    return ComponentSpec(
        type_key=spec.type_key,
        lib_desc=spec.lib_desc,
        logisim_name=spec.logisim_name,
        bbox=spec.bbox,
        anchor=spec.anchor,
        default_attrs=spec.default_attrs,
        ports=ports,
    )


def input_pin_spec() -> ComponentSpec:
    return _pin_spec(is_output=False)


def output_pin_spec() -> ComponentSpec:
    return _pin_spec(is_output=True)


def tunnel_spec() -> ComponentSpec:
    return _tunnel_spec()


def constant_spec() -> ComponentSpec:
    return _constant_spec()


def clock_spec() -> ComponentSpec:
    return _clock_spec()


def mux_spec(select_bits: int, **kwargs: Any) -> ComponentSpec:
    return _mux_spec(select_bits, **kwargs)


def demux_spec(select_bits: int, **kwargs: Any) -> ComponentSpec:
    return _demux_spec(select_bits, **kwargs)


def decoder_spec(select_bits: int, **kwargs: Any) -> ComponentSpec:
    return _decoder_spec(select_bits, **kwargs)


def adder_spec(bits: int = 1) -> ComponentSpec:
    return _adder_spec(bits)


def comparator_spec(bits: int = 1) -> ComponentSpec:
    return _comparator_spec(bits)


def _classic_register_spec(bits: int) -> ComponentSpec:
    # Bounds.create(-30, -20, 30, 40). Ports from Register.updatePorts.
    return ComponentSpec(
        type_key=f"Register_{bits}",
        lib_desc="#Memory",
        logisim_name="Register",
        bbox=(30, 40),
        anchor=(30, 20),
        default_attrs={
            "width": str(bits),
            "trigger": "rising",
            "appearance": "classic",
        },
        ports=(
            PortSpec(label="Q", dx=0, dy=0, direction="out"),
            PortSpec(label="D", dx=-30, dy=0, direction="in"),
            PortSpec(label="clk", dx=-20, dy=20, direction="in"),
            PortSpec(label="rst", dx=-10, dy=20, direction="in"),
            PortSpec(label="en", dx=-30, dy=10, direction="in"),
        ),
    )


def _classic_counter_spec(bits: int) -> ComponentSpec:
    # Same classic body as Register. Ports from Counter.configurePorts.
    return ComponentSpec(
        type_key=f"Counter_{bits}",
        lib_desc="#Memory",
        logisim_name="Counter",
        bbox=(30, 40),
        anchor=(30, 20),
        default_attrs={
            "width": str(bits),
            "trigger": "rising",
            "appearance": "classic",
        },
        ports=(
            PortSpec(label="Q", dx=0, dy=0, direction="out"),
            PortSpec(label="D", dx=-30, dy=0, direction="in"),
            PortSpec(label="clk", dx=-20, dy=20, direction="in"),
            PortSpec(label="clr", dx=-10, dy=20, direction="in"),
            PortSpec(label="ld", dx=-30, dy=-10, direction="in"),
            PortSpec(label="ud", dx=-20, dy=-20, direction="in"),
            PortSpec(label="en", dx=-30, dy=10, direction="in"),
            PortSpec(label="carry", dx=0, dy=10, direction="out"),
        ),
    )


def register_spec(bits: int = 1, classic: bool = False) -> ComponentSpec:
    if classic:
        return _classic_register_spec(bits)
    return _register_spec(bits)


def counter_spec(bits: int = 1, classic: bool = False) -> ComponentSpec:
    if classic:
        return _classic_counter_spec(bits)
    return _counter_spec(bits)


# Discrete flip-flops, evolution appearance.
# Bounds.create(-10, 0, 60, 60) in AbstractFlipFlop (5.0.0): the anchor
# sits 10 px in from the left edge. Async preset is S at the top, clear
# is R at the bottom. An S-R flip-flop's data pins are also named S and R,
# so those async pins are labeled PRE and CLR to keep port names unique.
_FLIP_FLOPS: dict[str, tuple[str, ...]] = {
    "D Flip-Flop": ("D",),
    "T Flip-Flop": ("T",),
    "J-K Flip-Flop": ("J", "K"),
    "S-R Flip-Flop": ("S", "R"),
}


def _flip_flop_ports(
    data: tuple[str, ...], classic: bool, preset: str, clear: str
) -> tuple[PortSpec, ...]:
    if classic:
        if len(data) == 1:
            ports = [
                PortSpec(data[0], -40, 20, "in"),
                PortSpec("CLK", -40, 0, "in"),
            ]
        else:
            ports = [
                PortSpec(data[0], -40, 0, "in"),
                PortSpec(data[1], -40, 20, "in"),
                PortSpec("CLK", -40, 10, "in"),
            ]
        ports.extend(
            [
                PortSpec("Q", 0, 0, "out"),
                PortSpec("Q_bar", 0, 20, "out"),
                PortSpec(clear, -10, 30, "in"),
                PortSpec(preset, -30, 30, "in"),
            ]
        )
    else:
        if len(data) == 1:
            ports = [
                PortSpec(data[0], -10, 10, "in"),
                PortSpec("CLK", -10, 50, "in"),
            ]
        else:
            ports = [
                PortSpec(data[0], -10, 10, "in"),
                PortSpec(data[1], -10, 30, "in"),
                PortSpec("CLK", -10, 50, "in"),
            ]
        ports.extend(
            [
                PortSpec("Q", 50, 10, "out"),
                PortSpec("Q_bar", 50, 50, "out"),
                PortSpec(clear, 20, 60, "in"),
                PortSpec(preset, 20, 0, "in"),
            ]
        )
    return tuple(ports)


def flip_flop_spec(name: str, classic: bool = False) -> ComponentSpec:
    if name not in _FLIP_FLOPS:
        raise KeyError(f"unknown flip-flop {name!r}")
    if classic:
        bbox, anchor = (40, 40), (40, 10)
    else:
        bbox, anchor = (60, 60), (10, 0)
    return ComponentSpec(
        type_key=name,
        lib_desc="#Memory",
        logisim_name=name,
        bbox=bbox,
        anchor=anchor,
        default_attrs={
            "appearance": "classic" if classic else "logisim_evolution",
            "trigger": "rising",
        },
        ports=_flip_flop_ports(
            _FLIP_FLOPS[name],
            classic,
            preset="PRE" if name == "S-R Flip-Flop" else "S",
            clear="CLR" if name == "S-R Flip-Flop" else "R",
        ),
    )


def led_spec() -> ComponentSpec:
    """LED input sits on ``loc``. East-facing body is 20×20 to the left."""
    return ComponentSpec(
        type_key="LED",
        lib_desc="#I/O",
        logisim_name="LED",
        bbox=(20, 20),
        anchor=(20, 10),
        default_attrs={"facing": "east"},
        ports=(PortSpec(label="in", dx=0, dy=0, direction="in"),),
    )


# A flat registry used by builder_tools to resolve `add_component(type=…)`
# without ad-hoc switches.
SPEC_FACTORIES: dict[str, callable] = {
    "AND": lambda **kw: gate_spec("AND", inputs=kw.get("inputs", 2), size=kw.get("size")),
    "OR": lambda **kw: gate_spec("OR", inputs=kw.get("inputs", 2), size=kw.get("size")),
    "NAND": lambda **kw: gate_spec("NAND", inputs=kw.get("inputs", 2), size=kw.get("size")),
    "NOR": lambda **kw: gate_spec("NOR", inputs=kw.get("inputs", 2), size=kw.get("size")),
    "XOR": lambda **kw: gate_spec("XOR", inputs=kw.get("inputs", 2), size=kw.get("size")),
    "XNOR": lambda **kw: gate_spec("XNOR", inputs=kw.get("inputs", 2), size=kw.get("size")),
    "NOT": lambda **kw: gate_spec("NOT", size=kw.get("size")),
    "BUF": lambda **kw: gate_spec("BUF"),
    "InputPin": lambda **kw: input_pin_spec(),
    "OutputPin": lambda **kw: output_pin_spec(),
    "Tunnel": lambda **kw: tunnel_spec(),
    "Constant": lambda **kw: constant_spec(),
    "Clock": lambda **kw: clock_spec(),
    "Multiplexer": lambda **kw: mux_spec(kw.get("select_bits", 1)),
    "Demultiplexer": lambda **kw: demux_spec(kw.get("select_bits", 1)),
    "Decoder": lambda **kw: decoder_spec(kw.get("select_bits", 1)),
    "Adder": lambda **kw: adder_spec(kw.get("bits", 1)),
    "Comparator": lambda **kw: comparator_spec(kw.get("bits", 1)),
    "Register": lambda **kw: register_spec(kw.get("bits", 1)),
    "Counter": lambda **kw: counter_spec(kw.get("bits", 1)),
    "D Flip-Flop": lambda **kw: flip_flop_spec("D Flip-Flop", classic=kw.get("classic", False)),
    "J-K Flip-Flop": lambda **kw: flip_flop_spec("J-K Flip-Flop", classic=kw.get("classic", False)),
    "T Flip-Flop": lambda **kw: flip_flop_spec("T Flip-Flop", classic=kw.get("classic", False)),
    "S-R Flip-Flop": lambda **kw: flip_flop_spec("S-R Flip-Flop", classic=kw.get("classic", False)),
    "LED": lambda **kw: led_spec(),
}


def resolve(type_key: str, **kw) -> ComponentSpec:
    if type_key not in SPEC_FACTORIES:
        raise KeyError(
            f"unknown component type {type_key!r}; "
            f"supported: {sorted(SPEC_FACTORIES)}"
        )
    return SPEC_FACTORIES[type_key](**kw)


def _faced(spec: ComponentSpec, attrs: dict[str, str]) -> ComponentSpec:
    facing = attrs.get("facing", "east")
    if facing == "east":
        return spec
    return with_facing(spec, facing)


def spec_for_component(project: Project, comp: Component) -> ComponentSpec | None:
    """Catalogue entry for a component already in a file, or ``None``.

    Honors gate ``size`` and ``facing``, plexer ``size`` / ``selloc`` /
    ``enable`` / facing, and classic Register and Counter appearance.
    Output pins are recognized from either ``output="true"`` or Logisim
    5.0.0's ``type="output"``. A decoder with no ``enable`` attribute
    still has the enable pin: that is the 5.0 factory default.
    """
    try:
        desc = project.lib_desc_for_id(comp.lib)
    except KeyError:
        return None
    attrs = comp.attrs
    name = comp.name
    if desc == "#Gates":
        key = next((k for k, label in GATE_TYPES.items() if label == name), None)
        if key is None:
            return None
        default_inputs = "1" if key in ("NOT", "BUF") else "2"
        inputs = int(attrs.get("inputs", default_inputs))
        raw_size = attrs.get("size")
        size = int(raw_size) if raw_size and raw_size.isdigit() else None
        return _faced(gate_spec(key, inputs=inputs, size=size), attrs)
    if desc == "#Wiring":
        if name == "Pin":
            return _faced(resolve("OutputPin" if is_output_pin(attrs) else "InputPin"), attrs)
        if name == "Tunnel":
            return _faced(resolve("Tunnel"), attrs)
        if name == "Clock":
            return _faced(resolve("Clock"), attrs)
        if name == "Constant":
            return _faced(resolve("Constant"), attrs)
        return None
    if desc == "#Plexers" and name in ("Multiplexer", "Demultiplexer", "Decoder"):
        sel = int(attrs.get("select", "1"))
        facing = attrs.get("facing", "east")
        selloc = attrs.get("selloc", "bl")
        if name == "Decoder":
            enable = attrs.get("enable", "true") == "true"
            return decoder_spec(sel, facing=facing, selloc=selloc, enable=enable)
        enable = attrs.get("enable", "false") == "true"
        if name == "Multiplexer":
            return mux_spec(
                sel,
                facing=facing,
                selloc=selloc,
                enable=enable,
                narrow=attrs.get("size") == "20",
            )
        return demux_spec(sel, facing=facing, selloc=selloc, enable=enable)
    if desc == "#Arithmetic":
        if name == "Adder":
            return resolve("Adder", bits=int(attrs.get("width", "1")))
        if name == "Comparator":
            return resolve("Comparator", bits=int(attrs.get("width", "1")))
        return None
    if desc == "#Memory":
        classic = attrs.get("appearance") == "classic"
        if name == "Register":
            return register_spec(int(attrs.get("width", "1")), classic=classic)
        if name == "Counter":
            return counter_spec(int(attrs.get("width", "1")), classic=classic)
        if name in _FLIP_FLOPS:
            return flip_flop_spec(name, classic=attrs.get("appearance") == "classic")
        return None
    if desc == "#I/O" and name == "LED":
        return _faced(led_spec(), attrs)
    return None


def component_port_points(project: Project, comp: Component) -> list[Point]:
    spec = spec_for_component(project, comp)
    if spec is None:
        return []
    return [(comp.loc[0] + port.dx, comp.loc[1] + port.dy) for port in spec.ports]


def circuit_port_points(project: Project, circuit: Circuit) -> list[Point]:
    points: list[Point] = []
    for comp in circuit.components:
        points.extend(component_port_points(project, comp))
    return points
