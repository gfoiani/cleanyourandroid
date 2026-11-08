#!/usr/bin/env python3
"""Undo a debloat list: put every package back in the state it had before tools/disable.py ran.

    restore.py <list>                     replay the recovery record for this phone and list
    restore.py <list> --group "<name>"    only that group (repeatable): undo the last batch
    restore.py <list> --package <name>    only that package (repeatable)
    restore.py <list> --without-record    no record (another computer, deleted folder): enable every
                                          package in the list, also ones that were off before

It only enables and reinstalls (`pm enable`, `cmd package install-existing`); it never disables or
removes anything, so it is safe to run more than once.

Exit status: 0 restored, 1 something could not be put back, 2 nothing ran (see common.py).
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import replace

import actions
import common
import device
import listfile
import recovery


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("list", help="the list that was applied")
    parser.add_argument("--without-record", action="store_true",
                        help="no recovery record: enable everything in the list")
    parser.add_argument("--group", action="append", help="only this group of the list (repeatable)")
    parser.add_argument("--package", action="append", default=[], help="only this package (repeatable)")
    parser.add_argument("--serial", help="the phone to use when more than one is connected")
    return parser


def _wanted(args: argparse.Namespace, entries: tuple, record: recovery.Record) -> frozenset | None:
    """The packages to restore, or None for all of them. A package may have left the list since."""
    if not args.group and not args.package:
        return None
    known = {e.package for e in entries} | set(record.packages)
    unknown = [p for p in args.package if p not in known]
    if unknown:
        raise listfile.ListError(f"not in the list or the recovery record: {', '.join(unknown)}")
    grouped = {e.package for e in common.select_groups(entries, args.group)} if args.group else set()
    return frozenset(grouped | set(args.package))


def _only(record: recovery.Record, wanted: frozenset | None) -> recovery.Record:
    if wanted is None:
        return record
    return replace(record, packages={n: p for n, p in record.packages.items() if n in wanted})


def _forget_restored(record: recovery.Record, outcomes: tuple) -> None:
    """Packages that are back on are no longer this repo's change: check.py must not turn them off again."""
    for outcome in outcomes:
        entry = record.packages.get(outcome.package)
        if entry is not None and entry.method and outcome.action in ("enabled", "reinstalled", "unchanged"):
            record = recovery.with_method(record, outcome.package, None)


def _record_for(args: argparse.Namespace, serial: str, entries: tuple) -> recovery.Record | None:
    record = recovery.load(serial, args.list)
    if record is not None or not args.without_record:
        return record
    everything_on = {e.package: recovery.PackageRecord("enabled") for e in entries}
    return recovery.Record(serial, args.list, "", everything_on)


def _run(args: argparse.Namespace, phone: device.Phone | None) -> int:
    parsed = listfile.load(args.list)
    phone = common.phone_or_connect(phone, args.serial)
    record = _record_for(args, phone.serial, parsed.entries)
    if record is None:
        common.err(f"No recovery record for this phone and list ({recovery.path_for(phone.serial, args.list)}).\n"
                   "If the list was applied from another computer or the record was deleted, run again with "
                   "--without-record: it enables every package in the list, also any that were off before.")
        return common.EXIT_NOT_RUN
    wanted = _wanted(args, parsed.entries, record)
    outcomes = actions.restore(phone, _only(record, wanted))
    if not args.without_record or recovery.load(phone.serial, args.list) is not None:
        _forget_restored(record, outcomes)
    changed = [o for o in outcomes if o.action != "unchanged"]
    for outcome in changed:
        detail = f"  ({outcome.detail})" if outcome.action not in ("enabled", "reinstalled") else ""
        print(f"  {outcome.action:<11} {outcome.package}{detail}")
    print(f"Restored {sum(o.action in ('enabled', 'reinstalled') for o in outcomes)} package(s); "
          f"{len(outcomes) - len(changed)} were already as before.")
    problems = [o for o in outcomes if o.action in ("refused", "unverified", "missing")]
    return common.EXIT_NEEDS_A_LOOK if problems else common.EXIT_OK


def main(argv: list | None = None, phone: device.Phone | None = None) -> int:
    args = _parser().parse_args(argv)
    return common.run(lambda: _run(args, phone))


if __name__ == "__main__":
    sys.exit(main())
