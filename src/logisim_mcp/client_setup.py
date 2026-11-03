"""Register this server with a local agent.

``logisim-mcp setup`` writes the stdio MCP entry the agent launches.
It does not clone the repo into the agent's config: the command is either
this interpreter (``python -m logisim_mcp``) or ``uvx --from <git>``.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from .config import DEFAULT_LOGISIM_JAR

GIT_FROM = "git+https://github.com/virsi/logisim-mcp"
SERVER_NAME = "logisim"
CLIENTS = ("cursor", "claude-desktop", "claude-code")


def running_from_uv(executable: str) -> bool:
    """True when this process is a uv cache or tool environment.

    Those interpreter paths disappear when the cache is cleaned, so setup
    records ``uvx --from <git>`` instead of the cache path.
    """
    text = executable.replace("\\", "/").lower()
    if any(
        marker in text
        for marker in ("/.cache/uv/", "/caches/uv/", "/uv/cache/", "/uv/tools/")
    ):
        return True
    return "uv" in text and "archive-v" in text


def launcher_stem(path: str) -> str:
    """File name without ``.exe``, using either slash style.

    ``pathlib`` on Linux does not treat ``\\`` as a separator, so a
    Windows ``uv.exe`` path has to be split by hand.
    """
    name = path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    if name.lower().endswith(".exe"):
        name = name[:-4]
    return name.lower()


def choose_launcher(
    kind: str,
    *,
    executable: str,
    uvx: str | None,
    in_ephemeral_env: bool,
) -> tuple[str, list[str]]:
    """Command the agent should run to start the stdio server."""
    if kind == "auto":
        kind = "uvx" if in_ephemeral_env and uvx else "python"
    if kind == "python":
        return executable, ["-m", "logisim_mcp"]
    if kind == "uvx":
        if not uvx:
            raise LookupError("uvx is not on PATH; install uv or pass --launcher python")
        if launcher_stem(uvx) == "uv":
            return uvx, ["tool", "run", "--from", GIT_FROM, "logisim-mcp"]
        return uvx, ["--from", GIT_FROM, "logisim-mcp"]
    raise ValueError(f"unknown launcher {kind!r}")


def claude_desktop_config(
    home: Path,
    platform: str,
    appdata: str | None,
    xdg_config: str | None,
) -> Path:
    if platform == "darwin":
        return home / "Library/Application Support/Claude/claude_desktop_config.json"
    if platform == "win32":
        root = Path(appdata) if appdata else home / "AppData/Roaming"
        return root / "Claude/claude_desktop_config.json"
    config_home = Path(xdg_config) if xdg_config else home / ".config"
    return config_home / "Claude/claude_desktop_config.json"


def client_config_path(client: str, home: Path) -> Path:
    if client == "cursor":
        return home / ".cursor" / "mcp.json"
    if client == "claude-code":
        return home / ".claude.json"
    if client == "claude-desktop":
        return claude_desktop_config(
            home,
            sys.platform,
            os.environ.get("APPDATA"),
            os.environ.get("XDG_CONFIG_HOME"),
        )
    raise ValueError(f"unknown client {client!r}")


def detected_clients(home: Path) -> list[str]:
    found: list[str] = []
    if (home / ".cursor").is_dir() or shutil.which("cursor"):
        found.append("cursor")
    desktop = client_config_path("claude-desktop", home)
    if desktop.is_file() or desktop.parent.is_dir():
        found.append("claude-desktop")
    if (home / ".claude.json").is_file() or (home / ".claude").is_dir() or shutil.which("claude"):
        found.append("claude-code")
    return found


def resolve_jar(explicit: Path | None) -> Path | None:
    if explicit is not None:
        return explicit.expanduser()
    env = os.environ.get("LOGISIM_JAR")
    if env:
        return Path(env).expanduser()
    default = Path(DEFAULT_LOGISIM_JAR)
    if default.is_file():
        return default
    return None


def merge_server(document: dict, entry: dict) -> dict:
    servers = document.get("mcpServers")
    if servers is None:
        document["mcpServers"] = {}
        servers = document["mcpServers"]
    if not isinstance(servers, dict):
        raise ValueError("mcpServers is not a JSON object")
    servers[SERVER_NAME] = entry
    return document


def load_config(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{path} is not strict JSON ({exc}). It was not modified."
        ) from exc
    if not isinstance(document, dict):
        raise ValueError(f"{path} must be a JSON object. It was not modified.")
    return document


def write_config(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        path.with_name(path.name + ".bak").write_bytes(path.read_bytes())
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def server_entry(command: str, args: list[str], jar: Path) -> dict:
    return {
        "command": command,
        "args": args,
        "env": {"LOGISIM_JAR": str(jar)},
    }


def format_plan(
    targets: list[tuple[str, Path]],
    command: str,
    args: list[str],
    jar: Path,
) -> str:
    lines = [
        "Register the logisim MCP server with:",
        f"  {command} {' '.join(args)}",
        f"  LOGISIM_JAR={jar}",
        "Configs:",
    ]
    for name, path in targets:
        lines.append(f"  {name}: {path}")
    lines.append("Restart the agent after this. It can then call the Logisim tools.")
    return "\n".join(lines)


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="logisim-mcp setup",
        description="Write this server into Cursor, Claude Desktop, or Claude Code.",
    )
    parser.add_argument(
        "--client",
        action="append",
        choices=CLIENTS,
        dest="clients",
        help="Agent to register. Repeat to select more than one. Default: ones found on this machine.",
    )
    parser.add_argument("--jar", type=Path, help="Logisim Evolution fat-jar. Must exist.")
    parser.add_argument(
        "--launcher",
        choices=("auto", "uvx", "python"),
        default="auto",
        help="How the agent starts the server. auto uses uvx from a uv install, otherwise this Python.",
    )
    parser.add_argument("--yes", action="store_true", help="Write without asking.")
    parser.add_argument("--dry-run", action="store_true", help="Print the plan and write nothing.")
    parser.add_argument("--home", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    home = (args.home or Path.home()).expanduser()
    jar = resolve_jar(args.jar)
    if jar is None:
        if not sys.stdin.isatty() or args.yes or args.dry_run:
            print(
                "Pass --jar /path/to/logisim-evolution-5.0.0-all.jar",
                file=sys.stderr,
            )
            return 2
        typed = input("Path to logisim-evolution-5.0.0-all.jar: ").strip()
        jar = Path(typed).expanduser() if typed else None
    if jar is None or not jar.is_file():
        print(f"Logisim jar not found: {jar}", file=sys.stderr)
        return 2
    jar = jar.resolve()

    names = list(args.clients) if args.clients else detected_clients(home)
    if not names:
        names = ["cursor"]
        print("No agent config was found; Cursor will be registered.", file=sys.stderr)
    targets = [(name, client_config_path(name, home)) for name in names]

    try:
        command, launch_args = choose_launcher(
            args.launcher,
            executable=sys.executable,
            uvx=shutil.which("uvx") or shutil.which("uv"),
            in_ephemeral_env=running_from_uv(sys.executable),
        )
    except LookupError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(format_plan(targets, command, launch_args, jar))
    if args.dry_run:
        return 0
    if not args.yes:
        if not sys.stdin.isatty():
            print("Re-run with --yes to write these files.", file=sys.stderr)
            return 2
        answer = input("Write these configs? [Y/n] ").strip().lower()
        if answer not in ("", "y", "yes"):
            print("Not written.")
            return 0

    entry = server_entry(command, launch_args, jar)
    prepared: list[tuple[Path, dict]] = []
    for _name, path in targets:
        try:
            prepared.append((path, merge_server(load_config(path), entry)))
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    for path, document in prepared:
        write_config(path, document)
        print(f"Wrote {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    return run(argv)
