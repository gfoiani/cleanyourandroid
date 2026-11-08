"""The settings record: the value each setting had before tune.py changed it.

    ~/.cleanyourandroid/<serial>/tweaks-<file name>-<hash of the file path>.json
    {
      "version": 1,
      "serial": "0a1b2c3d",
      "file": "/abs/path/tweaks/power.txt",
      "created": "2026-11-08T10:00:00Z",
      "settings": {"system/screen_off_timeout": {"before": "60000", "applied": "30000"}}
    }

`before` is the value the phone had, or null when the setting was not set (restore deletes it then).
`applied` is the value this repo wrote, or null while it has not changed the setting. Like the package
record, a changed setting keeps its first `before`, and the intent is written before each command.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path

import recovery
import tweakfile
from recovery import RecoveryError

VERSION = 1
PREFIX = "tweaks-"


@dataclass(frozen=True)
class SettingRecord:
    before: str | None
    applied: str | None = None


@dataclass(frozen=True)
class Record:
    serial: str
    file: str
    created: str
    settings: Mapping  # "namespace/key" -> SettingRecord; never mutated, replaced as a whole


def path_for(serial: str, file: Path | str) -> Path:
    return recovery.path_for(serial, file, prefix=PREFIX)


def valid_value(value: str | None) -> bool:
    return value is None or bool(tweakfile.VALUE_RE.fullmatch(value))


def valid_name(name: str) -> bool:
    namespace, _, key = name.partition("/")
    return namespace in tweakfile.NAMESPACES and bool(tweakfile.KEY_RE.fullmatch(key))


def _to_json(record: Record) -> str:
    return json.dumps({
        "version": VERSION, "serial": record.serial, "file": record.file, "created": record.created,
        "settings": {name: {"before": s.before, "applied": s.applied} for name, s in record.settings.items()},
    }, indent=2) + "\n"


def _from_json(text: str, where: Path) -> Record:
    try:
        data = json.loads(text)
        settings = {name: SettingRecord(entry["before"], entry["applied"])
                    for name, entry in data["settings"].items()}
        record = Record(data["serial"], data["file"], data["created"], settings)
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        raise RecoveryError(f"cannot read the settings record {where}: {error}") from error
    bad = [n for n, s in settings.items()
           if not valid_name(n) or not valid_value(s.before) or not valid_value(s.applied)]
    if data.get("version") != VERSION or bad:
        raise RecoveryError(f"cannot read the settings record {where}: unexpected content {bad or data.get('version')}")
    return record


def _write(record: Record) -> None:
    recovery.write_atomically(path_for(record.serial, record.file), _to_json(record))


def load(serial: str, file: Path | str) -> Record | None:
    target = path_for(serial, file)
    text = recovery.read_text(target)
    return None if text is None else _from_json(text, target)


def save(serial: str, file: Path | str, values: Mapping) -> Record:
    """Record `values` ("namespace/key" -> current value or None) and return the record.

    A setting this repo has changed, and that still has the value it wrote, keeps the value it had
    before. The others take their current value: also one the person changed since, so a later restore
    puts back their choice, not the value from before their change.
    """
    bad = sorted(n for n, v in values.items() if not valid_name(n) or not valid_value(v))
    if bad:
        raise RecoveryError(f"refusing to record values that could not be put back: {bad}")
    existing = load(serial, file)
    if existing is None:
        existing = Record(serial, str(Path(file).resolve()), recovery.now(), {})
    refreshed = {name: SettingRecord(value) for name, value in values.items()
                 if name not in existing.settings
                 or not tweakfile.same(value, existing.settings[name].applied)}
    record = replace(existing, settings={**existing.settings, **refreshed})
    if record != existing or not path_for(serial, file).exists():
        _write(record)
    return record


def with_applied(record: Record, name: str, applied: str | None) -> Record:
    """A copy of `record` noting the value this repo wrote (None: not changed), written to disk first."""
    if name not in record.settings or not valid_value(applied):
        raise RecoveryError(f"cannot note {applied!r} for {name}: not in the settings record")
    updated = replace(record, settings={**record.settings, name: replace(record.settings[name], applied=applied)})
    _write(updated)
    return updated
