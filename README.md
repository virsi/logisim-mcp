# logisim-mcp

<p align="center">
  <a href="https://boosty.to/virsi/donate">
    <img alt="Donate on Boosty" src="https://img.shields.io/badge/Boosty-Donate-f15f2c?style=for-the-badge&logo=boosty&logoColor=white">
  </a>
  <a href="https://yoomoney.ru/fundraise/1HOILVESO53.260514">
    <img alt="Donate via YooMoney" height="40" src=".github/assets/yoomoney.png">
  </a>
</p>

> If `logisim-mcp` saved you an evening of wiring NAND gates by hand,
> consider [supporting the project on Boosty](https://boosty.to/virsi/donate)
> or [donating via YooMoney](https://yoomoney.ru/fundraise/1HOILVESO53.260514) —
> it keeps the lights on and the builders coming.

[![tests](https://github.com/virsi/logisim-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/virsi/logisim-mcp/actions/workflows/ci.yml)
[![python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![license](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

MCP (Model Context Protocol) server for [Logisim Evolution](https://github.com/logisim-evolution/logisim-evolution) 5.0.
Lets a large language model design, edit and verify digital circuits in
the native `.circ` format **without ever opening the GUI**. Built for
students doing digital-logic labs with an AI assistant.

The server speaks stdio MCP. Tools fall into five groups:

| Group | Tools |
|---|---|
| **IO** | `create_circuit_file`, `read_circuit_file`, `list_circuits`, `add_subcircuit`, `rename_circuit`, `delete_circuit`, `set_main_circuit` |
| **Builder** (low-level) | `add_pin`, `add_gate`, `add_component`, `add_wire`, `connect`, `add_tunnel`, `remove_component` |
| **High-level** | `build_half_adder`, `build_full_adder`, `build_ripple_adder`, `build_mux`, `build_decoder`, `build_comparator`, `build_register`, `build_counter`, `build_from_truth_table` |
| **Simulation** | `run_test_vector`, `run_test_circuit`, `simulate_tty`, `verify_truth_table`, `simulate_sequential`, `convert_legacy_circ`, `count_components` |
| **Inspection** | `describe_circuit`, `describe_project`, `check_circuit_drc` |

## Requirements

- macOS / Linux / Windows
- Python ≥ 3.10
- Java ≥ 21 (`java` on `$PATH`, or `JAVA` / `JAVA_HOME`; Scoop, Adoptium, and JetBrains Runtime are scanned when the default `java` is older)
- Logisim Evolution 5.0 JAR — download the fat-jar from
  [logisim-evolution releases](https://github.com/logisim-evolution/logisim-evolution/releases),
  or install the macOS `.app` which ships the same jar at
  `/Applications/Logisim-evolution.app/Contents/app/logisim-evolution-5.0.0-all.jar`.

## Install

With [uv](https://docs.astral.sh/uv/) installed, register the server with Cursor, Claude Desktop, or Claude Code. You do not clone this repo. Setup asks where the Logisim jar is, shows the files it will write, and waits for a yes.

```bash
uvx --from git+https://github.com/virsi/logisim-mcp logisim-mcp setup
```

Restart the agent. It then has the tools (`describe_circuit`, `add_gate`, `check_circuit_drc`, `simulate_sequential`, and the rest). The config it writes looks like this:

```json
{
  "mcpServers": {
    "logisim": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/virsi/logisim-mcp", "logisim-mcp"],
      "env": {
        "LOGISIM_JAR": "/ABSOLUTE/PATH/TO/logisim-evolution-5.0.0-all.jar"
      }
    }
  }
}
```

From a checkout you already have, `.venv/bin/logisim-mcp setup` registers that venv's Python instead of `uvx`. `--client cursor` limits which agent is written. `--dry-run` prints the plan only.

If setup cannot see the agent, the same block goes in `~/.cursor/mcp.json`, Claude Desktop's `claude_desktop_config.json`, or Claude Code via `claude mcp add`.

## Work on the code

```bash
git clone https://github.com/virsi/logisim-mcp.git
cd logisim-mcp
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

```bash
.venv/bin/python -m logisim_mcp        # stdio server, what the agent launches
.venv/bin/python -m mcp dev .venv/bin/python -m logisim_mcp
```

## Environment

| Variable | Default | Purpose |
|---|---|---|
| `LOGISIM_JAR` | macOS app path | Path to the Logisim Evolution fat-JAR |
| `JAVA` | `which java` | Java executable to invoke |
| `LOGISIM_WORKDIR` | current dir | Working dir for subprocess calls |
| `LOGISIM_TIMEOUT_SEC` | `30` | Default subprocess timeout (clamped to ≤ 600) |
| `LOGISIM_LOCALE` | `en` | Forces stable English stdout |

## End-to-end example (what Claude does)

```
> Make a 1-bit full adder, put it in /tmp/lab.circ, then check it.

create_circuit_file("/tmp/lab.circ")
build_full_adder("/tmp/lab.circ")
verify_truth_table(
  "/tmp/lab.circ", "full_adder",
  inputs=["A","B","Cin"], outputs=["Sum","Cout"],
  rows=[ [a,b,c, (a+b+c)&1, (a+b+c)>>1]
         for a in (0,1) for b in (0,1) for c in (0,1) ],
)
→ {"ok": true, "passed": 8, "failed": 0}
```

## Tests

```bash
.venv/bin/pytest                # unit tests + Logisim end-to-end
```

End-to-end tests are auto-skipped when the Logisim JAR is missing, so
CI without Java still passes the structural part of the suite.

## Status of each builder

| Builder | Generates valid `.circ` | End-to-end verified |
|---|---|---|
| `build_half_adder` | yes | truth-table 4/4 passes |
| `build_full_adder` | yes | truth-table 8/8 passes |
| `build_ripple_adder` | yes | truth-table 7/7 passes (4-bit) |
| `build_mux` | yes | truth-table 8/8 passes (2-to-1) |
| `build_decoder` | yes | truth-table 4/4 passes (2-to-4) |
| `build_comparator` | yes | truth-table 16/16 passes (4-bit) |
| `build_from_truth_table` | yes | sequential rows (XOR, NAND, 6 minterms) |
| `build_register` | yes | sequential vector (clock driven in the rows) |
| `build_counter` | yes | structural (drive the clock the same way as a register) |

## Sequential circuits

`build_register` and `build_counter` emit schematics using Logisim's
`logisim_evolution` appearance. Port offsets match Logisim Evolution 5.0.0.

Logisim 4.1 and later, including 5.0.0, can check sequential circuits
from `--test-vector`. Add a `<set>` column and a `<seq>` column.
Rows that share a set and have `<seq>` greater than 0 run in that order
without a reset, so you drive the clock pin through its edges yourself.
`<seq>` 0 still resets before the row. `verify_truth_table` writes those
columns when you pass `sets` and `steps`:

```python
verify_truth_table(
    path, "register",
    inputs=["D", "Clk", "En", "Rst"], outputs=["Q"],
    rows=[
        ["0", "0", "1", "1", "0"],  # reset
        ["1", "0", "1", "0", "0"],  # D=1, clock still low
        ["1", "1", "1", "0", "1"],  # rising edge captures D
    ],
    sets=[1, 1, 1],
    steps=[1, 2, 3],
)
```

`<DC>` on an output always passes. `<float>` drives or expects
high-impedance.

`count_components` still opens the file through `--tty stats`. Exit
code 0 proves the schematic is structurally valid; the histogram reports
every component class (for example `Register=1, Pin=5`).

`simulate_sequential` drives the circuit on the helper's own thread.
It does not use `Simulator` or the Swing event thread. Pass `<tick>` as
an input name to run that many full clock cycles (`toggleClocks` twice
per cycle) after the other inputs settle. Outputs may be pins or LEDs,
matched by label. `verify_truth_table` is still the right tool when you
want Logisim's own vector checker and you can toggle a clock *pin*
yourself.

## Bus notation in `verify_truth_table`

When verifying multi-bit pins, include the width in the pin name with
the `[N]` suffix Logisim expects:

```python
verify_truth_table(path, "ripple_adder",
    inputs=["A[4]", "B[4]", "Cin"],
    outputs=["Sum[4]", "Cout"],
    rows=[...],
)
```

Without `[N]`, Logisim silently treats the pin as 1-bit and masks the
value to its low bit — your tests will pass for the wrong reasons.

## Security

The XML parser hard-rejects any `.circ` file containing a `DOCTYPE` or
custom `ENTITY` declaration, which neutralises XXE and billion-laughs
attacks. File size is capped at 25 MB before parsing. Every Java
subprocess runs with a clamped timeout (≤ 600 s) and arguments passed
as a list to `subprocess.run` (no `shell=True`). See
`tests/test_security.py` for the regression suite.

If you find a security issue please open a private GitHub Security
Advisory rather than a public issue.

## Known limitations

- A `Clock` component is not ticked by `verify_truth_table`. Drive a
  clock *pin* with `<set>` / `<seq>` rows, or use `simulate_sequential`
  with a `<tick>` column.
- Fan-out for combinational signals is implemented via tunnels — the
  result is electrically correct but the auto-layout is functional, not
  pretty.
- `build_from_truth_table` synthesizes sum-of-products only (no
  Quine–McCluskey minimization).
- `build_ripple_adder` uses the built-in `Adder` block, not chained
  full-adders.
- mini-CPU / RAM-loaded scenarios (`--load`) are not wrapped yet.
- Visual rendering (PNG/SVG) is out of scope; use `describe_circuit`.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). PRs welcome, in particular:

- Wrapping `--load`/`--save` for RAM image workflows.
- An SVG renderer for `.circ` files so the LLM can also "see" schematics.

## License

[MIT](LICENSE).
