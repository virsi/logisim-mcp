# Contributing to logisim-mcp

Thanks for considering a contribution! This is a small, focused project
so the bar to merge is fairly straightforward.

## Setup

```bash
git clone https://github.com/virsi/logisim-mcp.git
cd logisim-mcp
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

For end-to-end tests you also need Java ≥ 17 and the Logisim Evolution
fat-jar. The default path is the macOS app bundle; override with
`LOGISIM_JAR=…` if you keep the jar elsewhere.

## Running the test suite

```bash
.venv/bin/pytest
```

Tests that need Logisim are auto-skipped if the jar isn't present, so a
clean clone passes on a machine with only Python installed. CI runs both
variants.

## Project layout

```
src/logisim_mcp/
├── __main__.py          # stdio entry point
├── server.py            # FastMCP instance, tool registration
├── config.py            # env-driven settings
├── circ/                # .circ XML model + parser + writer + library
└── tools/               # one module per MCP-tool group
    ├── io_tools.py
    ├── builder_tools.py
    ├── highlevel_tools.py
    ├── sim_tools.py
    └── describe_tools.py
tests/
└── …
```

When adding a tool:

1. Put the implementation in the matching `tools/*.py` module.
2. Decorate the entry function with `@mcp.tool()`.
3. Add a test under `tests/`. End-to-end tests using Logisim go behind
   `requires_logisim`.

## Code style

- Python 3.10+ syntax (`X | Y` unions, `list[...]`).
- Type hints on every public function.
- No external runtime deps beyond `mcp` and `lxml` without discussion.
- Keep tool descriptions in docstrings short and concrete — they're
  surfaced to the LLM as tool metadata.

## Security

- Never use `shell=True` with `subprocess`.
- The XML parser must reject any `.circ` containing a `DOCTYPE` or
  custom `ENTITY` declaration (see `circ/parser.py`).
- Subprocess calls must specify a `timeout` directly or via `Settings`.
- See `tests/test_security.py` for the existing regression suite.

## Reverse-engineering Logisim coordinates

Several builders depend on exact port offsets for Logisim components.
The proven workflow:

1. Decompile the relevant class:
   `javap -p -c com.cburch.logisim.std.<group>.<Component>`
2. Find the `configurePorts` / `updatePorts` / `getInputOffset` method.
3. Translate the `new Port(dx, dy, …)` calls into `PortSpec` entries in
   `src/logisim_mcp/circ/library.py`.
4. Verify with a small probe program (see git history for examples).

This is how the gate, mux, decoder, adder, comparator, register and
counter port maps were obtained — please follow the same pattern for
new components.

## Pull requests

- One feature/fix per PR.
- Include a test that fails without your change.
- Run `pytest` locally before opening.
- For larger changes (new builders, new sim modes) please open an issue
  first so we can agree on scope.

By submitting a PR you agree your contribution is licensed under the
project's MIT license.
