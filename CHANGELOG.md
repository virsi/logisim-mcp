# Changelog

All notable changes to this project will be documented here.
The format is loosely based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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

- Sequential simulation through `verify_truth_table` is only reliable
  for combinational circuits (Logisim CLI limitation).
- No PNG/SVG renderer; LLM "sees" circuits through `describe_circuit`.
- mini-CPU / RAM image flows not wrapped yet.
