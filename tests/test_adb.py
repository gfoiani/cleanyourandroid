"""The adb wrapper, with subprocess replaced: what it runs and how it reports failures."""
import subprocess

import pytest

import adb
from adb import Adb, AdbError


class Done:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


def test_shell_runs_one_command_for_the_chosen_serial(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda args, **kw: calls.append(args) or Done(stdout="ok\n"))

    result = Adb("0a1b2c3d", "/bin/adb").shell("getprop ro.product.model")

    assert calls == [["/bin/adb", "-s", "0a1b2c3d", "shell", "getprop ro.product.model"]]
    assert result.ok and result.out == "ok\n"


def test_shell_turns_a_vanished_phone_into_a_readable_error(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: Done(1, "", "adb: device 'x' not found\n"))

    with pytest.raises(AdbError, match="disconnected"):
        Adb("x", "/bin/adb").shell("pm list packages")


def test_a_timeout_says_what_to_check(monkeypatch):
    def slow(*args, **kwargs):
        raise subprocess.TimeoutExpired("adb", 1)
    monkeypatch.setattr(subprocess, "run", slow)

    with pytest.raises(AdbError, match="unlocked"):
        Adb("x", "/bin/adb", timeout=1).shell("pm list packages")


def test_screenshot_writes_the_png(monkeypatch, tmp_path):
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: Done(stdout=b"\x89PNG", stderr=b""))

    size = Adb("x", "/bin/adb").screenshot(tmp_path / "shots" / "a.png")

    assert size == 4 and (tmp_path / "shots" / "a.png").read_bytes() == b"\x89PNG"


def test_screenshot_failure_is_an_error(monkeypatch, tmp_path):
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: Done(1, b"", b"no screen"))

    with pytest.raises(AdbError, match="no screen"):
        Adb("x", "/bin/adb").screenshot(tmp_path / "a.png")


def test_find_adb_prefers_the_adb_variable(monkeypatch, tmp_path):
    binary = tmp_path / "adb"
    binary.write_text("#!/bin/sh\n")
    binary.chmod(0o755)
    monkeypatch.setenv("ADB", str(binary))

    assert adb.find_adb() == str(binary)


def test_find_adb_explains_how_to_install(monkeypatch, tmp_path):
    for name in ("ADB", "ANDROID_HOME", "ANDROID_SDK_ROOT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(adb.shutil, "which", lambda name: None)
    monkeypatch.setattr(adb.Path, "home", lambda: tmp_path)

    with pytest.raises(AdbError, match="platform-tools"):
        adb.find_adb()


def test_connect_uses_android_serial(monkeypatch):
    monkeypatch.setattr(adb, "find_adb", lambda: "/bin/adb")
    monkeypatch.setenv("ANDROID_SERIAL", "b")
    listing = "List of devices attached\na\tdevice\nb\tdevice\n"
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: Done(stdout=listing))

    assert adb.connect().serial == "b"
