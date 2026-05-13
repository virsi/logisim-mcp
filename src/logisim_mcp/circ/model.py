"""Data model for a Logisim Evolution `.circ` project.

The model is intentionally lossy: it captures everything our tools need to
create, mutate, and re-serialize circuits, while preserving unknown
top-level elements (``<options>``, ``<mappings>``, ``<toolbar>``, …) and
``<tool>`` children of ``<lib>`` as raw XML so we don't accidentally drop
them on round-trip.
"""

from __future__ import annotations

from dataclasses import dataclass, field

Point = tuple[int, int]


def parse_loc(raw: str) -> Point:
    """Parse a Logisim location string ``(x,y)`` into a tuple of ints."""
    s = raw.strip()
    if not (s.startswith("(") and s.endswith(")")):
        raise ValueError(f"invalid loc: {raw!r}")
    x_str, _, y_str = s[1:-1].partition(",")
    return int(x_str.strip()), int(y_str.strip())


def fmt_loc(point: Point) -> str:
    """Format a point as ``(x,y)`` — Logisim's canonical form."""
    return f"({point[0]},{point[1]})"


@dataclass
class Lib:
    """A ``<lib desc="…" name="ID">`` entry."""

    id: str
    desc: str
    # Raw XML of any <tool> children — we keep them verbatim so Pin's
    # appearance="classic" tweaks etc. survive a round-trip.
    tools_raw_xml: list[str] = field(default_factory=list)


@dataclass
class Component:
    """A ``<comp lib="L" loc="(x,y)" name="N">`` with its ``<a>`` attributes."""

    lib: str
    name: str
    loc: Point
    attrs: dict[str, str] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return f"{self.name}@{fmt_loc(self.loc)}"


@dataclass
class Wire:
    """A ``<wire from="(x1,y1)" to="(x2,y2)"/>`` segment."""

    start: Point
    end: Point


@dataclass
class Circuit:
    """A ``<circuit name="…">`` block."""

    name: str
    attrs: dict[str, str] = field(default_factory=dict)
    components: list[Component] = field(default_factory=list)
    wires: list[Wire] = field(default_factory=list)
    # Raw XML for unknown direct children (e.g. <appear>...) — preserved verbatim.
    extras_raw_xml: list[str] = field(default_factory=list)

    def find_component(self, loc: Point) -> Component | None:
        for c in self.components:
            if c.loc == loc:
                return c
        return None


@dataclass
class Project:
    """The whole ``<project>`` document."""

    source: str = "4.0.0"
    version: str = "1.0"
    libs: list[Lib] = field(default_factory=list)
    main: str = "main"
    circuits: list[Circuit] = field(default_factory=list)
    # Raw XML of unknown top-level elements (<options>, <mappings>,
    # <toolbar>, <vhdl>, …) so we don't drop them.
    extras_raw_xml: list[str] = field(default_factory=list)
    # Optional leading text node ("This file is intended to be loaded …")
    leading_text: str | None = None

    def lib_id_for_desc(self, desc: str) -> str:
        for lib in self.libs:
            if lib.desc == desc:
                return lib.id
        raise KeyError(f"library {desc!r} not present in project")

    def lib_desc_for_id(self, lib_id: str) -> str:
        for lib in self.libs:
            if lib.id == lib_id:
                return lib.desc
        raise KeyError(f"library id {lib_id!r} not present in project")

    def find_circuit(self, name: str) -> Circuit | None:
        for c in self.circuits:
            if c.name == name:
                return c
        return None

    def require_circuit(self, name: str) -> Circuit:
        c = self.find_circuit(name)
        if c is None:
            raise KeyError(f"circuit {name!r} not found")
        return c
