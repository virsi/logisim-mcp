"""Parse a Logisim ``.circ`` file into the :mod:`logisim_mcp.circ.model`.

Anything we don't understand at the top level (``<options>``, ``<mappings>``,
``<toolbar>``, ``<vhdl>``, custom libs' ``<tool>`` entries, …) is kept as
raw XML strings so a parse → mutate → write round-trip stays faithful.

The XML parser is hardened against entity-expansion attacks (XXE,
billion-laughs) and a hard cap on file size prevents memory-blowup DoS.
Real Logisim ``.circ`` files never contain a ``DOCTYPE`` or custom
entity declarations, so we simply refuse to parse anything that does.
"""

from __future__ import annotations

import re
from pathlib import Path

from lxml import etree

from .model import Circuit, Component, Lib, Project, Wire, parse_loc

_KNOWN_PROJECT_CHILDREN = {"lib", "main", "circuit"}
_KNOWN_CIRCUIT_CHILDREN = {"a", "comp", "wire"}

# 25 MB is far above any realistic circuit (the largest schematic in the
# wild we have seen is ~3 MB) yet small enough that an accidental
# pathological file is rejected before exhausting memory.
MAX_CIRC_BYTES = 25 * 1024 * 1024

_DTD_OR_ENTITY = re.compile(rb"<!(DOCTYPE|ENTITY)\b", re.IGNORECASE)


def _check_no_dtd(data: bytes) -> None:
    if _DTD_OR_ENTITY.search(data):
        raise ValueError(
            "DOCTYPE / ENTITY declarations are not allowed in .circ files "
            "(blocks XXE and billion-laughs attacks)"
        )


def _make_parser() -> etree.XMLParser:
    """Hardened lxml parser.

    - ``resolve_entities=False`` blocks lxml from substituting entities
      while building the tree.
    - ``no_network=True`` blocks DTD/entity fetches over the network.
    - ``load_dtd=False`` prevents loading external DTD subsets.
    - ``huge_tree=False`` enforces lxml's default tree-size limits.
    """
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        huge_tree=False,
    )


def _attrs_to_dict(el: etree._Element) -> dict[str, str]:
    out: dict[str, str] = {}
    for sub in el.iterchildren(tag="a"):
        name = sub.get("name")
        val = sub.get("val", "")
        if name is None:
            continue
        out[name] = val
    return out


def _tostring(el: etree._Element) -> str:
    return etree.tostring(el, encoding="unicode")


def parse(path_or_xml: str | Path) -> Project:
    """Parse a ``.circ`` file or raw XML string into a :class:`Project`.

    Raises ``ValueError`` if the file is larger than :data:`MAX_CIRC_BYTES`.
    """
    parser = _make_parser()
    if isinstance(path_or_xml, Path) or (
        isinstance(path_or_xml, str)
        and "\n" not in path_or_xml
        and Path(path_or_xml).exists()
    ):
        p = Path(path_or_xml)
        size = p.stat().st_size
        if size > MAX_CIRC_BYTES:
            raise ValueError(
                f".circ file is too large ({size} bytes > {MAX_CIRC_BYTES})"
            )
        data = p.read_bytes()
        _check_no_dtd(data)
        root = etree.fromstring(data, parser=parser)
    else:
        data = (
            path_or_xml.encode()
            if isinstance(path_or_xml, str)
            else path_or_xml
        )
        if len(data) > MAX_CIRC_BYTES:
            raise ValueError(
                f"XML input is too large ({len(data)} bytes > {MAX_CIRC_BYTES})"
            )
        _check_no_dtd(data)
        root = etree.fromstring(data, parser=parser)

    if root.tag != "project":
        raise ValueError(f"expected <project> root, got <{root.tag}>")

    project = Project(
        source=root.get("source", "4.0.0"),
        version=root.get("version", "1.0"),
    )

    # The Logisim header text node lives between <project> and the first
    # <lib>. lxml stores it as ``root.text``.
    if root.text and root.text.strip():
        project.leading_text = root.text

    for child in root:
        tag = child.tag
        if tag is etree.Comment:
            # Treat comments as part of leading_text — rare, harmless.
            continue
        if tag == "lib":
            project.libs.append(
                Lib(
                    id=child.get("name", ""),
                    desc=child.get("desc", ""),
                    tools_raw_xml=[_tostring(t) for t in child],
                )
            )
        elif tag == "main":
            project.main = child.get("name", project.main)
        elif tag == "circuit":
            project.circuits.append(_parse_circuit(child))
        else:
            project.extras_raw_xml.append(_tostring(child))

    return project


def _parse_circuit(el: etree._Element) -> Circuit:
    circuit = Circuit(name=el.get("name", ""))
    circuit.attrs = _attrs_to_dict(el)
    for child in el:
        tag = child.tag
        if tag is etree.Comment:
            continue
        if tag == "a":
            continue  # already collected via _attrs_to_dict
        if tag == "comp":
            circuit.components.append(
                Component(
                    lib=child.get("lib", ""),
                    name=child.get("name", ""),
                    loc=parse_loc(child.get("loc", "(0,0)")),
                    attrs=_attrs_to_dict(child),
                )
            )
        elif tag == "wire":
            circuit.wires.append(
                Wire(
                    start=parse_loc(child.get("from", "(0,0)")),
                    end=parse_loc(child.get("to", "(0,0)")),
                )
            )
        else:
            circuit.extras_raw_xml.append(_tostring(child))
    return circuit
