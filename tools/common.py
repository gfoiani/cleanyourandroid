"""What every command-line tool shares: exit codes, error reporting and getting hold of the phone.

Exit codes, the same for every tool:
    0  done (or a dry run printed)
    1  it ran, and something needs a look: a refused package, drift, an unverified change
    2  it did not run: no phone, a list or record that cannot be used, a bad argument
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

import adb
import device
import guards
import listfile
import recovery

ROOT = Path(__file__).resolve().parent.parent
EXIT_OK = 0
EXIT_NEEDS_A_LOOK = 1
EXIT_NOT_RUN = 2
EXPECTED_ERRORS = (adb.AdbError, listfile.ListError, guards.GuardError, recovery.RecoveryError,
                   RuntimeError, OSError)


def err(message: str) -> None:
    print(message, file=sys.stderr)


def run(body: Callable[[], int]) -> int:
    """Run a tool's body; a known failure becomes a plain message and exit 2, never a traceback."""
    try:
        return body()
    except EXPECTED_ERRORS as error:
        err(f"stopped: {error}")
        return EXIT_NOT_RUN


def phone_or_connect(phone: device.Phone | None, serial: str | None = None) -> device.Phone:
    return phone if phone is not None else adb.connect(serial)


def select_groups(entries: tuple, groups: list | None) -> tuple:
    """Entries in the named groups (case ignored); an unknown name is an error, not an empty batch."""
    if not groups:
        return entries
    known = {e.group.lower(): e.group for e in entries}
    unknown = [g for g in groups if g.lower() not in known]
    if unknown:
        raise listfile.ListError(f"no group named {', '.join(map(repr, unknown))} in the list; "
                                 f"groups: {', '.join(sorted(set(known.values())))}")
    wanted = {g.lower() for g in groups}
    return tuple(e for e in entries if e.group.lower() in wanted)


def refuse_protected(entries: tuple, guard_set: tuple) -> bool:
    """True (and an explanation on stderr) when a list names a protected package."""
    blocked = guards.protected([e.package for e in entries], guard_set)
    if not blocked:
        return False
    err("refusing the list: it names packages this repo never touches (guards/*.txt):")
    for package, reason in blocked.items():
        err(f"  {package:<48} {reason}")
    err("Remove those lines from the list. There is no switch to override this.")
    return True
