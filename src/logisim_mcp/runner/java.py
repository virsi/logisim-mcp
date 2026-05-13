"""Thin subprocess wrapper around ``java -jar logisim-evolution…``."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..config import SETTINGS


@dataclass
class JavaResult:
    args: list[str]
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


class LogisimNotFound(RuntimeError):
    """Raised when the Logisim JAR can't be located."""


def _ensure_jar() -> Path:
    jar = SETTINGS.logisim_jar
    if not jar.exists():
        raise LogisimNotFound(
            f"Logisim JAR not found at {jar}. "
            "Set LOGISIM_JAR env var to point to logisim-evolution-*.jar"
        )
    return jar


def run_java(extra_args: list[str], timeout: int | None = None) -> JavaResult:
    """Invoke Logisim with the standard ``--no-splash --locale <…>`` prefix."""
    _ensure_jar()
    cmd = SETTINGS.java_cmd(*extra_args)
    t = timeout if timeout is not None else SETTINGS.timeout_sec
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=t,
            cwd=SETTINGS.workdir,
        )
    except subprocess.TimeoutExpired as e:
        return JavaResult(
            args=cmd,
            exit_code=-1,
            stdout=e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or ""),
            stderr=(e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or ""))
            + f"\n[timed out after {t}s]",
            timed_out=True,
        )
    return JavaResult(
        args=cmd,
        exit_code=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )
