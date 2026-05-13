from __future__ import annotations

from pathlib import Path

import pytest

from logisim_mcp.config import SETTINGS
from logisim_mcp.tools.sim_tools import (
    _parse_test_vector_output,
    run_test_vector,
    verify_truth_table,
)


requires_logisim = pytest.mark.skipif(
    not SETTINGS.logisim_jar.exists(),
    reason="Logisim JAR not installed",
)


def test_parse_vector_summary() -> None:
    text = (
        'Loading test vector "x".\n'
        "Running 4 vectors…\n"
        "1 \nError on test vector 1:\n  Sum = E (expected 0)\n"
        "2 3 4 \nPassed: 1, Failed: 3\n"
    )
    res = _parse_test_vector_output(text)
    assert res["passed"] == 1
    assert res["failed"] == 3
    assert res["failures"][0]["row"] == 1
    assert res["failures"][0]["details"][0]["signal"] == "Sum"
    assert res["failures"][0]["details"][0]["actual"] == "E"
    assert res["failures"][0]["details"][0]["expected"] == "0"


@requires_logisim
def test_run_test_vector_and_truth_table_against_fixture(fixtures_dir: Path) -> None:
    circ = fixtures_dir / "and_gate.circ"
    vec = fixtures_dir / "and_gate.vec"

    direct = run_test_vector(str(circ), "main", str(vec))
    assert direct["ok"] is True
    assert direct["passed"] == 4
    assert direct["failed"] == 0

    table = verify_truth_table(
        str(circ),
        "main",
        inputs=["A", "B"],
        outputs=["Y"],
        rows=[
            ["0", "0", "0"],
            ["0", "1", "0"],
            ["1", "0", "0"],
            ["1", "1", "1"],
        ],
    )
    assert table["ok"] is True
    assert table["passed"] == 4
