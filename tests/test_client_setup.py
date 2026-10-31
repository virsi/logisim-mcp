from __future__ import annotations

import json
from pathlib import Path

import pytest

from logisim_mcp.client_setup import (
    choose_launcher,
    claude_desktop_config,
    merge_server,
    run,
    running_from_uv,
)


def test_uv_cache_is_ephemeral() -> None:
    assert running_from_uv("/home/user/.cache/uv/archive-v0/abc/bin/python")
    assert running_from_uv(r"C:\Users\user\AppData\Local\uv\cache\archive-v0\abc\python.exe")
    assert not running_from_uv("/home/user/logisim-mcp/.venv/bin/python")


def test_launcher_python_uses_this_interpreter() -> None:
    command, args = choose_launcher(
        "python",
        executable="/opt/venv/bin/python",
        uvx="/usr/bin/uvx",
        in_ephemeral_env=False,
    )
    assert command == "/opt/venv/bin/python"
    assert args == ["-m", "logisim_mcp"]


def test_launcher_uvx_does_not_bake_a_cache_path() -> None:
    command, args = choose_launcher(
        "auto",
        executable="/home/user/.cache/uv/archive-v0/x/bin/python",
        uvx="/usr/bin/uvx",
        in_ephemeral_env=True,
    )
    assert command == "/usr/bin/uvx"
    assert args[0] == "--from"
    assert args[-1] == "logisim-mcp"


def test_windows_uv_exe_uses_tool_run() -> None:
    command, args = choose_launcher(
        "uvx",
        executable=r"C:\Users\me\AppData\Local\Programs\Python\python.exe",
        uvx=r"C:\Users\me\AppData\Local\uv\uv.exe",
        in_ephemeral_env=False,
    )
    assert command.endswith("uv.exe")
    assert args[:3] == ["tool", "run", "--from"]


def test_uv_binary_uses_tool_run() -> None:
    command, args = choose_launcher(
        "uvx",
        executable="/usr/bin/python",
        uvx="/usr/bin/uv",
        in_ephemeral_env=False,
    )
    assert command == "/usr/bin/uv"
    assert args[:3] == ["tool", "run", "--from"]


def test_claude_desktop_paths() -> None:
    home = Path("/home/user")
    assert claude_desktop_config(home, "darwin", None, None) == (
        home / "Library/Application Support/Claude/claude_desktop_config.json"
    )
    windows = claude_desktop_config(home, "win32", r"C:\Users\user\AppData\Roaming", None)
    assert windows.name == "claude_desktop_config.json"
    assert windows.parent.name == "Claude"
    assert claude_desktop_config(home, "linux", None, None) == (
        home / ".config/Claude/claude_desktop_config.json"
    )


def test_merge_keeps_other_servers() -> None:
    document = merge_server(
        {"numStartups": 3, "mcpServers": {"other": {"command": "echo"}}},
        {"command": "python", "args": ["-m", "logisim_mcp"], "env": {"LOGISIM_JAR": "/jar"}},
    )
    assert document["numStartups"] == 3
    assert document["mcpServers"]["other"]["command"] == "echo"
    assert document["mcpServers"]["logisim"]["args"] == ["-m", "logisim_mcp"]


def test_setup_writes_cursor_config(tmp_path: Path) -> None:
    jar = tmp_path / "logisim-evolution-5.0.0-all.jar"
    jar.write_bytes(b"jar")
    existing = tmp_path / ".cursor" / "mcp.json"
    existing.parent.mkdir()
    existing.write_text(
        json.dumps({"mcpServers": {"other": {"command": "echo"}}}) + "\n",
        encoding="utf-8",
    )
    code = run(
        [
            "--yes",
            "--home",
            str(tmp_path),
            "--jar",
            str(jar),
            "--client",
            "cursor",
            "--launcher",
            "python",
        ]
    )
    assert code == 0
    written = json.loads(existing.read_text(encoding="utf-8"))
    assert written["mcpServers"]["other"]["command"] == "echo"
    logisim = written["mcpServers"]["logisim"]
    assert logisim["args"] == ["-m", "logisim_mcp"]
    assert logisim["env"]["LOGISIM_JAR"] == str(jar.resolve())
    assert existing.with_name("mcp.json.bak").is_file()


def test_dry_run_does_not_write(tmp_path: Path) -> None:
    jar = tmp_path / "logisim.jar"
    jar.write_bytes(b"jar")
    code = run(
        [
            "--dry-run",
            "--home",
            str(tmp_path),
            "--jar",
            str(jar),
            "--client",
            "cursor",
            "--launcher",
            "python",
        ]
    )
    assert code == 0
    assert not (tmp_path / ".cursor" / "mcp.json").exists()


def test_missing_jar_is_refused(tmp_path: Path) -> None:
    code = run(
        [
            "--yes",
            "--home",
            str(tmp_path),
            "--jar",
            str(tmp_path / "missing.jar"),
            "--client",
            "cursor",
        ]
    )
    assert code == 2
    assert not (tmp_path / ".cursor" / "mcp.json").exists()


def test_invalid_json_is_left_alone(tmp_path: Path) -> None:
    jar = tmp_path / "logisim.jar"
    jar.write_bytes(b"jar")
    config = tmp_path / ".cursor" / "mcp.json"
    config.parent.mkdir()
    original = '{ "mcpServers": {} } // comment\n'
    config.write_text(original, encoding="utf-8")
    code = run(
        [
            "--yes",
            "--home",
            str(tmp_path),
            "--jar",
            str(jar),
            "--client",
            "cursor",
            "--launcher",
            "python",
        ]
    )
    assert code == 2
    assert config.read_text(encoding="utf-8") == original


def test_mcp_servers_must_be_an_object() -> None:
    with pytest.raises(ValueError, match="mcpServers"):
        merge_server({"mcpServers": []}, {"command": "python"})
