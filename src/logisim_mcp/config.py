"""Runtime configuration for the Logisim MCP server."""

from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

DEFAULT_LOGISIM_JAR = "/Applications/Logisim-evolution.app/Contents/app/logisim-evolution-5.0.0-all.jar"
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


_JAVA_VERSION = re.compile(r'version "(?:1\.)?(\d+)')
_MIN_JAVA = 21


def parse_java_major(version_text: str) -> int | None:
    """Major version from ``java -version`` stderr. ``1.8`` is 8."""
    match = _JAVA_VERSION.search(version_text)
    if match is None:
        return None
    return int(match.group(1))


def _java_major(binary: str) -> int | None:
    try:
        proc = subprocess.run(
            [binary, "-version"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return parse_java_major(proc.stderr + proc.stdout)


def _java_candidates() -> list[str]:
    found: list[str] = []

    def add(path: str | None) -> None:
        if path and path not in found:
            found.append(path)

    add(os.environ.get("JAVA"))
    add(shutil.which("java"))
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        exe = ".exe" if os.name == "nt" else ""
        add(str(Path(java_home) / "bin" / f"java{exe}"))
        add(str(Path(java_home) / "bin" / "java"))

    home = Path.home()
    patterns = [
        str(home / "scoop/apps/openjdk*/current/bin/java.exe"),
        str(home / "scoop/apps/openjdk*/current/bin/java"),
        "/usr/lib/jvm/java-21*/bin/java",
        "/usr/lib/jvm/java-2[2-9]*/bin/java",
        "/opt/homebrew/opt/openjdk@21/bin/java",
        "/usr/local/opt/openjdk@21/bin/java",
        "/Library/Java/JavaVirtualMachines/jdk-21*/Contents/Home/bin/java",
        "/Library/Java/JavaVirtualMachines/temurin-21*/Contents/Home/bin/java",
        str(home / ".jdks/jbr-21*/bin/java"),
        str(home / "AppData/Local/Programs/Eclipse Adoptium/jdk-21*/bin/java.exe"),
    ]
    for env_name in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        root = os.environ.get(env_name)
        if not root:
            continue
        patterns.append(str(Path(root) / "Eclipse Adoptium/jdk-21*/bin/java.exe"))
        patterns.append(str(Path(root) / "Java/jdk-21*/bin/java.exe"))
        patterns.append(str(Path(root) / "JetBrains/jbr*/bin/java.exe"))
    for pattern in patterns:
        for match in sorted(glob.glob(pattern)):
            add(match)
    add("/usr/bin/java")
    return found


class JavaTooOld(RuntimeError):
    """No Java 21 or newer binary was found."""


def _resolve_java() -> str:
    """First Java binary whose major version is at least 21.

    Logisim Evolution 5.0.0 is class-file 65. ``java`` on PATH is often
    an older system install on Windows and macOS, so JAVA_HOME, Scoop,
    Adoptium, and JetBrains Runtime are checked after it. An older binary
    is not used as a fallback: that fails later as an opaque class-file
    error.
    """
    found: list[str] = []
    for candidate in _java_candidates():
        major = _java_major(candidate)
        if major is not None and major >= _MIN_JAVA:
            return candidate
        if major is not None:
            found.append(f"{candidate} (Java {major})")
    detail = ", ".join(found) if found else "no java binary reported a version"
    raise JavaTooOld(
        "Logisim Evolution 5.0.0 needs Java 21 or newer. "
        f"Found: {detail}. Set JAVA or JAVA_HOME to a Java 21+ install."
    )


def _javac_names() -> list[str]:
    """Windows JDK layout uses ``javac.exe`` even when ``java`` lacks ``.exe``."""
    return ["javac.exe", "javac"] if os.name == "nt" else ["javac"]


def resolve_javac(java_binary: str) -> str:
    """``javac`` beside ``java``, then ``JAVA_HOME``, then ``PATH``.

    A JRE-only install has ``java`` and not ``javac``. The helper classes
    cannot be compiled there, so the error names that instead of raising
    ``FileNotFoundError`` from a bare ``javac`` command. The selected Java
    binary is looked up on PATH and its symlinks resolved first, so a
    ``/usr/bin/java`` pointing at JDK 21 uses that JDK's compiler instead
    of an older ``/usr/bin/javac``.
    """
    located = shutil.which(java_binary) or java_binary
    java_path = Path(located).expanduser()
    try:
        java_path = java_path.resolve()
    except OSError:
        pass
    # JAVA_HOME candidates may be recorded as ``…/bin/java`` without ``.exe``
    # on Windows; still prefer ``javac.exe`` beside that binary over PATH.
    names = _javac_names()
    for name in names:
        sibling = java_path.with_name(name)
        if sibling.is_file():
            return str(sibling)
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        for name in names:
            candidate = Path(java_home) / "bin" / name
            if candidate.is_file():
                return str(candidate)
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    raise RuntimeError(
        "javac was not found next to the Java 21 binary or on PATH. "
        "Sequential simulation needs a JDK, not a JRE-only install."
    )


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
