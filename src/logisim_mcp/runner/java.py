"""Thin subprocess wrapper around ``java -jar logisim-evolution…``."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

from ..config import SETTINGS, resolve_javac


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


def apply_windows_prefs(cmd: list[str], prefs_classpath: str | None) -> list[str]:
    """Launch via ``-cp`` so an in-memory ``PreferencesFactory`` is visible.

    ``java -jar`` ignores ``-cp``, and Logisim 5.0.0 crashes in
    ``WindowsPreferences`` when the HKCU JavaSoft registry node cannot be
    opened. The factory is only injected on Windows.
    """
    if not prefs_classpath:
        return cmd
    java, flag, jar, *rest = cmd
    if flag != "-jar":
        return cmd
    return [
        java,
        "-Djava.util.prefs.PreferencesFactory=MemPreferencesFactory",
        "-cp",
        os.pathsep.join([prefs_classpath, jar]),
        "com.cburch.logisim.Main",
        *rest,
    ]


def _reject_diagonal_circs(args: list[str]) -> None:
    from ..circ.parser import diagonal_wire_messages

    for arg in args:
        path = Path(arg)
        if path.suffix.lower() != ".circ" or not path.is_file():
            continue
        bad = diagonal_wire_messages(path)
        if bad:
            listed = "; ".join(bad[:8])
            raise ValueError(
                "diagonal wires are not valid in Logisim; opening the file "
                f"headless hangs on an error dialog: {listed}"
            )


def _invoke(
    cmd: list[str],
    timeout: int | None = None,
    stdin: str | None = None,
) -> JavaResult:
    t = timeout if timeout is not None else SETTINGS.timeout_sec
    try:
        proc = subprocess.run(
            cmd,
            input=stdin,
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


_COMPILE_LOCK = threading.Lock()
# The in-memory preferences factory is shipped precompiled so ordinary
# Windows CLI calls work on a JRE, which has no javac. Regenerate it with:
#   javac --release 21 -d src/logisim_mcp/runner/classes \
#       src/logisim_mcp/runner/MemPreferencesFactory.java
_PREFS_CLASS_NAMES = (
    "MemPreferencesFactory.class",
    "MemPreferencesFactory$MemNode.class",
)
_PREFS_CLASSES_DIR = Path(__file__).resolve().parent / "classes"

# Top-level SeqTester plus nested classes javac emits for it. Omitting the
# nested files leaves a cache that loads SeqTester then fails with
# NoClassDefFoundError.
_HELPER_CLASS_NAMES = (
    "SeqTester.class",
    "SeqTester$QuietLoader.class",
    "SeqTester$Loaded.class",
)


def prefs_classes() -> Path:
    """Directory with the precompiled in-memory preferences factory."""
    missing = [
        name for name in _PREFS_CLASS_NAMES if not (_PREFS_CLASSES_DIR / name).is_file()
    ]
    if missing:
        raise RuntimeError(
            "packaged preferences factory is incomplete: " + ", ".join(missing)
        )
    return _PREFS_CLASSES_DIR


def helper_classes() -> Path:
    """Compile SeqTester once; sequential simulation still needs a JDK.

    A temp directory receives the compile so a failed or concurrent
    ``javac`` cannot leave a fresh ``SeqTester.class`` beside a missing
    nested class.
    """
    with _COMPILE_LOCK:
        src_dir = Path(__file__).resolve().parent
        sources = [src_dir / "SeqTester.java"]
        cache_root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
        out = cache_root / "logisim-mcp" / "classes"
        out.mkdir(parents=True, exist_ok=True)
        newest = max(source.stat().st_mtime for source in sources)
        cached = [out / name for name in _HELPER_CLASS_NAMES]
        if all(path.exists() and path.stat().st_mtime >= newest for path in cached):
            return out
        jar = _ensure_jar()
        javac = resolve_javac(SETTINGS.java_binary)
        stage = Path(tempfile.mkdtemp(prefix="classes-", dir=out))
        try:
            proc = subprocess.run(
                [
                    javac,
                    "--release",
                    "21",
                    "-cp",
                    str(jar),
                    "-d",
                    str(stage),
                    *[str(source) for source in sources],
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if proc.returncode != 0:
                raise RuntimeError(proc.stderr or proc.stdout or "javac failed")
            for name in _HELPER_CLASS_NAMES:
                if not (stage / name).is_file():
                    raise RuntimeError(f"javac did not write {name}")
            for produced in stage.glob("*.class"):
                dest = out / produced.name
                if dest.exists():
                    dest.unlink()
                os.replace(produced, dest)
        finally:
            shutil.rmtree(stage, ignore_errors=True)
        return out


def run_java(extra_args: list[str], timeout: int | None = None) -> JavaResult:
    """Invoke Logisim with the standard ``--no-splash --locale <…>`` prefix."""
    _ensure_jar()
    _reject_diagonal_circs(extra_args)
    cmd = SETTINGS.java_cmd(*extra_args)
    if sys.platform == "win32":
        cmd = apply_windows_prefs(cmd, str(prefs_classes()))
    return _invoke(cmd, timeout=timeout)


def run_seq_tester(
    args: list[str],
    stdin: str | None = None,
    timeout: int | None = None,
) -> JavaResult:
    """Run the headless ``SeqTester`` helper on the Logisim classpath."""
    _ensure_jar()
    _reject_diagonal_circs(args)
    classes = helper_classes()
    cmd = [SETTINGS.java_binary]
    classpath = [str(classes), str(SETTINGS.logisim_jar)]
    if sys.platform == "win32":
        cmd.append("-Djava.util.prefs.PreferencesFactory=MemPreferencesFactory")
        classpath.insert(0, str(prefs_classes()))
    cmd.extend(
        [
            "-cp",
            os.pathsep.join(classpath),
            "SeqTester",
            *args,
        ]
    )
    return _invoke(cmd, timeout=timeout, stdin=stdin)


def count_error_wires(path: str, circuit: str, timeout: int | None = None) -> int:
    """How many wires carry ``Value.ERROR`` after one synchronous propagate."""
    res = run_seq_tester(["--error-wires", path, circuit], timeout=timeout)
    if not res.ok:
        detail = (res.stderr or res.stdout).strip()
        raise RuntimeError(detail or f"SeqTester exited {res.exit_code}")
    for line in res.stdout.splitlines():
        if line.startswith("ERROR_WIRES="):
            return int(line.split("=", 1)[1])
    raise RuntimeError(res.stdout or "SeqTester did not report ERROR_WIRES")
