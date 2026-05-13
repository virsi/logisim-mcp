"""Entry point: `python -m logisim_mcp` runs the stdio MCP server."""

from __future__ import annotations

from .server import mcp


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
