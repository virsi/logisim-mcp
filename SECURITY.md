# Security Policy

## Supported versions

The project is pre-1.0; only the latest `main` branch is supported.

## Reporting a vulnerability

Please **do not** open public GitHub issues for security problems.
Instead, use GitHub Security Advisories
(*Security → Report a vulnerability* on the repo) so the report stays
private until a fix is shipped.

A typical report includes:
- the version (commit SHA) you tested,
- a minimal `.circ` file or command that reproduces the issue,
- what you expected to happen vs. what happened,
- any suggested remediation.

We aim to acknowledge reports within 7 days and ship a fix within 30.

## Hardening that's already in place

- XML parser rejects any input containing a `DOCTYPE` or custom
  `ENTITY` declaration (mitigates XXE and billion-laughs).
- `.circ` files larger than 25 MB are refused before parsing.
- Every Logisim subprocess runs with a timeout. The
  `LOGISIM_TIMEOUT_SEC` env var is clamped to ≤ 600 seconds.
- All `subprocess.run` calls pass arguments as a list, never as a
  shell string (`shell=True` is not used anywhere in the codebase).
- Temporary `.vec` files use `tempfile.NamedTemporaryFile` (mode 0600,
  unpredictable names) and are unlinked in `finally`.

The regression tests for these properties live in
`tests/test_security.py`.

## Out of scope

This server is meant to be run locally as part of an LLM client
(Claude Desktop, Claude Code, etc.). Multi-user / network exposure is
not supported. Path-traversal "protection" is intentionally absent
because the LLM legitimately needs to read and write user-supplied
paths anywhere on disk; treat the server as having the same trust
level as your own shell.
