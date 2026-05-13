"""Component catalogue: maps a friendly type name to the Logisim
``<comp lib="…" name="…">`` identity plus port geometry and default
attributes.

Coordinates use Logisim's *output-anchored* convention: ``loc`` is the
component's output pin location (for gates), or the pin tip (for ``Pin``).
Port offsets are expressed relative to ``loc`` when the component faces
**east** (the Logisim default). Rotating via the ``facing`` attribute is
not modelled here — high-level tools always lay things out east-facing.
"""

from __future__ import annotations

from dataclasses import dataclass, field

Point = tuple[int, int]


# --- Standard library order used by Logisim Evolution 4.0.0 -----------------
# Index in this list == the ``name`` attribute on each ``<lib>`` element.
STANDARD_LIBS: list[tuple[str, str]] = [
    ("0", "#Wiring"),
    ("1", "#Gates"),
    ("2", "#Plexers"),
    ("3", "#Arithmetic"),
    ("4", "#Memory"),
    ("5", "#I/O"),
    ("6", "#Base"),
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
# Mirrors Logisim's ``AbstractGate.getInputOffset`` (decompiled from the
# 4.0.0 JAR). axis_length = size + bonusWidth + (negate_output ? 10 : 0).
#   bonusWidth: 0 for AND/OR/NAND/NOR, 10 for XOR/XNOR.
#   negate_output: true for NAND/NOR/XNOR.
# For size == 50 (Logisim "medium", default) and inputs <= 3:
#   inputs == 2:  ports at dy = -20, +20.
#   inputs == 3:  ports at dy = -30, 0, +30.
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
        elif size >= 60 or inputs <= 2:
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
    axis = _gate_axis_length(type_key, size)
    offsets = _input_offsets(inputs, size)
    ports = [
        PortSpec(label=f"in{i}", dx=-axis, dy=offsets[i], direction="in")
        for i in range(inputs)
    ]
    ports.append(PortSpec(label="out", dx=0, dy=0, direction="out"))
    return tuple(ports)


def _gate_spec(type_key: str, logisim_name: str, inputs: int = 2) -> ComponentSpec:
    axis = _gate_axis_length(type_key, 50)
    attrs: dict[str, str] = {"size": "50"}
    if not _GATE_GEOMETRY[type_key].get("single_input"):
        attrs["inputs"] = str(inputs)
    return ComponentSpec(
        type_key=type_key,
        lib_desc="#Gates",
        logisim_name=logisim_name,
        bbox=(axis, 50),
        anchor=(axis, 25),
        default_attrs=attrs,
        ports=_gate_ports(type_key, inputs, size=50),
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
def _mux_spec(select_bits: int) -> ComponentSpec:
    data_inputs = 1 << select_bits
    height = max(40, 20 * data_inputs)
    # Logisim multiplexer: output east-anchored; data inputs on left,
    # spaced ``2 * dy`` apart depending on size. We approximate by using
    # a uniform vertical pitch of 10 px.
    ports: list[PortSpec] = []
    pitch = max(10, height // data_inputs)
    top = -((data_inputs - 1) * pitch) // 2
    for i in range(data_inputs):
        ports.append(PortSpec(label=f"d{i}", dx=-30, dy=top + i * pitch, direction="in"))
    ports.append(PortSpec(label="sel", dx=-10, dy=height // 2 - 5, direction="in"))
    ports.append(PortSpec(label="out", dx=0, dy=0, direction="out"))
    return ComponentSpec(
        type_key=f"Multiplexer_{select_bits}",
        lib_desc="#Plexers",
        logisim_name="Multiplexer",
        bbox=(30, height),
        anchor=(30, height // 2),
        default_attrs={
            "facing": "east",
            "select": str(select_bits),
        },
        ports=tuple(ports),
    )


def _demux_spec(select_bits: int) -> ComponentSpec:
    data_outputs = 1 << select_bits
    height = max(40, 20 * data_outputs)
    ports: list[PortSpec] = [PortSpec(label="in", dx=-30, dy=0, direction="in")]
    pitch = max(10, height // data_outputs)
    top = -((data_outputs - 1) * pitch) // 2
    for i in range(data_outputs):
        ports.append(PortSpec(label=f"q{i}", dx=0, dy=top + i * pitch, direction="out"))
    ports.append(PortSpec(label="sel", dx=-10, dy=height // 2 - 5, direction="in"))
    return ComponentSpec(
        type_key=f"Demultiplexer_{select_bits}",
        lib_desc="#Plexers",
        logisim_name="Demultiplexer",
        bbox=(30, height),
        anchor=(30, height // 2),
        default_attrs={"facing": "east", "select": str(select_bits)},
        ports=tuple(ports),
    )


def _decoder_spec(select_bits: int) -> ComponentSpec:
    outputs = 1 << select_bits
    height = max(40, 20 * outputs)
    pitch = max(10, height // outputs)
    top = -((outputs - 1) * pitch) // 2
    ports: list[PortSpec] = []
    for i in range(outputs):
        ports.append(PortSpec(label=f"q{i}", dx=0, dy=top + i * pitch, direction="out"))
    ports.append(PortSpec(label="sel", dx=-30, dy=0, direction="in"))
    return ComponentSpec(
        type_key=f"Decoder_{select_bits}",
        lib_desc="#Plexers",
        logisim_name="Decoder",
        bbox=(30, height),
        anchor=(30, height // 2),
        default_attrs={"facing": "east", "select": str(select_bits)},
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
# Register and Counter use Logisim's default ("evolution") appearance.
# Coordinates verified against Register.configurePorts and
# Counter.configurePorts in logisim-evolution main as of 4.0.0:
#   Register evolution: bounds (0,0)..(60,90); ports
#     Q@(60,30), D@(0,30), clk@(0,70), reset@(30,90), enable@(0,50).
#   Counter evolution: bounds (0,0)..(sym+40, height); ports
#     Q@(sym+40, q_y), D@(0, q_y), clk@(0,80), clr@(0,20), ld@(0,30),
#     ud@(0,50), en@(0,70), carry@(sym+40, 50);
#     q_y = 120 if width==1 else 110;
#     sym = Counter.getSymbolWidth(width).
def _counter_symbol_width(width: int) -> int:
    if width <= 3:
        return 140
    if width <= 8:
        return 150
    if width <= 16:
        return 160
    return 190


def _counter_height(width: int) -> int:
    # Verified empirically with InstanceFactory.getOffsetBounds.
    return {1: 130, 2: 150, 3: 170, 4: 190, 5: 210, 6: 230, 7: 250, 8: 270}.get(
        width, 270 + 20 * (width - 8)
    )


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


def gate_spec(gate: str, inputs: int = 2) -> ComponentSpec:
    name = gate.upper()
    if name not in GATE_TYPES:
        raise KeyError(f"unknown gate type {gate!r}; supported: {sorted(GATE_TYPES)}")
    logisim_name = GATE_TYPES[name]
    if name in ("NOT", "BUF"):
        inputs = 1
    return _gate_spec(name, logisim_name, inputs)


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


def mux_spec(select_bits: int) -> ComponentSpec:
    return _mux_spec(select_bits)


def demux_spec(select_bits: int) -> ComponentSpec:
    return _demux_spec(select_bits)


def decoder_spec(select_bits: int) -> ComponentSpec:
    return _decoder_spec(select_bits)


def adder_spec(bits: int = 1) -> ComponentSpec:
    return _adder_spec(bits)


def comparator_spec(bits: int = 1) -> ComponentSpec:
    return _comparator_spec(bits)


def register_spec(bits: int = 1) -> ComponentSpec:
    return _register_spec(bits)


def counter_spec(bits: int = 1) -> ComponentSpec:
    return _counter_spec(bits)


# A flat registry used by builder_tools to resolve `add_component(type=…)`
# without ad-hoc switches.
SPEC_FACTORIES: dict[str, callable] = {
    "AND": lambda **kw: gate_spec("AND", inputs=kw.get("inputs", 2)),
    "OR": lambda **kw: gate_spec("OR", inputs=kw.get("inputs", 2)),
    "NAND": lambda **kw: gate_spec("NAND", inputs=kw.get("inputs", 2)),
    "NOR": lambda **kw: gate_spec("NOR", inputs=kw.get("inputs", 2)),
    "XOR": lambda **kw: gate_spec("XOR", inputs=kw.get("inputs", 2)),
    "XNOR": lambda **kw: gate_spec("XNOR", inputs=kw.get("inputs", 2)),
    "NOT": lambda **kw: gate_spec("NOT"),
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
}


def resolve(type_key: str, **kw) -> ComponentSpec:
    if type_key not in SPEC_FACTORIES:
        raise KeyError(
            f"unknown component type {type_key!r}; "
            f"supported: {sorted(SPEC_FACTORIES)}"
        )
    return SPEC_FACTORIES[type_key](**kw)
