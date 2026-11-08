#!/usr/bin/env python3
"""Write the phone table and the brand line from each examples/<folder>/phone.json.

    gen_tables.py            rewrite examples/README.md and the brand block in README.md
    gen_tables.py --check    write nothing; exit 1 when a file is out of date

A pull request that adds a phone adds only its own folder. The tables are generated, between markers:

    <!-- phones:start ... -->  ...  <!-- phones:end -->     examples/README.md
    <!-- brands:start ... -->  ...  <!-- brands:end -->     README.md

phone.json:
    {
      "phone": "OnePlus 8T",                  the name the tables show
      "brand": "OnePlus",
      "models": ["KB2003", "KB2005"],         ro.product.model values (probe.py matches on these)
      "device": "OnePlus8T",                  ro.product.device codename
      "os": "Android 14, OxygenOS 14",
      "notes": "one line: what the list disables and keeps"
    }

Exit status: 0 written or up to date, 1 out of date (--check), 2 a phone.json or marker is unusable.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

import common

KEYS = {"phone": str, "brand": str, "models": list, "device": str, "os": str, "notes": str}
TARGETS = {"phones": ("examples/README.md",), "brands": ("README.md",)}


class TableError(ValueError):
    pass


def read_phone_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise TableError(f"cannot read {path}: {error}") from error
    wrong = [key for key, kind in KEYS.items() if not isinstance(data.get(key), kind)]
    if wrong:
        raise TableError(f"{path}: missing or wrong type for {', '.join(wrong)}")
    return data


def _cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def phones_block(rows: list) -> str:
    lines = ["| Folder | Phone | Models | OS | Notes |", "|---|---|---|---|---|"]
    for folder, meta in rows:
        lines.append(f"| `{folder}/` | {_cell(meta['phone'])} | {_cell(', '.join(meta['models']))} | "
                     f"{_cell(meta['os'])} | {_cell(meta['notes'])} |")
    if not rows:
        lines.append("| | No tested phone yet: be the first ([CONTRIBUTING.md](../CONTRIBUTING.md)). | | | |")
    return "\n".join(lines)


def brands_block(rows: list) -> str:
    counts = Counter(meta["brand"] for _, meta in rows)
    if not counts:
        return "No tested phones yet."
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0].lower()))
    return " · ".join(f"**{brand} · {count}**" for brand, count in ordered)


def replace_block(text: str, name: str, body: str, where: str) -> str:
    pattern = re.compile(rf"(<!-- {name}:start[^>]*-->\n)(.*?)(<!-- {name}:end -->)", re.DOTALL)
    if not pattern.search(text):
        raise TableError(f"{where}: no <!-- {name}:start --> ... <!-- {name}:end --> markers")
    return pattern.sub(lambda m: f"{m.group(1)}{body}\n{m.group(3)}", text, count=1)


def _rows(root: Path) -> list:
    rows = [(p.parent.name, read_phone_json(p)) for p in sorted((root / "examples").glob("*/phone.json"))]
    return sorted(rows, key=lambda row: row[1]["phone"].lower())


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--root", default=str(common.ROOT))
    args = parser.parse_args(argv)
    root = Path(args.root)
    try:
        rows = _rows(root)
        bodies = {"phones": phones_block(rows), "brands": brands_block(rows)}
        stale = []
        for name, files in TARGETS.items():
            for relative in files:
                path = root / relative
                text = path.read_text(encoding="utf-8")
                updated = replace_block(text, name, bodies[name], relative)
                if updated != text:
                    stale.append(relative)
                    if not args.check:
                        path.write_text(updated, encoding="utf-8")
    except (TableError, OSError) as error:
        common.err(f"stopped: {error}")
        return common.EXIT_NOT_RUN
    if args.check and stale:
        common.err(f"out of date: {', '.join(stale)}; run python3 tools/gen_tables.py")
        return common.EXIT_NEEDS_A_LOOK
    return common.EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
