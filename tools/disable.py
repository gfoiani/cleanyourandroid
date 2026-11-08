#!/usr/bin/env python3
"""Disable the packages in a debloat list, for user 0. A dry run unless --apply is given.

    disable.py <list>                               show what would change; change nothing
    disable.py <list> --apply                       disable, one package per command
    disable.py <list> --apply --group "<name>"      only that group (repeatable): work in small batches
    disable.py <list> --apply --fallback-uninstall  where the phone refuses to disable a system package,
                                                    remove it for user 0 instead, keeping its data (-k);
                                                    only after the person agreed to it

Before the first change, the state of every package in the list is written to the recovery record
(~/.cleanyourandroid/), and `tools/restore.py <same list>` puts it back. A list that names a protected
package (guards/*.txt) is refused as a whole. Packages the person is using right now (default home,
phone, SMS, keyboard, accessibility, device admin) are skipped and reported.

Exit status: 0 done or dry run, 1 something was refused or not kept, 2 nothing ran (see common.py).
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

REBOOT_NOTE = ("Wait at least 15 seconds before rebooting: Android writes package state to disk about ten "
               "seconds after a change, and a reboot sent sooner can bring the old state back.")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("list", help="the debloat list to apply (usually one written by compose.py)")
    parser.add_argument("--apply", action="store_true", help="change the phone; without it this is a dry run")
    parser.add_argument("--group", action="append", help="only this group of the list (repeatable)")
    parser.add_argument("--fallback-uninstall", action="store_true",
                        help="remove for user 0 (keeping data) what the phone refuses to disable")
    parser.add_argument("--serial", help="the phone to use when more than one is connected")
    return parser


def _print_plan(plan: actions.Plan, entries: tuple) -> None:
    by_name = {e.package: e for e in entries}
    print(f"Will change {len(plan.to_change)} package(s):")
    for package in plan.to_change:
        entry = by_name[package]
        note = " (installed by the user, not part of the system)" if package in plan.user_apps else ""
        print(f"  {package:<48} [{entry.group}] {entry.comment}{note}")
    for title, found in (("Skipped, in use right now", plan.in_use), ("Skipped, protected", plan.protected)):
        if found:
            print(f"{title}:")
            for package, reason in found.items():
                print(f"  {package:<48} {reason}")
    if plan.already:
        print(f"Already off: {', '.join(plan.already)}")
    if plan.absent:
        print(f"Not on this phone: {', '.join(plan.absent)}")


def _print_result(result: actions.ApplyResult, fallback: bool) -> None:
    for outcome in result.outcomes:
        detail = f"  ({outcome.detail})" if outcome.detail else ""
        print(f"  {outcome.action:<11} {outcome.package}{detail}")
    stopped = [o for o in result.outcomes if o.action in ("interrupted", "not attempted")]
    if stopped:
        changed = sum(o.action in actions.SUCCESSFUL for o in result.outcomes)
        print(f"\nThe run stopped early: {changed} package(s) were changed, {len(stopped)} were not. Check the "
              "cable and that the phone is unlocked, then run the same command again to continue, or undo with "
              "tools/restore.py.")
    refused = [o.package for o in result.outcomes if o.action == "refused"]
    if refused and not fallback:
        print(f"\nThe phone refused to disable {len(refused)} package(s). Leave them, or - only after the "
              "person agrees - run again with --fallback-uninstall to remove them for user 0 while keeping "
              "their data; tools/restore.py brings them back with `cmd package install-existing`.")


def _run(args: argparse.Namespace, phone: device.Phone | None) -> int:
    parsed = listfile.load(args.list)
    entries = common.select_groups(parsed.entries, args.group)
    guard_set = guards.load()
    if common.refuse_protected(parsed.entries, guard_set):
        return common.EXIT_NOT_RUN
    phone = common.phone_or_connect(phone, args.serial)
    states = device.read_states(phone)
    plan = actions.plan(entries, states, guard_set, device.in_use(phone))
    _print_plan(plan, entries)
    if not args.apply:
        print("\nDry run: nothing was changed. Run again with --apply to make these changes.")
        return common.EXIT_OK
    if not plan.to_change:
        print("\nNothing to change.")
        return common.EXIT_OK
    record = recovery.save(phone.serial, args.list, {e.package: states.state(e.package) for e in parsed.entries})
    print(f"\nRecovery record: {recovery.path_for(phone.serial, args.list)}")
    result = actions.apply(phone, plan, record, args.fallback_uninstall)
    _print_result(result, args.fallback_uninstall)
    print(f"\n{REBOOT_NOTE}")
    print(f"Undo at any time: python3 tools/restore.py {args.list}")
    return common.EXIT_OK if result.ok else common.EXIT_NEEDS_A_LOOK


def main(argv: list | None = None, phone: device.Phone | None = None) -> int:
    args = _parser().parse_args(argv)
    return common.run(lambda: _run(args, phone))


if __name__ == "__main__":
    sys.exit(main())
