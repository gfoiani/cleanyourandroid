"""A thin wrapper around the `adb` binary: pick the phone, run one shell command, take a screenshot.

Every tool in this folder talks to the phone through `Adb.shell`, one command per call. Chained
commands (`a; b`) are avoided on purpose: on some firmware the second one silently never runs.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

DEFAULT_TIMEOUT_S = 90
STATES_NEEDING_HELP = {
    "unauthorized": "the phone has not accepted this computer yet: unlock it and tap Allow on the "
                    "\"Allow USB debugging?\" prompt (tick \"Always allow from this computer\").",
    "offline": "the phone is connected but offline: unplug and replug the cable, or toggle USB debugging.",
    "no permissions": "this computer's USB permissions block adb (Linux: add a udev rule for the phone).",
}


class AdbError(RuntimeError):
    """The phone could not be reached or chosen. The message is written for the person, not a developer."""


@dataclass(frozen=True)
class ShellResult:
    rc: int
    out: str

    @property
    def ok(self) -> bool:
        return self.rc == 0


def parse_devices(text: str) -> tuple[tuple[str, str], ...]:
    """`adb devices -l` output -> ((serial, state), ...)."""
    found = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("List of devices", "*")):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        state = "no permissions" if parts[1] == "no" else parts[1]
        found.append((parts[0], state))
    return tuple(found)


def choose_device(devices: tuple[tuple[str, str], ...], serial: str | None) -> str:
    """The serial to use, or an AdbError that says what the person should do."""
    if serial:
        for found_serial, state in devices:
            if found_serial == serial:
                if state != "device":
                    raise AdbError(f"{serial}: {STATES_NEEDING_HELP.get(state, state)}")
                return serial
        raise AdbError(f"No phone with serial {serial} is connected (adb devices lists "
                       f"{', '.join(s for s, _ in devices) or 'nothing'}).")
    ready = [s for s, state in devices if state == "device"]
    if len(ready) > 1:
        raise AdbError("more than one phone is connected: set ANDROID_SERIAL to the one to use "
                       f"({', '.join(ready)}).")
    if ready:
        return ready[0]
    for found_serial, state in devices:
        raise AdbError(f"{found_serial}: {STATES_NEEDING_HELP.get(state, state)}")
    raise AdbError("No phone found. Connect it with a USB data cable, turn on USB debugging in "
                   "Developer options, and accept the prompt on the phone.")


def find_adb() -> str:
    """The adb binary: $ADB, then PATH, then the usual SDK folders."""
    candidates = [os.environ.get("ADB"), shutil.which("adb")]
    for sdk in (os.environ.get("ANDROID_HOME"), os.environ.get("ANDROID_SDK_ROOT"),
                str(Path.home() / "Library/Android/sdk"), str(Path.home() / "Android/Sdk")):
        if sdk:
            candidates.append(str(Path(sdk) / "platform-tools" / "adb"))
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return candidate
    raise AdbError("adb was not found. Install Android platform-tools "
                   "(macOS: `brew install android-platform-tools`) or set ADB to its path.")


class Adb:
    """One phone, reached through the adb binary."""

    def __init__(self, serial: str, adb_path: str, timeout: int = DEFAULT_TIMEOUT_S) -> None:
        self.serial = serial
        self._adb = adb_path
        self._timeout = timeout

    def _run(self, args: list[str], binary: bool = False) -> subprocess.CompletedProcess:
        try:
            return subprocess.run([self._adb, "-s", self.serial, *args], capture_output=True, check=False,
                                  timeout=self._timeout, text=not binary)
        except subprocess.TimeoutExpired as error:
            raise AdbError(f"the phone did not answer within {self._timeout}s ({' '.join(args)}); "
                           "check the cable and that the screen is unlocked.") from error

    def shell(self, command: str) -> ShellResult:
        done = self._run(["shell", command])
        if done.returncode != 0 and "device '" in done.stderr and "not found" in done.stderr:
            raise AdbError(f"the phone {self.serial} disconnected.")
        return ShellResult(done.returncode, done.stdout + done.stderr)

    def screenshot(self, destination: Path) -> int:
        """Save a PNG of the screen; returns its size in bytes (0 means the app blocks capture)."""
        done = self._run(["exec-out", "screencap", "-p"], binary=True)
        if done.returncode != 0:
            raise AdbError(f"screencap failed: {done.stderr.decode(errors='replace').strip()}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(done.stdout)
        return len(done.stdout)


def connect(serial: str | None = None) -> Adb:
    """The phone to work on: the one given, $ANDROID_SERIAL, or the only one connected."""
    adb_path = find_adb()
    listing = subprocess.run([adb_path, "devices", "-l"], capture_output=True, text=True, timeout=30, check=False)
    chosen = choose_device(parse_devices(listing.stdout), serial or os.environ.get("ANDROID_SERIAL"))
    return Adb(chosen, adb_path)
