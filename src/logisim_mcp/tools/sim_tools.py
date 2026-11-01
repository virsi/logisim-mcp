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

from ..runner.java import run_java, run_seq_tester
from ..server import mcp


# ---------- run_test_vector --------------------------------------------------

_RE_VECTOR_TOTAL = re.compile(r"^Passed:\s*(\d+)\s*,\s*Failed:\s*(\d+)", re.MULTILINE)
_RE_VECTOR_HEADER = re.compile(r"^Error on test vector\s+(\d+):\s*$", re.MULTILINE)
_RE_VECTOR_DETAIL = re.compile(
    r"^\s+(?P<signal>\S+)\s*=\s*(?P<actual>\S+)\s*\(expected\s+(?P<expected>\S+)\)\s*$"
)


_RE_VECTOR_LOAD_ERROR = re.compile(
    r"Error loading test vector|Circuit '[^']*' not found"
)


def _parse_test_vector_output(stdout: str) -> dict[str, Any]:
    """Convert ``--test-vector`` stdout to a structured summary."""
    passed = failed = 0
    match = _RE_VECTOR_TOTAL.search(stdout)
    reported = match is not None
    if match:
        passed, failed = int(match.group(1)), int(match.group(2))

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
    return {
        "passed": passed,
        "failed": failed,
        "failures": failures,
        "reported": reported,
    }


def vector_succeeded(summary: dict[str, Any], stdout: str, stderr: str, exit_ok: bool) -> bool:
    """True only when Logisim actually ran at least one vector row.

    A missing circuit or a vector that fails to load still exits 0 and
    prints no ``Passed:`` line. Treating that as success hides a typo.
    """
    text = f"{stdout}\n{stderr}"
    if _RE_VECTOR_LOAD_ERROR.search(text):
        return False
    ran = bool(summary.get("reported")) and summary["passed"] + summary["failed"] > 0
    return exit_ok and ran and summary["failed"] == 0


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
    summary["ok"] = vector_succeeded(summary, res.stdout, res.stderr, res.ok)
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

# Names accepted by Logisim Evolution 5.0.0's ``--tty``. ``bin`` and
# ``tabbed`` are older names this server used; they map onto the real ones.
_TTY_FORMATS = {
    "table",
    "tty",
    "halt",
    "speed",
    "stats",
    "binary",
    "hex",
    "csv",
    "tabs",
    "bin",
    "tabbed",
}
_TTY_ALIASES = {"bin": "binary", "tabbed": "tabs"}


@mcp.tool()
def simulate_tty(
    path: str,
    format: str = "table",
    toplevel_circuit: str | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    """Run a circuit headless via ``--tty <format>``.

    Formats: ``table``, ``tty``, ``halt``, ``speed``, ``stats``,
    ``binary``, ``hex``, ``csv``, ``tabs``. ``bin`` and ``tabbed`` are
    accepted as aliases. Table output in 5.0.0 includes bit widths in
    the header when a pin is wider than one bit.

    The circuit must contain a ``TTY`` component (from ``#I/O``) for the
    interactive ``tty`` format, or a ``Halt`` component for tests. For
    purely combinational checks you typically want ``format='table'``.
    """
    if format not in _TTY_FORMATS:
        raise ValueError(
            f"unknown tty format {format!r}; allowed: {sorted(_TTY_FORMATS - _TTY_ALIASES.keys())}"
        )
    args = ["--tty", _TTY_ALIASES.get(format, format)]
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


def format_truth_table(
    inputs: list[str],
    outputs: list[str],
    rows: list[list[str]],
    sets: list[int] | None = None,
    steps: list[int] | None = None,
) -> str:
    """Build a Logisim ``.vec`` document.

    ``sets`` and ``steps`` add the 4.1+ ``<set>`` / ``<seq>`` columns.
    Rows that share a set and have a step greater than 0 run in step
    order without a reset, so a clock pin can be walked through edges.
    Step 0 resets before the row (combinational). Omit both arguments
    for the classic one-row-one-reset format.
    """
    if (sets is None) != (steps is None):
        raise ValueError("sets and steps must be given together")
    if sets is not None and steps is not None:
        if len(sets) != len(rows) or len(steps) != len(rows):
            raise ValueError("sets and steps must have one entry per row")

    expected_cols = len(inputs) + len(outputs)
    for i, row in enumerate(rows):
        if len(row) != expected_cols:
            raise ValueError(
                f"row {i} has {len(row)} values; expected {expected_cols} "
                f"({len(inputs)} inputs + {len(outputs)} outputs)"
            )

    header_cols = list(inputs) + list(outputs)
    body_rows = [list(row) for row in rows]
    if sets is not None and steps is not None:
        header_cols.extend(["<set>", "<seq>"])
        for row, set_id, step in zip(body_rows, sets, steps):
            row.extend([str(set_id), str(step)])
    header = " ".join(header_cols)
    body = "\n".join(" ".join(row) for row in body_rows)
    return f"{header}\n{body}\n"


@mcp.tool()
def verify_truth_table(
    path: str,
    circuit: str,
    inputs: list[str],
    outputs: list[str],
    rows: list[list[str]],
    timeout: int = 60,
    sets: list[int] | None = None,
    steps: list[int] | None = None,
) -> dict[str, Any]:
    """Verify a circuit against an inline truth table.

    Args mirror what an LLM would naturally pass: lists of pin names and
    rows of values. Internally we write a temporary ``.vec`` file and
    delegate to :func:`run_test_vector`.

    Each row must be ``len(inputs) + len(outputs)`` items: input values
    first (the values to drive), then expected output values. ``"x"``
    means don't-care. ``<DC>`` on an output always passes; ``<float>``
    drives or expects high-impedance.

    Pass ``sets`` and ``steps`` to test sequential circuits on Logisim
    Evolution 4.1 or newer. Drive the clock pin yourself: a row with
    clock 0 followed by a row with clock 1, both in the same set and
    with steps 1, 2, …, is one rising edge. The circuit is not reset
    between those rows.
    """
    vec_text = format_truth_table(inputs, outputs, rows, sets, steps)

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


@mcp.tool()
def simulate_sequential(
    path: str,
    circuit: str,
    inputs: list[str],
    outputs: list[str],
    rows: list[list[str]],
    timeout: int = 30,
) -> dict[str, Any]:
    """Drive a circuit on this thread and read pins or LEDs after each row.

    Unlike ``verify_truth_table``, this does not use ``--test-vector``.
    It binds ``CircuitState`` to the helper process and steps
    ``Propagator`` directly, which is what actually ticks a ``Clock``
    component. Name an input ``<tick>`` to run that many common clock
    superperiods after the other inputs are applied. One superperiod is
    the LCM of every configured clock's high+low period; a lone clock
    therefore runs exactly that many complete high/low cycles. ``rows``
    are whitespace-separated values: inputs, then the expected outputs.

    Values may be decimal, ``0x`` hex, or ``0b`` binary, and must fit
    the pin width. An output cell of ``x``, ``-``, or ``<DC>`` is not
    checked. Outputs must be output pins or LEDs; an input pin listed
    as an output is an error.
    """
    stdin = "\n".join(" ".join(str(cell) for cell in row) for row in rows) + "\n"
    res = run_seq_tester(
        [str(path), circuit, ",".join(inputs), ",".join(outputs)],
        stdin=stdin,
        timeout=timeout,
    )
    passed = failed = 0
    for line in res.stdout.splitlines():
        if line.startswith("PASSED="):
            passed = int(line.split("=", 1)[1])
        elif line.startswith("FAILED="):
            failed = int(line.split("=", 1)[1])
    return {
        "ok": bool(rows)
        and res.ok
        and failed == 0
        and passed == len(rows),
        "passed": passed,
        "failed": failed,
        "exit_code": res.exit_code,
        "stdout": res.stdout,
        "stderr": res.stderr,
    }


# Component names may contain spaces ("AND Gate"). The library is the
# last token. TOTAL summary lines are matched exactly so a component such
# as "TotalAdder" is not mistaken for one.
_RE_STATS_ROW = re.compile(r"^\s*(\d+)\s+(\d+)\s+(.+?)\s+(\S+)\s*$")
_RE_STATS_TOTAL = re.compile(
    r"^\s*(\d+)\s+(\d+)\s+TOTAL\s+\((?:without|with)\b.*\)\s*$",
    re.IGNORECASE,
)


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
        if m:
            if "without" in line.lower():
                total = int(m.group(1))
            continue
        m = _RE_STATS_ROW.match(line)
        if m:
            count, _unique, name, _lib = m.groups()
            components[name.strip()] = int(count)
    return {
        "ok": res.ok,
        "exit_code": res.exit_code,
        "components": components,
        "total": total,
        "stdout": res.stdout,
        "stderr": res.stderr,
    }
