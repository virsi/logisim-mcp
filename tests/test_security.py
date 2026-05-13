"""Tests for the hardened XML parser and config clamps."""

from __future__ import annotations

from pathlib import Path

import pytest

from logisim_mcp.circ.parser import MAX_CIRC_BYTES, parse


def test_external_entity_is_rejected(tmp_path: Path) -> None:
    """A DOCTYPE referencing /etc/passwd must be refused before parsing."""
    secret = tmp_path / "secret.txt"
    secret.write_text("THIS_SHOULD_NOT_LEAK")
    malicious = tmp_path / "evil.circ"
    malicious.write_text(
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<!DOCTYPE project ['
        f'<!ENTITY exfil SYSTEM "file://{secret}">]>'
        '<project source="4.0.0" version="1.0">'
        '<lib desc="#Wiring" name="0"/>'
        '<main name="main"/>'
        '<circuit name="main"><a name="circuit" val="&exfil;"/></circuit>'
        "</project>",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="DOCTYPE"):
        parse(malicious)


def test_billion_laughs_rejected(tmp_path: Path) -> None:
    """An internal-entity bomb must be refused — DTD declarations are
    forbidden so the bomb never gets a chance to expand."""
    bomb_xml = (
        '<?xml version="1.0"?>'
        '<!DOCTYPE lolz ['
        '<!ENTITY lol "lol">'
        '<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">'
        ']>'
        '<project source="4.0.0" version="1.0">'
        '<circuit name="main"><a name="circuit" val="&lol2;"/></circuit>'
        "</project>"
    )
    bomb = tmp_path / "bomb.circ"
    bomb.write_text(bomb_xml, encoding="utf-8")
    with pytest.raises(ValueError, match="DOCTYPE"):
        parse(bomb)


def test_oversized_file_rejected(tmp_path: Path) -> None:
    big = tmp_path / "huge.circ"
    # Write a file just over the cap; content needn't be valid XML, the
    # size check fires first.
    big.write_bytes(b"<project>" + b"x" * (MAX_CIRC_BYTES + 10) + b"</project>")
    with pytest.raises(ValueError, match="too large"):
        parse(big)


def test_oversized_xml_string_rejected() -> None:
    with pytest.raises(ValueError, match="too large"):
        parse(b"<project>" + b"x" * (MAX_CIRC_BYTES + 10) + b"</project>")


def test_timeout_env_is_clamped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOGISIM_TIMEOUT_SEC", "99999")
    from logisim_mcp.config import MAX_TIMEOUT_SEC, load_settings

    s = load_settings()
    assert s.timeout_sec == MAX_TIMEOUT_SEC


def test_negative_timeout_env_is_clamped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOGISIM_TIMEOUT_SEC", "-100")
    from logisim_mcp.config import load_settings

    s = load_settings()
    assert s.timeout_sec >= 1
