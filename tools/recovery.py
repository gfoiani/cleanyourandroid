"""The recovery record: what each listed package looked like before this repo changed anything.

    ~/.cleanyourandroid/<serial>/<list name>-<hash of the list path>.json
    {
      "version": 1,
      "serial": "0a1b2c3d",
      "list": "/abs/path/work/my-phone.txt",
      "created": "2026-11-08T10:00:00Z",
      "packages": {"com.heytap.mcs": {"before": "enabled", "method": "disable"}}
    }

`before` is enabled, disabled, uninstalled or absent. `method` is how this repo changed it (disable or
uninstall), or null while it is unchanged. The first record wins: a retry after a half-applied run
must not record the broken state as the original, so later saves only add packages the record lacks.
It is written before the first change reaches the phone and after every single change, so a cable
pulled halfway leaves a record that still undoes everything that happened.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

VERSION = 1
STATES = ("enabled", "disabled", "uninstalled", "absent")
METHODS = (None, "disable", "uninstall")
PACKAGE_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+")


class RecoveryError(RuntimeError):
    """The record exists but cannot be used: nothing may change until a person looks at it."""


@dataclass(frozen=True)
class PackageRecord:
    before: str
    method: str | None = None


@dataclass(frozen=True)
class Record:
    serial: str
    list: str
    created: str
    packages: Mapping  # package -> PackageRecord; never mutated, replaced as a whole


def home() -> Path:
    return Path(os.environ.get("CLEANYOURANDROID_HOME") or Path.home() / ".cleanyourandroid")


def path_for(serial: str, list_path: Path | str, prefix: str = "") -> Path:
    """Per phone and per file: the same list name at two paths gets two records."""
    resolved = str(Path(list_path).resolve())
    digest = hashlib.sha256(resolved.encode()).hexdigest()[:10]
    safe_serial = re.sub(r"[^A-Za-z0-9._-]", "_", serial)
    return home() / safe_serial / f"{prefix}{Path(list_path).stem}-{digest}.json"


def _to_json(record: Record) -> str:
    return json.dumps({
        "version": VERSION, "serial": record.serial, "list": record.list, "created": record.created,
        "packages": {name: {"before": p.before, "method": p.method} for name, p in record.packages.items()},
    }, indent=2, sort_keys=False) + "\n"


def _from_json(text: str, where: Path) -> Record:
    try:
        data = json.loads(text)
        packages = {name: PackageRecord(entry["before"], entry["method"])
                    for name, entry in data["packages"].items()}
        record = Record(data["serial"], data["list"], data["created"], packages)
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        raise RecoveryError(f"cannot read the recovery record {where}: {error}") from error
    not_names = [n for n in packages if not PACKAGE_NAME_RE.fullmatch(n)]
    if not_names:
        raise RecoveryError(f"cannot read the recovery record {where}: not a package name: {not_names}")
    bad = [n for n, p in packages.items() if p.before not in STATES or p.method not in METHODS]
    if data.get("version") != VERSION or bad:
        raise RecoveryError(f"cannot read the recovery record {where}: unexpected content {bad or data.get('version')}")
    return record


def write_atomically(target: Path, text: str) -> None:
    """Flushed to disk before it replaces the old file: a crash right after a change must not leave an
    empty or stale record behind."""
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    with open(temporary, "w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, target)


def read_text(target: Path) -> str | None:
    """The record's text, or None when there is no record yet."""
    if not target.exists():
        return None
    try:
        return target.read_text(encoding="utf-8")
    except OSError as error:
        raise RecoveryError(f"cannot read the recovery record {target}: {error}") from error


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(record: Record) -> None:
    write_atomically(path_for(record.serial, record.list), _to_json(record))


def load(serial: str, list_path: Path | str) -> Record | None:
    target = path_for(serial, list_path)
    text = read_text(target)
    return None if text is None else _from_json(text, target)


def save(serial: str, list_path: Path | str, states: Mapping) -> Record:
    """Record `states` (package -> state) and return the record.

    A package this repo has changed (method set) keeps the state it had before: that is the way back.
    A package it has not changed takes its current state, so a package that appeared, or that the person
    switched on or off since the last run, is undone to what it is now, not to what it was then.
    """
    unknown = sorted(state for state in states.values() if state not in STATES)
    if unknown:
        raise RecoveryError(f"refusing to record unknown states: {unknown}")
    existing = load(serial, list_path)
    if existing is None:
        existing = Record(serial, str(Path(list_path).resolve()), now(), {})
    refreshed = {name: PackageRecord(state) for name, state in states.items()
                 if name not in existing.packages or existing.packages[name].method is None}
    record = replace(existing, packages={**existing.packages, **refreshed})
    if record != existing or not path_for(serial, list_path).exists():
        _write(record)
    return record


def with_method(record: Record, package: str, method: str | None) -> Record:
    """A copy of `record` noting how `package` was changed (None: not changed), written to disk first."""
    if method not in METHODS or package not in record.packages:
        raise RecoveryError(f"cannot note {method!r} for {package}: not in the record")
    updated = replace(record, packages={**record.packages,
                                        package: replace(record.packages[package], method=method)})
    _write(updated)
    return updated
