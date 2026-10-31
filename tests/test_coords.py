from __future__ import annotations

import pytest

from logisim_mcp.circ.coords import RouteBlocked, auto_place, route_l, snap
from logisim_mcp.circ.library import gate_spec
from logisim_mcp.circ.model import Wire


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


def test_route_l_prefers_the_clear_elbow() -> None:
    wires = route_l((100, 100), (200, 150), occupied_ports={(200, 100)})
    assert [(w.start, w.end) for w in wires] == [
        ((100, 100), (100, 150)),
        ((100, 150), (200, 150)),
    ]


def test_route_l_doglegs_when_both_elbows_are_blocked() -> None:
    wires = route_l(
        (100, 100),
        (200, 150),
        occupied_ports={(200, 100), (100, 150)},
    )
    assert len(wires) == 3
    assert wires[0].start == (100, 100)
    assert wires[-1].end == (200, 150)


def test_route_l_avoids_colinear_overlap() -> None:
    blocking = [Wire(start=(150, 100), end=(250, 100))]
    wires = route_l((100, 100), (200, 150), existing_wires=blocking)
    assert wires[0].end == (100, 150)


def test_route_l_reuses_the_source_branch_without_shorting_a_foreign_corner() -> None:
    existing = [
        # Source branch on the net being extended.
        Wire(start=(100, 100), end=(150, 100)),
        # A different net turning at (100, 150).
        Wire(start=(100, 150), end=(50, 150)),
        Wire(start=(100, 150), end=(100, 180)),
    ]
    wires = route_l((100, 100), (200, 150), existing_wires=existing)
    assert [(w.start, w.end) for w in wires] == [
        ((100, 100), (200, 100)),
        ((200, 100), (200, 150)),
    ]


def test_route_l_allows_a_target_branch_on_the_intended_net() -> None:
    existing = [Wire(start=(200, 150), end=(160, 150))]
    wires = route_l((100, 100), (200, 150), existing_wires=existing)
    assert wires[-1].end == (200, 150)
    assert [(w.start, w.end) for w in wires] == [
        ((100, 100), (200, 100)),
        ((200, 100), (200, 150)),
    ]


def test_route_l_refuses_a_fully_blocked_path() -> None:
    wires = []
    for step in range(1, 31):
        for channel in (step * 10, -step * 10):
            wires.append(Wire(start=(channel, 0), end=(channel, 100)))
            wires.append(Wire(start=(0, channel), end=(100, channel)))
    with pytest.raises(RouteBlocked):
        route_l((0, 0), (100, 100), occupied_ports={(100, 0), (0, 100)}, existing_wires=wires)


def test_auto_place_avoids_existing_wires() -> None:
    spec = gate_spec("AND")
    first = auto_place([], spec)
    blocked = auto_place([], spec, wires=[Wire(start=(100, 60), end=(100, 100))])
    assert blocked != first


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
