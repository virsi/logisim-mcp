"""Constructors for fresh Logisim projects.

A blank project Logisim Evolution 5.0.0 will open. The library list matches
a file saved by the 5.0.0 GUI. Numeric ids are file-local.
"""

from __future__ import annotations

from .library import STANDARD_LIBS
from .model import Circuit, Lib, Project


_LEADING_TEXT = (
    "This file is intended to be loaded by Logisim-evolution v5.0.0"
    "(https://github.com/logisim-evolution/)."
)


def empty_project(main_circuit: str = "main") -> Project:
    libs = [Lib(id=lib_id, desc=desc) for lib_id, desc in STANDARD_LIBS]
    # Logisim's default Pin <tool appearance="classic"> tweak — keep it so
    # newly-created files match what the GUI would save.
    libs[0].tools_raw_xml.append(
        '<tool name="Pin"><a name="appearance" val="classic"/></tool>'
    )
    circuit = Circuit(
        name=main_circuit,
        attrs={
            "circuit": main_circuit,
            "simulationFrequency": "1.0",
        },
    )
    project = Project(
        source="5.0.0",
        version="1.0",
        libs=libs,
        main=main_circuit,
        circuits=[circuit],
        leading_text=_LEADING_TEXT,
        extras_raw_xml=[
            '<options><a name="gateUndefined" val="ignore"/>'
            '<a name="simlimit" val="1000"/>'
            '<a name="simrand" val="0"/></options>',
            "<mappings/>",
            "<toolbar/>",
        ],
    )
    return project
