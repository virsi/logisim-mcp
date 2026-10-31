"""Grid utilities, L-shaped routing, and bbox helpers for Logisim layouts.

Logisim snaps everything to a 10 px grid; misaligned coordinates silently
become "floating" wires in the GUI. Every helper below preserves that
invariant.
"""

from __future__ import annotations

from .library import ComponentSpec
from .model import Component, Point, Wire

GRID = 10


class RouteBlocked(RuntimeError):
    """No axis-aligned path avoids the occupied ports and wires."""


def snap(point: Point, grid: int = GRID) -> Point:
    """Snap a point to the nearest grid intersection."""
    return (round(point[0] / grid) * grid, round(point[1] / grid) * grid)


def port_location(comp: Component, spec: ComponentSpec, port_label: str) -> Point:
    """Absolute coordinates of a named port on ``comp``."""
    p = spec.port_by_label(port_label)
    return (comp.loc[0] + p.dx, comp.loc[1] + p.dy)


def on_segment(point: Point, start: Point, end: Point, *, interior: bool = False) -> bool:
    """True when ``point`` lies on an axis-aligned segment.

    Diagonal segments are not wires Logisim will load, so they never match.
    ``interior`` excludes the two endpoints.
    """
    x, y = point
    x1, y1 = start
    x2, y2 = end
    if x1 == x2:
        if x != x1:
            return False
        lo, hi = (y1, y2) if y1 <= y2 else (y2, y1)
        return lo < y < hi if interior else lo <= y <= hi
    if y1 == y2:
        if y != y1:
            return False
        lo, hi = (x1, x2) if x1 <= x2 else (x2, x1)
        return lo < x < hi if interior else lo <= x <= hi
    return False


def _overlap_length(a0: int, a1: int, b0: int, b1: int) -> int:
    lo1, hi1 = (a0, a1) if a0 <= a1 else (a1, a0)
    lo2, hi2 = (b0, b1) if b0 <= b1 else (b1, b0)
    return min(hi1, hi2) - max(lo1, lo2)


def overlaps_colinear(a: Point, b: Point, c: Point, d: Point) -> bool:
    """True when two axis-aligned segments share more than a single point."""
    if a[1] == b[1] == c[1] == d[1]:
        return _overlap_length(a[0], b[0], c[0], d[0]) > 0
    if a[0] == b[0] == c[0] == d[0]:
        return _overlap_length(a[1], b[1], c[1], d[1]) > 0
    return False


def _segment_blocked(
    start: Point,
    end: Point,
    occupied: set[Point],
    wires: list[Wire],
    allow: set[Point],
) -> bool:
    if start == end:
        return False
    for point in occupied:
        if point in allow:
            continue
        if point == start or point == end or on_segment(point, start, end, interior=True):
            return True
    for wire in wires:
        if overlaps_colinear(start, end, wire.start, wire.end):
            return True
    return False


def _emit(segments: list[tuple[Point, Point]]) -> list[Wire]:
    return [Wire(start=s, end=e) for s, e in segments if s != e]


def _candidates(a: Point, b: Point) -> list[list[tuple[Point, Point]]]:
    options: list[list[tuple[Point, Point]]] = []
    if a[0] == b[0] or a[1] == b[1]:
        options.append([(a, b)])
    mid_h = (b[0], a[1])
    if mid_h != a and mid_h != b:
        options.append([(a, mid_h), (mid_h, b)])
    mid_v = (a[0], b[1])
    if mid_v != a and mid_v != b and mid_v != mid_h:
        options.append([(a, mid_v), (mid_v, b)])
    return options


def _dogleg(
    a: Point,
    b: Point,
    occupied: set[Point],
    wires: list[Wire],
) -> list[Wire] | None:
    allow = {a, b}
    ax, ay = a
    bx, by = b
    for step in range(1, 31):
        for channel in (ax + step * GRID, ax - step * GRID):
            if channel == bx:
                continue
            p1 = (channel, ay)
            p2 = (channel, by)
            segments = [(a, p1), (p1, p2), (p2, b)]
            if not any(_segment_blocked(s, e, occupied, wires, allow) for s, e in segments):
                return _emit(segments)
        for channel in (ay + step * GRID, ay - step * GRID):
            if channel == by:
                continue
            p1 = (ax, channel)
            p2 = (bx, channel)
            segments = [(a, p1), (p1, p2), (p2, b)]
            if not any(_segment_blocked(s, e, occupied, wires, allow) for s, e in segments):
                return _emit(segments)
    return None


def route_l(
    a: Point,
    b: Point,
    occupied_ports: set[Point] | list[Point] | None = None,
    existing_wires: list[Wire] | None = None,
) -> list[Wire]:
    """Route ``a`` to ``b`` with axis-aligned segments.

    With no obstacles this is horizontal-first, matching the historical
    L router. Otherwise it tries that L, then vertical-first, then a
    3-segment dogleg on a free grid channel. A segment is blocked when
    it touches an occupied port other than ``a`` and ``b``, or when it
    overlaps an existing wire along more than a point. If every
    candidate is blocked, this raises :class:`RouteBlocked` instead of
    drawing the short it was asked to avoid.
    """
    a = snap(a)
    b = snap(b)
    if a == b:
        return []
    occupied = set(occupied_ports or ())
    wires = list(existing_wires or ())
    options = _candidates(a, b)
    if not occupied and not wires:
        return _emit(options[0])
    allow = {a, b}
    for segments in options:
        if not any(_segment_blocked(s, e, occupied, wires, allow) for s, e in segments):
            return _emit(segments)
    dogleg = _dogleg(a, b, occupied, wires)
    if dogleg is not None:
        return dogleg
    raise RouteBlocked(f"no free path from {a} to {b}")


def bbox_corners(comp: Component, spec: ComponentSpec) -> tuple[Point, Point]:
    """Compute the (top-left, bottom-right) bounding box of a component."""
    w, h = spec.bbox
    ax, ay = spec.anchor
    top_left = (comp.loc[0] - ax, comp.loc[1] - ay)
    bottom_right = (top_left[0] + w, top_left[1] + h)
    return top_left, bottom_right


def overlaps(a_tl: Point, a_br: Point, b_tl: Point, b_br: Point) -> bool:
    return not (a_br[0] <= b_tl[0] or b_br[0] <= a_tl[0] or a_br[1] <= b_tl[1] or b_br[1] <= a_tl[1])


def wire_box(start: Point, end: Point) -> tuple[Point, Point]:
    """A 1px-thick box around an axis-aligned wire.

    ``overlaps`` treats a zero-area segment as a line it can miss, so the
    box is thickened enough that a component body covering the wire counts.
    """
    x1, y1 = start
    x2, y2 = end
    lo_x, hi_x = (x1, x2) if x1 <= x2 else (x2, x1)
    lo_y, hi_y = (y1, y2) if y1 <= y2 else (y2, y1)
    if lo_x == hi_x:
        hi_x += 1
    if lo_y == hi_y:
        hi_y += 1
    return (lo_x, lo_y), (hi_x, hi_y)


def auto_place(
    occupied: list[tuple[Point, Point]],
    spec: ComponentSpec,
    start: Point = (140, 80),
    step_x: int = 80,
    step_y: int = 60,
    columns: int = 8,
    wires: list[Wire] | None = None,
) -> Point:
    """Find a free anchor position for a new component.

    ``occupied`` is a list of ``(top_left, bottom_right)`` bboxes. Existing
    wires are blocked too, so a new body is not dropped onto a net.
    """
    blocked = list(occupied)
    for wire in wires or ():
        blocked.append(wire_box(wire.start, wire.end))
    w, h = spec.bbox
    ax, ay = spec.anchor
    row = 0
    while row < 256:  # hard ceiling, very generous
        for col in range(columns):
            cx = start[0] + col * step_x
            cy = start[1] + row * step_y
            candidate = snap((cx, cy))
            tl = (candidate[0] - ax, candidate[1] - ay)
            br = (tl[0] + w, tl[1] + h)
            if not any(overlaps(tl, br, otl, obr) for otl, obr in blocked):
                return candidate
        row += 1
    raise RuntimeError("auto_place: ran out of grid slots")
