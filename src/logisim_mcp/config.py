"""Runtime configuration for the Logisim MCP server."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

DEFAULT_LOGISIM_JAR = "/Applications/Logisim-evolution.app/Contents/app/logisim-evolution-4.0.0-all.jar"
DEFAULT_TIMEOUT_SEC = 30
MAX_TIMEOUT_SEC = 600
DEFAULT_LOCALE = "en"


@dataclass(frozen=True)
class Settings:
    logisim_jar: Path
    java_binary: str
    workdir: Path
    timeout_sec: int
    locale: str

    def java_cmd(self, *extra: str) -> list[str]:
        return [
            self.java_binary,
            "-jar",
            str(self.logisim_jar),
            "--no-splash",
            "--locale",
            self.locale,
            *extra,
        ]


def _resolve_workdir() -> Path:
    raw = os.environ.get("LOGISIM_WORKDIR")
    if raw:
        return Path(raw).expanduser().resolve()
    return Path.cwd().resolve()


def _resolve_java() -> str:
    java = os.environ.get("JAVA") or shutil.which("java") or "/usr/bin/java"
    return java


def load_settings() -> Settings:
    jar_path = Path(os.environ.get("LOGISIM_JAR", DEFAULT_LOGISIM_JAR)).expanduser()
    raw_timeout = int(os.environ.get("LOGISIM_TIMEOUT_SEC", DEFAULT_TIMEOUT_SEC))
    # Clamp to a safe upper bound so a hostile env var can't turn every
    # subprocess into an indefinite DoS sink.
    timeout = max(1, min(raw_timeout, MAX_TIMEOUT_SEC))
    locale = os.environ.get("LOGISIM_LOCALE", DEFAULT_LOCALE)
    return Settings(
        logisim_jar=jar_path,
        java_binary=_resolve_java(),
        workdir=_resolve_workdir(),
        timeout_sec=timeout,
        locale=locale,
    )


SETTINGS = load_settings()
