# Changelog

All notable changes to this project will be documented here.
The format is loosely based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- `logisim-mcp setup` registers the server with Cursor, Claude Desktop, or
  Claude Code. `uvx --from git+https://github.com/virsi/logisim-mcp logisim-mcp setup`
  does this without cloning the repo.
- `simulate_sequential` steps a circuit with `Propagator` on the calling
  thread, including `Clock` components (`<tick>`) and LED outputs.
- `check_circuit_drc` reports shorted nets, floating inputs, wires that
  pass across a pin, diagonal wires, and wires sitting at `Value.ERROR`.
- Discrete D, T, J-K, and S-R flip-flops, plus LED. Gate lookup honors
  `size` and `facing`.
- `route_l` tries the other elbow, then a dogleg, when a segment would
  hit another pin or overlap an existing wire.
- Java 21 is selected when `java` on `PATH` is older. On Windows the
  launcher uses an in-memory preferences factory so a locked-down
  registry cannot crash startup.

### Fixed

- `verify_truth_table` and `run_test_vector` fail when Logisim exits 0
  without running any rows, including a missing circuit or a vector that
  does not load.
- `build_from_truth_table` no longer shorts minterms together or drops
  terms past the fifth OR input. A 3-input gate at the default size uses
  Logisim's 20px input spacing. Bus tunnels on the mux, decoder, and
  comparator carry the pin width, so a multi-bit select or data net is
  not left unknown. The magnitude comparator is unsigned; Logisim's
  built-in default is two's complement.
- Plexer ports follow `size`, `selloc`, `enable`, and facing. Classic
  Register and Counter use their classic port map. A decoder that omits
  `enable` keeps the enable pin.
- `route_l` raises when every path is blocked. `auto_place` stays off
  existing wires. Duplicate wires keep an attribute that only one copy had.
- Java older than 21 is refused. `javac` is taken from the same JDK.
  `simulate_sequential` accepts `0x` and `0b`, rejects values that do not
  fit the pin, and will not treat an input pin as an output.
- `logisim-mcp setup` writes `uv tool run` when the launcher is `uv.exe`.

### Changed

- Target Logisim Evolution 5.0.0. New files are stamped `source="5.0.0"`.
- Counter, multiplexer, demultiplexer, and decoder port maps follow the
  5.0.0 component geometry. Wide counters use the grouped-row height.
- NOT gates are saved with `size="30"` (the wide option). `size="50"`
  is rejected by Logisim and the gate is dropped on load. Buffers no
  longer carry a `size` attribute they do not have.
- `verify_truth_table` accepts `sets` and `steps`, which become the
  `<set>` and `<seq>` columns added for sequential vectors in 4.1.
- `--tty` format names match the 5.0.0 CLI (`binary`, `tabs`). `bin`
  and `tabbed` still work as aliases.
- Wire attributes such as `buswidthpos` survive a parse/write round-trip.
- `count_components` keeps multi-word class names (`AND Gate`).
- Depend on `mcp` 1.x. The 2.x package renamed `FastMCP` and does not
  import here.
- New projects list the libraries a 5.0.0 save uses. Output pins are
  recognized from `type="output"` as well as `output="true"`. Diagonal
  wires are refused before Java starts, because Logisim reports them
  with a dialog that would hang a headless run.

## [0.1.0] — Initial public release

### Added

- 30 MCP tools across five groups: IO, Builder, High-level, Simulation,
  Inspection.
- High-level builders for half-adder, full-adder, ripple-adder, mux,
  decoder, comparator, register, counter, and arbitrary truth-table SOP
  synthesis.
- End-to-end verification through Logisim Evolution's `--test-vector`
  CLI for combinational circuits.
- `count_components` structural check via `--tty stats`.
- `describe_circuit` text netlist (union-find over wires + tunnels).
- Hardened XML parsing: `DOCTYPE`/`ENTITY` rejection, 25 MB size cap.
- Subprocess timeout clamp (≤ 600 s).
- Test suite with 41 cases, including a security regression module.

### Known limitations

- A `Clock` component is not ticked by `verify_truth_table`. Drive a
  clock pin with `sets` / `steps`, or use `run_test_circuit`.
- No PNG/SVG renderer; LLM "sees" circuits through `describe_circuit`.
- mini-CPU / RAM image flows not wrapped yet.
