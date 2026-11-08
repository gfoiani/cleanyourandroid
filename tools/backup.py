#!/usr/bin/env python3
"""Save what the phone looks like before anything changes. Reads only.

    backup.py                  write backup/<serial>-<date-time>/
    backup.py --out <dir>      write under another folder

Files: getprop.txt, packages-{known,enabled,disabled,uninstalled,system,thirdparty}.txt,
settings-{global,secure,system}.txt, in-use.txt, users.txt and info.json.

This is a record of the phone's configuration, not a backup of photos, chats or contacts: the person
backs those up with their own cloud or computer before starting (PROMPT.md asks them). The files hold
device identifiers, so backup/ is in .gitignore and is never shared.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import common
import device


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=str(common.ROOT / "backup"), help="folder for the backup")
    parser.add_argument("--serial", help="the phone to use when more than one is connected")
    return parser


def _lines(names) -> str:
    return "".join(f"{name}\n" for name in sorted(names))


def _contents(phone: device.Phone) -> dict:
    states = device.read_states(phone)
    using = device.in_use(phone)
    info = device.read_info(phone)
    files = {
        "getprop.txt": phone.shell("getprop").out,
        "packages-known.txt": _lines(states.known),
        "packages-enabled.txt": _lines(states.installed - states.disabled),
        "packages-disabled.txt": _lines(states.disabled),
        "packages-uninstalled.txt": _lines(states.known - states.installed),
        "packages-system.txt": _lines(states.system),
        "packages-thirdparty.txt": _lines(states.known - states.system),
        "in-use.txt": "".join(f"{package}\t{reason}\n" for package, reason in sorted(using.items())),
        "users.txt": phone.shell("pm list users").out,
        "info.json": json.dumps({**asdict(info), "saved": datetime.now().isoformat(timespec="seconds")},
                                indent=2) + "\n",
    }
    for namespace in ("global", "secure", "system"):
        files[f"settings-{namespace}.txt"] = phone.shell(f"settings list {namespace}").out
    return files


def _run(args: argparse.Namespace, phone: device.Phone | None) -> int:
    phone = common.phone_or_connect(phone, args.serial)
    folder = Path(args.out) / f"{phone.serial}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    files = _contents(phone)
    folder.mkdir(parents=True, exist_ok=False)
    for name, text in files.items():
        (folder / name).write_text(text, encoding="utf-8")
    print(f"Saved {len(files)} files to {folder}")
    print("It holds device identifiers: keep it private (backup/ is in .gitignore).")
    return common.EXIT_OK


def main(argv: list | None = None, phone: device.Phone | None = None) -> int:
    args = _parser().parse_args(argv)
    return common.run(lambda: _run(args, phone))


if __name__ == "__main__":
    sys.exit(main())
