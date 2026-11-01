"""Thin subprocess wrapper around ``java -jar logisim-evolution…``."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

from ..config import SETTINGS, HelperUnavailable, resolve_javac


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

    candidates = list(args)
    if "--new-file-format" in args:
        # Only the input is parsed; an existing output file is overwritten.
        index = args.index("--new-file-format")
        candidates = args[index + 1 : index + 2]
    for arg in candidates:
        path = Path(arg).expanduser()
        if not path.is_absolute():
            path = SETTINGS.workdir / path
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


def _file_fingerprint(path: Path) -> str:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return f"{path.resolve()}:missing"
    return f"{path.resolve()}:{digest.hexdigest()}"


def _helper_cache_key(sources: list[Path], jar: Path) -> str:
    """Hash everything that changes the compiled helper classes.

    Source mtimes are not enough: a wheel can preserve old timestamps, and
    a different Logisim JAR can keep the same size and mtime. File content
    digests make both changes invalidate the cache.
    """
    digest = hashlib.sha256()
    digest.update(b"helper-build-2/javac --release 21\0")
    for source in sources:
        digest.update(source.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(source.read_bytes())
        digest.update(b"\0")
    digest.update(_file_fingerprint(jar).encode("utf-8"))
    digest.update(b"\0")
    return digest.hexdigest()[:20]


def _classes_complete(out: Path) -> bool:
    return all((out / name).is_file() for name in _HELPER_CLASS_NAMES)


def _publish_classes(stage: Path, out: Path) -> None:
    """Publish a fully compiled helper directory in one atomic rename.

    Several server processes may compile the same cache concurrently. A
    directory rename means readers never observe a half-published set of
    top-level and nested classes; the loser of the race simply uses the
    winner's complete directory.
    """
    try:
        os.replace(stage, out)
    except OSError:
        if not _classes_complete(out):
            raise


def helper_classes() -> Path:
    """Compile SeqTester once; sequential simulation still needs a JDK.

    Each source/JAR combination gets its own cache directory. A temp
    directory receives the compile, then one directory rename publishes
    the complete set so concurrent server processes cannot mix class files
    from different builds. The compiler is checked only on a cache miss,
    so a complete cache still works after the JDK is removed.
    """
    with _COMPILE_LOCK:
        src_dir = Path(__file__).resolve().parent
        sources = [src_dir / "SeqTester.java"]
        jar = _ensure_jar()
        cache_root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
        parent = cache_root / "logisim-mcp"
        parent.mkdir(parents=True, exist_ok=True)
        key = _helper_cache_key(sources, jar)
        out = parent / f"classes-{key}"
        if _classes_complete(out):
            return out
        javac = resolve_javac(SETTINGS.java_binary)
        stage = Path(tempfile.mkdtemp(prefix=f".classes-{key}-", dir=parent))
        try:
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
                    raise HelperUnavailable(
                        proc.stderr or proc.stdout or "javac failed"
                    )
                for name in _HELPER_CLASS_NAMES:
                    if not (stage / name).is_file():
                        raise HelperUnavailable(f"javac did not write {name}")
                _publish_classes(stage, out)
            except HelperUnavailable:
                raise
            except (OSError, subprocess.SubprocessError) as exc:
                raise HelperUnavailable(
                    f"could not build helper classes: {exc}"
                ) from exc
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
