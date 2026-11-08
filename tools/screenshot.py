#!/usr/bin/env python3
"""Take a screenshot on the phone and save it here, to check each step by looking at it.

    screenshot.py shots/01-before.png

Exit status: 0 saved, 1 the capture came back empty (the app on screen blocks screenshots),
2 nothing ran (see common.py).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import common
import device


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("output", help="where to save the PNG")
    parser.add_argument("--serial", help="the phone to use when more than one is connected")
    return parser


def _run(args: argparse.Namespace, phone: device.Phone | None) -> int:
    phone = common.phone_or_connect(phone, args.serial)
    size = phone.screenshot(Path(args.output))
    if size == 0:
        common.err("The screenshot came back empty: the app on screen blocks screenshots (banking apps, "
                   "DRM video, password fields). That is the app, not damage. Go to the home screen and retry.")
        return common.EXIT_NEEDS_A_LOOK
    print(f"Saved {args.output} ({size} bytes)")
    return common.EXIT_OK


def main(argv: list | None = None, phone: device.Phone | None = None) -> int:
    args = _parser().parse_args(argv)
    return common.run(lambda: _run(args, phone))


if __name__ == "__main__":
    sys.exit(main())
