#!/usr/bin/env python3
"""Identify the phone and suggest the lists that apply to it. Reads only.

    probe.py                 brand, model, Android version, skin, carrier, users; matching lists
    probe.py --root <dir>    look for lists and examples under another checkout (tests)

A list under lists/ is suggested from its metadata lines:

    # @brands: oneplus oppo      required; `any` for lists that fit every brand
    # @sdk: 33-35                optional; also `34`, `33-` or `-34`
    # @carriers: tim             optional; matched against the SIM's operator name

A folder under examples/ is suggested when its phone.json names this model or device codename.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import common
import device
import listfile


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=str(common.ROOT), help="the checkout to search for lists")
    parser.add_argument("--serial", help="the phone to use when more than one is connected")
    return parser


def _sdk_matches(spec: str, sdk: int) -> bool:
    if not spec:
        return True
    low, dash, high = spec.partition("-")
    if not dash:
        return low.strip().isdigit() and sdk == int(low)
    return (not low.strip() or sdk >= int(low)) and (not high.strip() or sdk <= int(high))


def list_matches(meta: dict, info: device.DeviceInfo) -> bool:
    brands = meta.get("brands", "").lower().split()
    if not brands or ("any" not in brands and info.brand.lower() not in brands):
        return False
    if not _sdk_matches(meta.get("sdk", ""), info.sdk):
        return False
    carriers = meta.get("carriers", "").lower().split()
    words = set(re.split(r"[\s,]+", info.carrier.lower()))
    return not carriers or bool(words & set(carriers))


def suggest_lists(info: device.DeviceInfo, root: Path) -> list:
    return [path.relative_to(root).as_posix() for path in sorted((root / "lists").rglob("*.txt"))
            if list_matches(listfile.load(path).meta, info)]


def suggest_examples(info: device.DeviceInfo, root: Path) -> list:
    found = []
    for meta_path in sorted((root / "examples").glob("*/phone.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if info.model in meta.get("models", []) or info.device == meta.get("device"):
            found.append((meta_path.parent / "debloat.txt").relative_to(root).as_posix())
    return found


def _users(phone: device.Phone) -> list:
    return re.findall(r"UserInfo\{(\d+):([^:}]*)", phone.shell("pm list users").out)


def _run(args: argparse.Namespace, phone: device.Phone | None) -> int:
    root = Path(args.root)
    phone = common.phone_or_connect(phone, args.serial)
    info = device.read_info(phone)
    print(f"Phone:    {info.brand} {info.model} ({info.device}), serial {info.serial}")
    print(f"System:   Android {info.android} (SDK {info.sdk}), {info.skin}, build {info.build}")
    print(f"Carrier:  {info.carrier or 'no SIM or not reported'}")
    users = _users(phone)
    if len(users) > 1:
        names = ", ".join(f"{uid} {name}" for uid, name in users)
        print(f"Note:     more than one user or profile ({names}). The tools change user 0 only; apps in a "
              "work profile, Secure Folder or second space are left as they are.")
    lists = suggest_lists(info, root)
    examples = suggest_examples(info, root)
    print("\nLists that match this phone:" if lists else "\nNo list under lists/ matches this phone yet.")
    for path in lists:
        print(f"  {path}")
    print("Tested lists for this model:" if examples else "No tested list for this exact model yet.")
    for path in examples:
        print(f"  {path}")
    if lists or examples:
        print(f"\nNext: python3 tools/compose.py {' '.join(lists + examples)} --checklist")
    return common.EXIT_OK


def main(argv: list | None = None, phone: device.Phone | None = None) -> int:
    args = _parser().parse_args(argv)
    return common.run(lambda: _run(args, phone))


if __name__ == "__main__":
    sys.exit(main())
