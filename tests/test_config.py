import os

import pytest

from logisim_mcp.config import JavaTooOld, _resolve_java, parse_java_major, resolve_javac
from logisim_mcp.runner.java import apply_windows_prefs


def test_parse_java_major_treats_1_8_as_8() -> None:
    assert parse_java_major('openjdk version "21.0.2" 2024-01-16') == 21
    assert parse_java_major('java version "1.8.0_391"') == 8
    assert parse_java_major("no version here") is None


def test_resolve_java_refuses_an_older_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "logisim_mcp.config._java_candidates",
        lambda: ["/opt/java8/bin/java"],
    )
    monkeypatch.setattr("logisim_mcp.config._java_major", lambda _binary: 8)
    with pytest.raises(JavaTooOld, match="Java 21"):
        _resolve_java()


def test_javac_is_taken_from_the_java_directory(tmp_path) -> None:
    java = tmp_path / "java"
    javac = tmp_path / "javac"
    java.write_text("#!/bin/sh\n", encoding="utf-8")
    javac.write_text("#!/bin/sh\n", encoding="utf-8")
    assert resolve_javac(str(java)) == str(javac)


@pytest.mark.skipif(os.name == "nt", reason="symlink creation needs extra privileges")
def test_javac_follows_a_java_symlink_to_the_jdk(tmp_path) -> None:
    jdk_bin = tmp_path / "jdk21" / "bin"
    jdk_bin.mkdir(parents=True)
    target_java = jdk_bin / "java"
    target_javac = jdk_bin / "javac"
    target_java.write_text("#!/bin/sh\n", encoding="utf-8")
    target_javac.write_text("#!/bin/sh\n", encoding="utf-8")

    launcher_dir = tmp_path / "bin"
    launcher_dir.mkdir()
    launcher = launcher_dir / "java"
    launcher.symlink_to(target_java)
    old_javac = launcher_dir / "javac"
    old_javac.write_text("#!/bin/sh\n", encoding="utf-8")

    assert resolve_javac(str(launcher)) == str(target_javac)


def test_javac_looks_up_a_bare_java_on_path(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    jdk_bin = tmp_path / "jdk21" / "bin"
    jdk_bin.mkdir(parents=True)
    java = jdk_bin / "java"
    javac = jdk_bin / "javac"
    java.write_text("#!/bin/sh\n", encoding="utf-8")
    javac.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.delenv("JAVA_HOME", raising=False)
    monkeypatch.setattr(
        "logisim_mcp.config.shutil.which",
        lambda name: str(java) if name == "java" else None,
    )
    assert resolve_javac("java") == str(javac)


def test_windows_javac_exe_beside_java_without_exe(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """JAVA_HOME candidates may omit ``.exe``; still pick ``javac.exe``."""
    java = tmp_path / "java"
    javac = tmp_path / "javac.exe"
    java.write_text("x", encoding="utf-8")
    javac.write_text("x", encoding="utf-8")
    monkeypatch.setattr(
        "logisim_mcp.config._javac_names",
        lambda: ["javac.exe", "javac"],
    )
    monkeypatch.delenv("JAVA_HOME", raising=False)
    monkeypatch.setattr("logisim_mcp.config.shutil.which", lambda _name: None)
    assert resolve_javac(str(java)) == str(javac)


def test_missing_javac_names_the_jdk(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    java = tmp_path / "java"
    java.write_text("x", encoding="utf-8")
    monkeypatch.delenv("JAVA_HOME", raising=False)
    monkeypatch.setattr("logisim_mcp.config.shutil.which", lambda _name: None)
    with pytest.raises(RuntimeError, match="JDK"):
        resolve_javac(str(java))


def test_windows_prefs_launch_is_not_jar_mode() -> None:
    cmd = apply_windows_prefs(
        ["java", "-jar", "logisim.jar", "--no-splash", "--locale", "en"],
        "classes",
    )
    assert cmd[0] == "java"
    assert "-jar" not in cmd
    assert cmd[1] == "-Djava.util.prefs.PreferencesFactory=MemPreferencesFactory"
    assert "classes" in cmd[3]
    assert "logisim.jar" in cmd[3]
    assert cmd[4] == "com.cburch.logisim.Main"
    assert cmd[5:] == ["--no-splash", "--locale", "en"]
