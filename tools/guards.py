"""Packages no tool in this repo will disable or uninstall, whatever a list says.

The patterns live in guards/*.txt, one per line, with the reason as a trailing comment:

    com.android.phone            # calls, SMS and the SIM
    com.android.providers.*      # contacts, SMS, media and calendar data

Every file applies to every phone: a Samsung pattern never matches a OnePlus package, so there is
nothing to select. There is no switch to override a guard. A package that is wrongly protected is
fixed in the guard file, with a reason, in a reviewed change.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parent.parent
GUARD_DIR = ROOT / "guards"
# A bare name such as `android` or `oplus` is allowed here (framework packages), unlike in lists.
PATTERN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)*(\.\*|\*)?")


class GuardError(ValueError):
    """The guard files themselves are broken; nothing may run until they are fixed."""


class Guard(NamedTuple):
    pattern: str
    reason: str
    source: str

    def matches(self, package: str) -> bool:
        if self.pattern.endswith("*"):
            return package.startswith(self.pattern[:-1])
        return package == self.pattern


def _parse(path: Path) -> list:
    found = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        body, _, reason = raw.partition("#")
        pattern = body.strip()
        if not pattern:
            continue
        if not PATTERN_RE.fullmatch(pattern):
            raise GuardError(f"{path.name}:{number}: not a package pattern: {pattern!r}")
        found.append(Guard(pattern, reason.strip() or f"protected by {path.name}", str(path)))
    return found


def load(directory: Path | str = GUARD_DIR) -> tuple:
    files = sorted(Path(directory).glob("*.txt"))
    if not files:
        raise GuardError(f"no guard files in {directory}: refusing to work without them")
    return tuple(guard for path in files for guard in _parse(path))


def match(package: str, guard_set: Iterable[Guard]) -> Guard | None:
    for guard in guard_set:
        if guard.matches(package):
            return guard
    return None


def protected(packages: Iterable[str], guard_set: tuple) -> dict:
    """package -> reason, for the packages a guard covers, in the order given."""
    found = {}
    for package in packages:
        guard = match(package, guard_set)
        if guard is not None:
            found[package] = guard.reason
    return found
