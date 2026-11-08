#!/usr/bin/env python3
"""Combine brand, carrier and model lists into one personal list, after the person's choices.

    compose.py <list>... --checklist              print the groups to ask about, with what is installed
    compose.py <list>... -o work/my-phone.txt     write the personal list to apply
        --drop-group "<name>"    leave a whole group out (the ones the person ticked "I use this")
        --drop <package>         leave one package out
        --include-expert         include every [expert] group (only when the person asked for it)
        --include-group "<name>" include one [expert] group by name
        --offline                do not read the phone (keeps packages that may not be installed)

Lists are read in order; a package in more than one list keeps its first entry. Packages a guard
protects are dropped with a warning. With a phone connected, packages that are not on it are left out,
so the written list is what the dry run will show.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import common
import device
import guards
import listfile

TIER_TITLES = {
    "safe": "Safe: applied after one confirmation for all of them",
    "ask": "Ask: one checklist question per group; leave out what the person uses",
    "expert": "Expert: only if the person asks for more",
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("lists", nargs="+", help="lists to combine, most general first")
    parser.add_argument("--checklist", action="store_true", help="print the questions to ask, write nothing")
    parser.add_argument("-o", "--output", help="write the personal list here (default: print it)")
    parser.add_argument("--drop-group", action="append", default=[], help="leave this group out")
    parser.add_argument("--drop", action="append", default=[], help="leave this package out")
    parser.add_argument("--include-expert", action="store_true", help="include all [expert] groups")
    parser.add_argument("--include-group", action="append", default=[], help="include this [expert] group")
    parser.add_argument("--offline", action="store_true", help="do not read the phone")
    parser.add_argument("--serial", help="the phone to use when more than one is connected")
    return parser


def _checklist(entries: tuple, states: device.PackageStates | None) -> str:
    lines = []
    for tier in listfile.TIERS:
        groups: dict = {}
        for entry in (e for e in entries if e.tier == tier):
            groups.setdefault(entry.group, []).append(entry)
        if not groups:
            continue
        lines += [f"\n## {TIER_TITLES[tier]}"]
        for group, members in groups.items():
            lines.append(f"\n### {group} ({len(members)} package{'s' if len(members) != 1 else ''})")
            for entry in members:
                state = f" [{states.state(entry.package)}]" if states else ""
                comment = f" - {entry.comment}" if entry.comment else ""
                lines.append(f"- {entry.package}{state}{comment}")
    return "\n".join(lines).lstrip("\n") + "\n"


def _selected(entries: tuple, args: argparse.Namespace) -> tuple:
    dropped_groups = {g.lower() for g in args.drop_group}
    included = {g.lower() for g in args.include_group}
    return tuple(e for e in entries
                 if e.group.lower() not in dropped_groups and e.package not in args.drop
                 and (e.tier != "expert" or args.include_expert or e.group.lower() in included))


def _header(args: argparse.Namespace, info: device.DeviceInfo | None) -> list:
    phone = (f"{info.brand} {info.model} ({info.device}), Android {info.android}, {info.skin}, {info.build}"
             if info else "not checked (--offline)")
    expert = "all" if args.include_expert else (", ".join(args.include_group) or "none")
    return [
        f"Personal debloat list written by tools/compose.py on {date.today().isoformat()}",
        f"Phone: {phone}",
        f"From: {', '.join(args.lists)}",
        f"Dropped groups: {', '.join(args.drop_group) or 'none'}",
        f"Dropped packages: {', '.join(args.drop) or 'none'}",
        f"Expert groups included: {expert}",
        "",
        "Dry run:  python3 tools/disable.py <this file>",
        "Apply:    python3 tools/disable.py <this file> --apply",
        "Undo:     python3 tools/restore.py <this file>",
    ]


def _run(args: argparse.Namespace, phone: device.Phone | None) -> int:
    entries = listfile.compose([listfile.load(path) for path in args.lists])
    common.select_groups(entries, args.drop_group + args.include_group)  # unknown names are an error
    blocked = guards.protected([e.package for e in entries], guards.load())
    for package, reason in blocked.items():
        common.err(f"left out, protected: {package} ({reason})")
    entries = tuple(e for e in entries if e.package not in blocked)
    states = info = None
    if not args.offline:
        phone = common.phone_or_connect(phone, args.serial)
        states, info = device.read_states(phone), device.read_info(phone)
        entries = tuple(e for e in entries if states.state(e.package) != "absent")
    if args.checklist:
        print(_checklist(entries, states), end="")
        return common.EXIT_OK
    text = listfile.render(_selected(entries, args), header=_header(args, info))
    if not args.output:
        print(text, end="")
        return common.EXIT_OK
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    print(f"Wrote {output} ({len(_selected(entries, args))} packages). Next: python3 tools/disable.py {output}")
    return common.EXIT_OK


def main(argv: list | None = None, phone: device.Phone | None = None) -> int:
    args = _parser().parse_args(argv)
    return common.run(lambda: _run(args, phone))


if __name__ == "__main__":
    sys.exit(main())
