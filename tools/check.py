#!/usr/bin/env python3
"""What a system update turned back on, compared with the list that was applied.

    check.py <list>          report packages this repo had changed that are enabled again; exit 1 if any
    check.py <list> --fix    change them again, the same way as before (disable, or uninstall for user 0
                             where that is what was done), with the same guards

Only packages the recovery record says this repo changed are checked, so groups the person chose to
keep never show up as drift. Fits a weekly reminder: exit 1 means "have a look".

Exit status: 0 in sync or fixed, 1 drift or an incomplete fix, 2 nothing ran (see common.py).
"""
from __future__ import annotations

import argparse
import sys

import actions
import common
import device
import guards
import listfile
import recovery


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("list", help="the list that was applied")
    parser.add_argument("--fix", action="store_true", help="change the drifted packages again")
    parser.add_argument("--serial", help="the phone to use when more than one is connected")
    return parser


def _fix(phone: device.Phone, entries: tuple, record: recovery.Record, states: device.PackageStates) -> bool:
    guard_set = guards.load()
    using = device.in_use(phone)
    ok = True
    for method, fallback in (("disable", False), ("uninstall", True)):
        subset = tuple(e for e in entries if record.packages[e.package].method == method)
        if not subset:
            continue
        states = device.read_states(phone)  # the previous pass changed the phone
        plan = actions.plan(subset, states, guard_set, using)
        for package, reason in {**plan.protected, **plan.in_use}.items():
            print(f"  skipped     {package}  ({reason})")
        result = actions.apply(phone, plan, record, fallback)
        record = result.record
        for outcome in result.outcomes:
            print(f"  {outcome.action:<11} {outcome.package}")
        ok = ok and result.ok and not plan.protected and not plan.in_use
    return ok


def _run(args: argparse.Namespace, phone: device.Phone | None) -> int:
    parsed = listfile.load(args.list)
    phone = common.phone_or_connect(phone, args.serial)
    record = recovery.load(phone.serial, args.list)
    if record is None:
        common.err(f"No recovery record for this phone and list, so there is nothing to compare with "
                   f"({recovery.path_for(phone.serial, args.list)}).")
        return common.EXIT_NOT_RUN
    states = device.read_states(phone)
    drifted = actions.drift(parsed.entries, states, record)
    if not drifted:
        print("In sync: everything this list changed is still off.")
        return common.EXIT_OK
    print(f"{len(drifted)} package(s) are on again (a system update?):")
    for package in drifted:
        print(f"  {package}")
    if not args.fix:
        print(f"\nRun `python3 tools/check.py {args.list} --fix` to change them again.")
        return common.EXIT_NEEDS_A_LOOK
    entries = tuple(e for e in parsed.entries if e.package in drifted)
    return common.EXIT_OK if _fix(phone, entries, record, states) else common.EXIT_NEEDS_A_LOOK


def main(argv: list | None = None, phone: device.Phone | None = None) -> int:
    args = _parser().parse_args(argv)
    return common.run(lambda: _run(args, phone))


if __name__ == "__main__":
    sys.exit(main())
