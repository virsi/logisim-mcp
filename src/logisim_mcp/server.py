"""FastMCP server instance for Logisim Evolution."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("logisim-mcp")


def register_all_tools() -> None:
    """Import every tool module so its @mcp.tool() decorators run."""
    from .tools import (  # noqa: F401
        io_tools,
        builder_tools,
        highlevel_tools,
        sim_tools,
        describe_tools,
    )


register_all_tools()
