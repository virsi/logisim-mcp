"""Entry point.

``python -m logisim_mcp`` runs the stdio MCP server.
``python -m logisim_mcp setup`` registers that server with a local agent.
"""

from __future__ import annotations

import sys


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "setup":
        from .client_setup import main as setup_main

        sys.exit(setup_main(sys.argv[2:]))
    from .server import mcp

    mcp.run()


if __name__ == "__main__":
    main()
