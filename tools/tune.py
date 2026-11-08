#!/usr/bin/env python3
"""Battery-saving settings from tweaks/: dry run first, the old values recorded, every change undoable.

    tune.py tweaks/power.txt                               dry run: each group, the value now and the new one
    tune.py tweaks/power.txt --group "<name>" --apply      change those groups (repeatable; at least one)
    tune.py tweaks/power.txt --restore                     put back every value tune.py changed
    tune.py tweaks/power.txt --restore --group "<name>"    only that group

Only files inside tweaks/ are accepted: every setting this tool can change has been reviewed there, and
tools/tweakfile.py refuses the settings no file may name. There is no "apply everything": the person
picks each group. A setting the person changed after tune.py is left as they set it on restore.

Exit status: 0 done (or a dry run printed), 1 a setting was refused, not kept or the run stopped,
2 nothing ran (see common.py).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import actions
import common
import device
import tweakfile
import tweakrecord
from listfile import ListError

CATALOG = common.ROOT / "tweaks"
PROBLEMS = ("refused", "unverified", "interrupted", "not attempted")
NO_PERMISSION = "WRITE_SECURE_SETTINGS"   # in the answer of a phone that keeps settings from adb
NO_PERMISSION_HINT = (
    "\nThe phone does not let a computer change these settings over USB, so nothing was changed. OnePlus,\n"
    "OPPO and realme allow it only with \"Disable permission monitoring\" in Developer options, Xiaomi with\n"
    "\"USB debugging (Security settings)\". Do not turn that protection off for this:\n"
    "change the setting by hand where the comment in the file says.")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", help="a settings file in tweaks/")
    parser.add_argument("--group", action="append", help="only this group (repeatable; required with --apply)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="make the changes (default: dry run)")
    mode.add_argument("--restore", action="store_true", help="put back the values from before")
    parser.add_argument("--serial", help="the phone to use when more than one is connected")
    return parser


def _reviewed(path: str, catalog: Path) -> tweakfile.TweakFile:
    resolved = Path(path).resolve()
    if catalog.resolve() not in resolved.parents:
        raise ListError(f"{path}: only the reviewed files in tweaks/ are accepted")
    return tweakfile.load(resolved)


def _shown(value: str | None) -> str:
    return "not set" if value is None else value


def _status(tweak: tweakfile.Tweak, current: str | None) -> str:
    if not tweakrecord.valid_value(current):
        return f"current value {current!r} cannot be recorded safely; left as is"
    if tweak.satisfied_by(current):
        if current is None and tweak.default is not None:
            return f"already {tweak.default} (not set: Android's default)"
        return f"already {_shown(current)}"
    return f"{_shown(current)} -> {tweak.value}"


def _print_plan(tweaks: tuple, values: dict) -> None:
    group = None
    for tweak in tweaks:
        if (tweak.group, tweak.tier) != group:
            group = (tweak.group, tweak.tier)
            print(f"\n== {tweak.group} [{tweak.tier}]")
        comment = f"   # {tweak.comment}" if tweak.comment else ""
        print(f"  {tweak.name:<44} {_status(tweak, values[tweak.name])}{comment}")


def _print_outcomes(outcomes: tuple) -> None:
    for outcome in outcomes:
        print(f"  {outcome.action:<13} {outcome.name}  ({outcome.detail})")
    if any(o.action == "refused" and NO_PERMISSION in o.detail for o in outcomes):
        print(NO_PERMISSION_HINT)


def _apply(args: argparse.Namespace, phone: device.Phone, chosen: tuple) -> int:
    values = {t.name: device.read_setting(phone, t.namespace, t.key) for t in chosen}
    _print_plan(chosen, values)
    to_change = tuple(t for t in chosen
                      if tweakrecord.valid_value(values[t.name]) and not t.satisfied_by(values[t.name]))
    if not args.apply:
        print("\nDry run: nothing was changed. Run again with --group \"<name>\" --apply for the groups the "
              "person said yes to.")
        return common.EXIT_OK
    if not to_change:
        print("\nNothing to change.")
        return common.EXIT_OK
    recordable = {name: value for name, value in values.items() if tweakrecord.valid_value(value)}
    record = tweakrecord.save(phone.serial, args.file, recordable)
    print(f"\nSettings record: {tweakrecord.path_for(phone.serial, args.file)}")
    outcomes, _ = actions.apply_settings(phone, to_change, record)
    _print_outcomes(outcomes)
    if any(o.action in ("interrupted", "not attempted") for o in outcomes):
        print("\nThe run stopped early. Check the cable and that the phone is unlocked, then run the same "
              "command again, or undo with --restore.")
    print(f"Undo at any time: python3 tools/tune.py {args.file} --restore")
    return common.EXIT_NEEDS_A_LOOK if any(o.action in PROBLEMS for o in outcomes) else common.EXIT_OK


def _restore(args: argparse.Namespace, phone: device.Phone, chosen: tuple) -> int:
    record = tweakrecord.load(phone.serial, args.file)
    if record is None:
        common.err(f"No settings record for this phone and file ({tweakrecord.path_for(phone.serial, args.file)}). "
                   "Nothing to put back from this computer; change the values by hand in Settings if needed.")
        return common.EXIT_NOT_RUN
    names = frozenset(t.name for t in chosen) if args.group else None
    outcomes, _ = actions.restore_settings(phone, record, names)
    _print_outcomes(outcomes)
    print(f"Restored {sum(o.action == 'restored' for o in outcomes)} setting(s).")
    return common.EXIT_NEEDS_A_LOOK if any(o.action in PROBLEMS for o in outcomes) else common.EXIT_OK


def _run(args: argparse.Namespace, phone: device.Phone | None, catalog: Path) -> int:
    if args.apply and not args.group:
        common.err("--apply needs at least one --group: only the groups the person said yes to are applied.")
        return common.EXIT_NOT_RUN
    parsed = _reviewed(args.file, catalog)
    chosen = common.select_groups(parsed.entries, args.group)
    phone = common.phone_or_connect(phone, args.serial)
    return _restore(args, phone, chosen) if args.restore else _apply(args, phone, chosen)


def main(argv: list | None = None, phone: device.Phone | None = None, catalog: Path = CATALOG) -> int:
    args = _parser().parse_args(argv)
    return common.run(lambda: _run(args, phone, catalog))


if __name__ == "__main__":
    sys.exit(main())
