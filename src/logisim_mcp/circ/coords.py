"""Grid utilities, L-shaped routing, and bbox helpers for Logisim layouts.

Logisim snaps everything to a 10 px grid; misaligned coordinates silently
become "floating" wires in the GUI. Every helper below preserves that
invariant.
"""

from __future__ import annotations

from .library import ComponentSpec
from .model import Component, Point, Wire

GRID = 10


def snap(point: Point, grid: int = GRID) -> Point:
    """Snap a point to the nearest grid intersection."""
    return (round(point[0] / grid) * grid, round(point[1] / grid) * grid)


def port_location(comp: Component, spec: ComponentSpec, port_label: str) -> Point:
    """Absolute coordinates of a named port on ``comp``."""
    p = spec.port_by_label(port_label)
    return (comp.loc[0] + p.dx, comp.loc[1] + p.dy)


def route_l(a: Point, b: Point) -> list[Wire]:
    """Return up to two wire segments forming an L between ``a`` and ``b``.

    Strategy: horizontal first, then vertical. Empty result iff a == b.
    """
    a = snap(a)
    b = snap(b)
    if a == b:
        return []
    if a[0] == b[0] or a[1] == b[1]:
        return [Wire(start=a, end=b)]
    mid = (b[0], a[1])
    return [Wire(start=a, end=mid), Wire(start=mid, end=b)]


def bbox_corners(comp: Component, spec: ComponentSpec) -> tuple[Point, Point]:
    """Compute the (top-left, bottom-right) bounding box of a component."""
    w, h = spec.bbox
    ax, ay = spec.anchor
    top_left = (comp.loc[0] - ax, comp.loc[1] - ay)
    bottom_right = (top_left[0] + w, top_left[1] + h)
    return top_left, bottom_right


def overlaps(a_tl: Point, a_br: Point, b_tl: Point, b_br: Point) -> bool:
    return not (a_br[0] <= b_tl[0] or b_br[0] <= a_tl[0] or a_br[1] <= b_tl[1] or b_br[1] <= a_tl[1])


def auto_place(
    occupied: list[tuple[Point, Point]],
    spec: ComponentSpec,
    start: Point = (140, 80),
    step_x: int = 80,
    step_y: int = 60,
    columns: int = 8,
) -> Point:
    """Find a free anchor position for a new component.

    ``occupied`` is a list of ``(top_left, bottom_right)`` bboxes. We
    sweep a coarse grid row-by-row until we find a slot whose anchored
    bbox doesn't intersect anything already placed.
    """
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
            if not any(overlaps(tl, br, otl, obr) for otl, obr in occupied):
                return candidate
        row += 1
    raise RuntimeError("auto_place: ran out of grid slots")
