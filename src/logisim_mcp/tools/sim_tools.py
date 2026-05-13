"""MCP tools that drive the Logisim CLI for simulation and verification.

All of these shell out to ``java -jar logisim-evolution…`` via
:mod:`logisim_mcp.runner.java`. The stdout / stderr / exit code is
parsed into a JSON-friendly structure so an LLM can reason about
test results without staring at raw CLI output.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Any

from ..runner.java import run_java
from ..server import mcp


# ---------- run_test_vector --------------------------------------------------

_RE_VECTOR_TOTAL = re.compile(r"^Passed:\s*(\d+)\s*,\s*Failed:\s*(\d+)", re.MULTILINE)
_RE_VECTOR_HEADER = re.compile(r"^Error on test vector\s+(\d+):\s*$", re.MULTILINE)
_RE_VECTOR_DETAIL = re.compile(
    r"^\s+(?P<signal>\S+)\s*=\s*(?P<actual>\S+)\s*\(expected\s+(?P<expected>\S+)\)\s*$"
)


def _parse_test_vector_output(stdout: str) -> dict[str, Any]:
    """Convert ``--test-vector`` stdout to a structured summary."""
    passed = failed = 0
    m = _RE_VECTOR_TOTAL.search(stdout)
    if m:
        passed, failed = int(m.group(1)), int(m.group(2))

    failures: list[dict[str, Any]] = []
    lines = stdout.splitlines()
    i = 0
    while i < len(lines):
        m = _RE_VECTOR_HEADER.match(lines[i])
        if m:
            row = int(m.group(1))
            details: list[dict[str, str]] = []
            j = i + 1
            while j < len(lines):
                dm = _RE_VECTOR_DETAIL.match(lines[j])
                if dm:
                    details.append(dm.groupdict())
                    j += 1
                else:
                    break
            failures.append({"row": row, "details": details})
            i = j
        else:
            i += 1
    return {"passed": passed, "failed": failed, "failures": failures}


@mcp.tool()
def run_test_vector(
    path: str,
    circuit: str,
    vector_path: str,
    timeout: int = 60,
) -> dict[str, Any]:
    """Run a Logisim test vector against a circuit.

    ``vector_path`` is a Logisim ``.vec`` file: first line is the header
    with pin labels (``[N]`` suffix for buses), subsequent lines are
    value rows (``0``, ``1``, ``0xFF``, ``x`` for don't-care).
    """
    res = run_java(
        ["--test-vector", circuit, str(vector_path), str(path)],
        timeout=timeout,
    )
    summary = _parse_test_vector_output(res.stdout)
    summary["exit_code"] = res.exit_code
    summary["stdout"] = res.stdout
    summary["stderr"] = res.stderr
    summary["ok"] = res.ok and summary["failed"] == 0
    return summary


# ---------- run_test_circuit -------------------------------------------------


@mcp.tool()
def run_test_circuit(path: str, timeout: int = 60) -> dict[str, Any]:
    """Run the test bench embedded inside a ``.circ`` (``--test-circuit``).

    Exit code 0 means the test bench reached its ``Halt`` (success); any
    other exit code means it failed.
    """
    res = run_java(["--test-circuit", str(path)], timeout=timeout)
    return {
        "ok": res.ok,
        "exit_code": res.exit_code,
        "stdout": res.stdout,
        "stderr": res.stderr,
    }


# ---------- simulate_tty -----------------------------------------------------

_TTY_FORMATS = {"table", "tty", "halt", "speed", "stats", "tabbed", "csv", "bin", "hex"}


@mcp.tool()
def simulate_tty(
    path: str,
    format: str = "table",
    toplevel_circuit: str | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    """Run a circuit headless via ``--tty <format>``.

    The circuit must contain a ``TTY`` component (from ``#I/O``) for the
    interactive ``tty`` format, or a ``Halt`` component for tests. For
    purely combinational checks you typically want ``format='table'``.
    """
    if format not in _TTY_FORMATS:
        raise ValueError(
            f"unknown tty format {format!r}; allowed: {sorted(_TTY_FORMATS)}"
        )
    args = ["--tty", format]
    if toplevel_circuit:
        args.extend(["--toplevel-circuit", toplevel_circuit])
    args.append(str(path))
    res = run_java(args, timeout=timeout)
    return {
        "ok": res.ok,
        "exit_code": res.exit_code,
        "raw": res.stdout,
        "stderr": res.stderr,
    }


# ---------- verify_truth_table ----------------------------------------------


@mcp.tool()
def verify_truth_table(
    path: str,
    circuit: str,
    inputs: list[str],
    outputs: list[str],
    rows: list[list[str]],
    timeout: int = 60,
) -> dict[str, Any]:
    """Verify a circuit against an inline truth table.

    Args mirror what an LLM would naturally pass: lists of pin names and
    rows of values. Internally we write a temporary ``.vec`` file and
    delegate to :func:`run_test_vector`.

    Each row must be ``len(inputs) + len(outputs)`` items: input values
    first (the values to drive), then expected output values. ``"x"``
    means don't-care.
    """
    expected_cols = len(inputs) + len(outputs)
    for i, row in enumerate(rows):
        if len(row) != expected_cols:
            raise ValueError(
                f"row {i} has {len(row)} values; expected {expected_cols} "
                f"({len(inputs)} inputs + {len(outputs)} outputs)"
            )

    header = " ".join(inputs + outputs)
    body = "\n".join(" ".join(row) for row in rows)
    vec_text = f"{header}\n{body}\n"

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".vec", delete=False, encoding="utf-8"
    ) as fh:
        fh.write(vec_text)
        vec_path = fh.name
    try:
        result = run_test_vector(path, circuit, vec_path, timeout=timeout)
    finally:
        Path(vec_path).unlink(missing_ok=True)

    result["vector"] = vec_text
    return result


# ---------- legacy conversion / HDL ----------------------------------------


@mcp.tool()
def convert_legacy_circ(
    input_path: str, output_path: str, timeout: int = 60
) -> dict[str, Any]:
    """Re-save an older ``.circ`` in the current Logisim Evolution format."""
    res = run_java(
        ["--new-file-format", str(input_path), str(output_path)],
        timeout=timeout,
    )
    return {
        "ok": res.ok,
        "exit_code": res.exit_code,
        "stdout": res.stdout,
        "stderr": res.stderr,
        "output_path": str(Path(output_path).resolve()),
    }


_RE_STATS_ROW = re.compile(r"^\s*(\d+)\s+(\d+)\s+(\S+)\s+(\S+)\s*$")
_RE_STATS_TOTAL = re.compile(r"^\s*(\d+)\s+(\d+)\s+TOTAL", re.IGNORECASE)


@mcp.tool()
def count_components(
    path: str, circuit: str | None = None, timeout: int = 30
) -> dict[str, Any]:
    """Open a ``.circ`` headless and return a component-class histogram.

    Wraps ``--tty stats`` — Logisim parses the file end-to-end, so exit
    code 0 also proves the schematic is structurally valid (no unknown
    libraries, no missing required attributes). Useful as a smoke test
    when end-to-end simulation isn't practical (e.g. sequential
    circuits).
    """
    args = ["--tty", "stats"]
    if circuit:
        args.extend(["--toplevel-circuit", circuit])
    args.append(str(path))
    res = run_java(args, timeout=timeout)
    components: dict[str, int] = {}
    total = 0
    for line in res.stdout.splitlines():
        m = _RE_STATS_TOTAL.match(line)
        if m and "without" in line.lower():
            total = int(m.group(1))
            continue
        m = _RE_STATS_ROW.match(line)
        if m:
            count, _unique, name, _lib = m.groups()
            components[name] = int(count)
    return {
        "ok": res.ok,
        "exit_code": res.exit_code,
        "components": components,
        "total": total,
        "stdout": res.stdout,
        "stderr": res.stderr,
    }
