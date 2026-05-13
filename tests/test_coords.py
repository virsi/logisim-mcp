from __future__ import annotations

from logisim_mcp.circ.coords import auto_place, route_l, snap
from logisim_mcp.circ.library import gate_spec


def test_snap_to_grid() -> None:
    assert snap((103, 97)) == (100, 100)
    assert snap((44, 12)) == (40, 10)
    assert snap((46, 18)) == (50, 20)


def test_route_l_straight() -> None:
    wires = route_l((100, 100), (200, 100))
    assert len(wires) == 1
    assert wires[0].start == (100, 100)
    assert wires[0].end == (200, 100)


def test_route_l_corner() -> None:
    wires = route_l((100, 100), (200, 150))
    assert len(wires) == 2
    assert wires[0].start == (100, 100)
    assert wires[0].end == (200, 100)
    assert wires[1].start == (200, 100)
    assert wires[1].end == (200, 150)


def test_route_l_zero_length() -> None:
    assert route_l((50, 50), (50, 50)) == []


def test_auto_place_finds_distinct_slots() -> None:
    spec = gate_spec("AND")
    placed: list[tuple[tuple[int, int], tuple[int, int]]] = []
    pts = []
    for _ in range(4):
        anchor = auto_place(placed, spec)
        pts.append(anchor)
        tl = (anchor[0] - spec.anchor[0], anchor[1] - spec.anchor[1])
        br = (tl[0] + spec.bbox[0], tl[1] + spec.bbox[1])
        placed.append((tl, br))
    assert len(set(pts)) == 4
