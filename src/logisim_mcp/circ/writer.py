"""Serialise a :class:`logisim_mcp.circ.model.Project` back to ``.circ`` XML.

The output mirrors Logisim's own indentation style (two-space indent, every
element on its own line, ``<a name="…" val="…"/>`` self-closing) so files
stay diff-friendly across round-trips.
"""

from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import quoteattr

from .model import Circuit, Component, Project, Wire, fmt_loc

INDENT = "  "
XML_DECL = '<?xml version="1.0" encoding="UTF-8" standalone="no"?>'


def _dedupe_wires(wires: list[Wire]) -> list[Wire]:
    """Drop duplicate wires (ignoring endpoint order).

    Attributes on a later copy are kept when the first copy omitted them,
    so a second ``buswidthpos`` is not thrown away with the duplicate.
    """
    order: list[tuple[tuple[int, int], tuple[int, int]]] = []
    merged: dict[tuple[tuple[int, int], tuple[int, int]], Wire] = {}
    for wire in wires:
        key = (wire.start, wire.end) if wire.start <= wire.end else (wire.end, wire.start)
        current = merged.get(key)
        if current is None:
            merged[key] = Wire(start=wire.start, end=wire.end, attrs=dict(wire.attrs))
            order.append(key)
            continue
        for name, value in wire.attrs.items():
            current.attrs.setdefault(name, value)
    return [merged[key] for key in order]


def _attr(name: str, value: str) -> str:
    return f"{name}={quoteattr(value)}"


def _attrs_block(attrs: dict[str, str], indent: str) -> list[str]:
    out: list[str] = []
    for name, val in attrs.items():
        out.append(f"{indent}<a {_attr('name', name)} {_attr('val', val)}/>")
    return out


def _comp(comp: Component, indent: str) -> list[str]:
    head = (
        f"{indent}<comp "
        f"{_attr('lib', comp.lib)} "
        f"{_attr('loc', fmt_loc(comp.loc))} "
        f"{_attr('name', comp.name)}"
    )
    if not comp.attrs:
        return [head + "/>"]
    out = [head + ">"]
    out.extend(_attrs_block(comp.attrs, indent + INDENT))
    out.append(f"{indent}</comp>")
    return out


def _wire(w: Wire, indent: str) -> str:
    extra = "".join(f" {_attr(name, val)}" for name, val in w.attrs.items())
    return (
        f"{indent}<wire "
        f"{_attr('from', fmt_loc(w.start))} "
        f"{_attr('to', fmt_loc(w.end))}"
        f"{extra}/>"
    )


def _circuit(c: Circuit, indent: str) -> list[str]:
    lines: list[str] = [f"{indent}<circuit {_attr('name', c.name)}>"]
    sub = indent + INDENT
    lines.extend(_attrs_block(c.attrs, sub))
    for w in _dedupe_wires(c.wires):
        lines.append(_wire(w, sub))
    for comp in c.components:
        lines.extend(_comp(comp, sub))
    for raw in c.extras_raw_xml:
        # Each raw chunk may already have its own indentation — prefix it
        # uniformly so the output still looks clean.
        for line in raw.splitlines():
            lines.append(sub + line if line.strip() else line)
    lines.append(f"{indent}</circuit>")
    return lines


def dump(project: Project) -> str:
    lines: list[str] = [XML_DECL]
    lines.append(
        f"<project {_attr('source', project.source)} {_attr('version', project.version)}>"
    )
    if project.leading_text and project.leading_text.strip():
        # Re-emit the Logisim header comment as a single indented line.
        marker = project.leading_text.strip()
        lines.append(f"{INDENT}{marker}")
    for lib in project.libs:
        if lib.tools_raw_xml:
            lines.append(
                f"{INDENT}<lib {_attr('desc', lib.desc)} {_attr('name', lib.id)}>"
            )
            for tool_xml in lib.tools_raw_xml:
                for ln in tool_xml.splitlines():
                    if ln.strip():
                        lines.append(INDENT + INDENT + ln.strip())
            lines.append(f"{INDENT}</lib>")
        else:
            lines.append(
                f"{INDENT}<lib {_attr('desc', lib.desc)} {_attr('name', lib.id)}/>"
            )
    lines.append(f"{INDENT}<main {_attr('name', project.main)}/>")
    for raw in project.extras_raw_xml:
        for ln in raw.splitlines():
            if ln.strip():
                lines.append(INDENT + ln.strip())
    for c in project.circuits:
        lines.extend(_circuit(c, INDENT))
    lines.append("</project>")
    return "\n".join(lines) + "\n"


def save(project: Project, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(dump(project), encoding="utf-8")
    return p
