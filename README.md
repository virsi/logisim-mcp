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

MCP (Model Context Protocol) server for [Logisim Evolution](https://github.com/logisim-evolution/logisim-evolution) 4.x.
Lets a large language model design, edit and verify digital circuits in
the native `.circ` format **without ever opening the GUI**. Built for
students doing digital-logic labs with an AI assistant.

The server speaks stdio MCP. Tools fall into five groups:

| Group | Tools |
|---|---|
| **IO** | `create_circuit_file`, `read_circuit_file`, `list_circuits`, `add_subcircuit`, `rename_circuit`, `delete_circuit`, `set_main_circuit` |
| **Builder** (low-level) | `add_pin`, `add_gate`, `add_component`, `add_wire`, `connect`, `add_tunnel`, `remove_component` |
| **High-level** | `build_half_adder`, `build_full_adder`, `build_ripple_adder`, `build_mux`, `build_decoder`, `build_comparator`, `build_register`, `build_counter`, `build_from_truth_table` |
| **Simulation** | `run_test_vector`, `run_test_circuit`, `simulate_tty`, `verify_truth_table`, `convert_legacy_circ`, `count_components` |
| **Inspection** | `describe_circuit`, `describe_project` |

## Requirements

- macOS / Linux
- Python ≥ 3.10
- Java ≥ 17 (`java` on `$PATH`)
- Logisim Evolution 4.x JAR — download the fat-jar from
  [logisim-evolution releases](https://github.com/logisim-evolution/logisim-evolution/releases),
  or install the macOS `.app` which ships the same jar at
  `/Applications/Logisim-evolution.app/Contents/app/logisim-evolution-4.0.0-all.jar`.

## Install

```bash
git clone https://github.com/virsi/logisim-mcp.git
cd logisim-mcp
python3 -m venv .venv
.venv/bin/pip install -e .
```

`pip install -e .[dev]` if you also want pytest.

## Try it

```bash
.venv/bin/python -m logisim_mcp        # starts the stdio server
```

Or hit it with the MCP inspector:

```bash
.venv/bin/python -m mcp dev .venv/bin/python -m logisim_mcp
```

## Connect to Claude Desktop

Add the following block to `~/Library/Application Support/Claude/claude_desktop_config.json`
(macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows), then restart Claude Desktop.

```json
{
  "mcpServers": {
    "logisim": {
      "command": "/ABSOLUTE/PATH/TO/logisim-mcp/.venv/bin/python",
      "args": ["-m", "logisim_mcp"],
      "env": {
        "LOGISIM_JAR": "/ABSOLUTE/PATH/TO/logisim-evolution-4.0.0-all.jar"
      }
    }
  }
}
```

## Connect to Claude Code

```bash
claude mcp add logisim \
  --scope user \
  --env LOGISIM_JAR=/ABSOLUTE/PATH/TO/logisim-evolution-4.0.0-all.jar \
  -- /ABSOLUTE/PATH/TO/logisim-mcp/.venv/bin/python -m logisim_mcp
```

Then `claude mcp list` should show `logisim: … - ✓ Connected`.

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
| `build_from_truth_table` | yes | structural |
| `build_register` | yes | structural (see *Sequential circuits* below) |
| `build_counter` | yes | structural (see *Sequential circuits* below) |

## Sequential circuits

`build_register` and `build_counter` emit schematics using Logisim's
`logisim_evolution` appearance with port offsets verified against the
Logisim source. End-to-end sequential verification via `--test-vector`
is limited by Logisim 4.0.0 itself: the CLI test runner samples a
steady-state per row and does not auto-tick the clock between rows.
The MCP server therefore exposes:

- `count_components` — opens the file through `--tty stats`. Exit code 0
  proves the schematic is structurally valid; the histogram reports every
  component class so the LLM can sanity-check what it built
  (e.g. `Register=1, Pin=5`).

A partially-working headless test runner (`SeqTester.java`) is included
under `src/logisim_mcp/runner/` for reference — it shows how one would
drive pins via the Logisim Java API. The current Simulator expects a
Swing event-dispatch thread that's awkward to provide in pure headless
mode, so simulation of generated circuits is best done by:

1. **The Logisim GUI**: open the `.circ`, then *Simulate → Reset
   Simulation* and *Simulate → Ticks Enabled* (or step manually with
   Ctrl-K).
2. **A self-checking testbench** inside the `.circ`: a `Clock` drives
   the register, expected outputs come from a ROM, a comparator drives
   a `Halt` element when a mismatch is found, and `run_test_circuit`
   (already wrapped) reports pass/fail.

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

- Sequential simulation through `verify_truth_table` is only reliable
  for purely combinational circuits.
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
- Adding a working headless sequential runner (`SeqTester` is a stub).
- An SVG renderer for `.circ` files so the LLM can also "see" schematics.

## License

[MIT](LICENSE).
