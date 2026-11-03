"""Port maps checked against Logisim Evolution 5.0.0."""

from logisim_mcp.circ.factory import empty_project
from logisim_mcp.circ.library import (
    counter_spec,
    decoder_spec,
    demux_spec,
    flip_flop_spec,
    gate_spec,
    led_spec,
    mux_spec,
    register_spec,
    spec_for_component,
    with_facing,
)
from logisim_mcp.circ.model import Component


def test_not_uses_wide_size_option() -> None:
    spec = gate_spec("NOT")
    assert spec.default_attrs == {"size": "30"}
    assert (spec.input_port(0).dx, spec.input_port(0).dy) == (-30, 0)


def test_buffer_omits_size_attribute() -> None:
    spec = gate_spec("BUF")
    assert spec.default_attrs == {}
    assert (spec.input_port(0).dx, spec.input_port(0).dy) == (-20, 0)


def test_mux_2to1_ports() -> None:
    spec = mux_spec(1)
    assert (spec.port_by_label("d0").dx, spec.port_by_label("d0").dy) == (-30, -10)
    assert (spec.port_by_label("d1").dx, spec.port_by_label("d1").dy) == (-30, 10)
    assert (spec.port_by_label("sel").dx, spec.port_by_label("sel").dy) == (-20, 20)
    assert (spec.port_by_label("out").dx, spec.port_by_label("out").dy) == (0, 0)


def test_mux_4to1_ports() -> None:
    spec = mux_spec(2)
    assert (spec.port_by_label("d0").dx, spec.port_by_label("d0").dy) == (-40, -20)
    assert (spec.port_by_label("d3").dx, spec.port_by_label("d3").dy) == (-40, 10)
    assert (spec.port_by_label("sel").dx, spec.port_by_label("sel").dy) == (-20, 20)


def test_decoder_disables_enable_pin() -> None:
    spec = decoder_spec(2)
    assert spec.default_attrs["enable"] == "false"
    assert (spec.port_by_label("q0").dx, spec.port_by_label("q0").dy) == (20, -40)
    assert (spec.port_by_label("q3").dx, spec.port_by_label("q3").dy) == (20, -10)
    assert (spec.port_by_label("sel").dx, spec.port_by_label("sel").dy) == (0, 0)


def test_demux_anchor_is_the_data_input() -> None:
    spec = demux_spec(1)
    assert (spec.port_by_label("in").dx, spec.port_by_label("in").dy) == (0, 0)
    assert (spec.port_by_label("q0").dx, spec.port_by_label("q0").dy) == (30, -10)
    assert (spec.port_by_label("sel").dx, spec.port_by_label("sel").dy) == (20, 20)


def test_narrow_nand_and_south_facing() -> None:
    spec = gate_spec("NAND", inputs=2, size=30)
    assert (spec.port_by_label("in0").dx, spec.port_by_label("in0").dy) == (-40, -10)
    assert (spec.port_by_label("in1").dx, spec.port_by_label("in1").dy) == (-40, 10)
    south = with_facing(spec, "south")
    assert (south.port_by_label("in0").dx, south.port_by_label("in0").dy) == (-10, -40)
    assert (south.port_by_label("out").dx, south.port_by_label("out").dy) == (0, 0)


def test_not_narrow_size_is_the_axis() -> None:
    spec = gate_spec("NOT", size=20)
    assert spec.default_attrs["size"] == "20"
    assert (spec.input_port(0).dx, spec.input_port(0).dy) == (-20, 0)


def test_d_flip_flop_evolution_ports() -> None:
    spec = flip_flop_spec("D Flip-Flop")
    assert spec.default_attrs["appearance"] == "logisim_evolution"
    assert (spec.port_by_label("D").dx, spec.port_by_label("D").dy) == (-10, 10)
    assert (spec.port_by_label("CLK").dx, spec.port_by_label("CLK").dy) == (-10, 50)
    assert (spec.port_by_label("Q").dx, spec.port_by_label("Q").dy) == (50, 10)
    assert (spec.port_by_label("Q_bar").dx, spec.port_by_label("Q_bar").dy) == (50, 50)
    assert (spec.port_by_label("S").dx, spec.port_by_label("S").dy) == (20, 0)
    assert (spec.port_by_label("R").dx, spec.port_by_label("R").dy) == (20, 60)


def test_jk_flip_flop_and_led_ports() -> None:
    spec = flip_flop_spec("J-K Flip-Flop")
    assert (spec.port_by_label("J").dx, spec.port_by_label("J").dy) == (-10, 10)
    assert (spec.port_by_label("K").dx, spec.port_by_label("K").dy) == (-10, 30)
    assert (spec.port_by_label("CLK").dx, spec.port_by_label("CLK").dy) == (-10, 50)
    led = led_spec()
    assert led.logisim_name == "LED"
    assert (led.port_by_label("in").dx, led.port_by_label("in").dy) == (0, 0)


def test_type_output_pin_and_rotated_gate_are_recognized() -> None:
    project = empty_project()
    circuit = project.circuits[0]
    pin = Component(lib="0", name="Pin", loc=(10, 10), attrs={"type": "output", "label": "Y"})
    gate = Component(
        lib="1",
        name="NAND Gate",
        loc=(80, 80),
        attrs={"facing": "south", "size": "30", "inputs": "2"},
    )
    circuit.components.extend([pin, gate])
    pin_spec = spec_for_component(project, pin)
    gate_spec_found = spec_for_component(project, gate)
    assert pin_spec is not None and pin_spec.type_key == "OutputPin"
    assert gate_spec_found is not None
    assert (gate_spec_found.port_by_label("in0").dx, gate_spec_found.port_by_label("in0").dy) == (
        -10,
        -40,
    )


def test_three_input_spacing_follows_gate_size() -> None:
    # AbstractGate.getInputOffset: size < 60 uses 20px spacing, even for 3 inputs.
    medium = gate_spec("OR", inputs=3, size=50)
    assert [medium.input_port(i).dy for i in range(3)] == [-20, 0, 20]
    wide = gate_spec("OR", inputs=3, size=70)
    assert [wide.input_port(i).dy for i in range(3)] == [-30, 0, 30]


def test_mux_facing_size_and_select_location() -> None:
    north = mux_spec(1, facing="north")
    assert (north.port_by_label("sel").dx, north.port_by_label("sel").dy) == (-20, 20)
    assert (north.port_by_label("d0").dx, north.port_by_label("d0").dy) == (-10, 30)
    narrow = mux_spec(1, narrow=True)
    assert (narrow.port_by_label("d0").dx, narrow.port_by_label("d0").dy) == (-20, -10)
    assert (narrow.port_by_label("sel").dx, narrow.port_by_label("sel").dy) == (-10, 20)
    top = mux_spec(1, selloc="tr")
    assert (top.port_by_label("sel").dx, top.port_by_label("sel").dy) == (-20, -20)


def test_decoder_north_ports_and_default_enable() -> None:
    pair = decoder_spec(1, facing="north")
    assert (pair.port_by_label("q0").dx, pair.port_by_label("q0").dy) == (10, -10)
    assert (pair.port_by_label("q1").dx, pair.port_by_label("q1").dy) == (30, -10)
    wide = decoder_spec(3, facing="north")
    assert (wide.port_by_label("q0").dx, wide.port_by_label("q0").dy) == (0, -20)
    assert (wide.port_by_label("q1").dx, wide.port_by_label("q1").dy) == (10, -20)
    project = empty_project()
    omitted = Component("2", "Decoder", (0, 0), {"select": "2"})
    spec = spec_for_component(project, omitted)
    assert spec is not None
    assert (spec.port_by_label("en").dx, spec.port_by_label("en").dy) == (-10, 0)


def test_classic_register_and_counter_ports() -> None:
    register = register_spec(4, classic=True)
    assert (register.port_by_label("Q").dx, register.port_by_label("Q").dy) == (0, 0)
    assert (register.port_by_label("D").dx, register.port_by_label("D").dy) == (-30, 0)
    assert (register.port_by_label("clk").dx, register.port_by_label("clk").dy) == (-20, 20)
    assert (register.port_by_label("rst").dx, register.port_by_label("rst").dy) == (-10, 20)
    assert (register.port_by_label("en").dx, register.port_by_label("en").dy) == (-30, 10)
    counter = counter_spec(4, classic=True)
    assert (counter.port_by_label("ld").dx, counter.port_by_label("ld").dy) == (-30, -10)
    assert (counter.port_by_label("ud").dx, counter.port_by_label("ud").dy) == (-20, -20)
    assert (counter.port_by_label("carry").dx, counter.port_by_label("carry").dy) == (0, 10)
    project = empty_project()
    saved = Component(
        "5",
        "Register",
        (0, 0),
        {"width": "4", "appearance": "classic"},
    )
    found = spec_for_component(project, saved)
    assert found is not None
    assert (found.port_by_label("D").dx, found.port_by_label("D").dy) == (-30, 0)


def test_north_demux_does_not_use_gate_rotation() -> None:
    spec = demux_spec(1, facing="north")
    assert (spec.port_by_label("q0").dx, spec.port_by_label("q0").dy) == (-10, -30)
    assert (spec.port_by_label("sel").dx, spec.port_by_label("sel").dy) == (-20, -20)


def test_counter_bounds_follow_grouped_rows() -> None:
    # (bits, symbol width, height, Q dx, Q dy) from Counter.java in 5.0.0.
    cases = [
        (1, 140, 130, 180, 120),
        (4, 150, 190, 190, 110),
        (9, 150, 170, 190, 110),
        (17, 160, 210, 200, 110),
    ]
    for bits, sym, height, qdx, qdy in cases:
        spec = counter_spec(bits)
        assert spec.bbox == (sym + 40, height), bits
        q = spec.port_by_label("Q")
        assert (q.dx, q.dy) == (qdx, qdy), bits
