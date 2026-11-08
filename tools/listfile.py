"""Debloat lists: one package per line, grouped under a header that carries a tier.

    # @brands: oneplus oppo          metadata, read by probe.py to suggest the list
    # == OnePlus telemetry [safe]    a group; the tier decides how the assistant asks about it
    com.oplus.statistics.rom         # trailing comment: what the package is

Tiers:
    safe    applied after one confirmation for the whole tier
    ask     each group becomes a checklist question; only what the person does not tick is applied
    expert  never offered unless the person asks for it

A package name is pasted into a shell command on the phone, so anything that is not a bare package
name refuses the whole list, with the file and line.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path
from typing import NamedTuple

TIERS = ("safe", "ask", "expert")
DEFAULT_GROUP = "Ungrouped"
DEFAULT_TIER = "ask"
PACKAGE_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+")
GROUP_RE = re.compile(r"#\s*==\s*(?P<title>.*?)\s*(?:\[(?P<tier>[^\]]*)\])?\s*$")
META_RE = re.compile(r"#\s*@(?P<key>[a-z_]+)\s*:\s*(?P<value>.*?)\s*$")


class ListError(ValueError):
    """A list that cannot be used as it is. The message names the file and line."""


class Entry(NamedTuple):
    package: str
    group: str
    tier: str
    comment: str
    source: str


class ListFile(NamedTuple):
    source: str
    meta: dict
    entries: tuple


def _group(line: str, where: str) -> tuple[str, str]:
    match = GROUP_RE.fullmatch(line)
    tier = (match.group("tier") or "").strip().lower() if match else ""
    if not match or tier not in TIERS:
        raise ListError(f"{where}: a group header needs a tier, one of {', '.join(TIERS)}: {line!r}")
    return match.group("title"), tier


def _entry(line: str, where: str) -> tuple[str, str]:
    body, _, comment = line.partition("#")
    package = body.strip()
    if not PACKAGE_RE.fullmatch(package):
        raise ListError(f"{where}: not a package name: {package!r}")
    return package, comment.strip()


def walk(text: str, source: str = "<text>") -> tuple[dict, list]:
    """The metadata, and each entry line as (where, line, group, tier), for any file in this format."""
    text = text.lstrip("\ufeff")
    meta: dict = {}
    lines: list = []
    group, tier = DEFAULT_GROUP, DEFAULT_TIER
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        where = f"{source}:{number}"
        if not line:
            continue
        if re.match(r"#\s*==", line):
            group, tier = _group(line, where)
            continue
        if line.startswith("#"):
            meta_match = META_RE.fullmatch(line)
            if meta_match:
                meta[meta_match.group("key")] = meta_match.group("value")
            continue
        lines.append((where, line, group, tier))
    return meta, lines


def parse(text: str, source: str = "<text>") -> ListFile:
    meta, lines = walk(text, source)
    entries: list = []
    seen: set = set()
    for where, line, group, tier in lines:
        package, comment = _entry(line, where)
        if package in seen:
            raise ListError(f"{where}: {package} is listed twice")
        seen.add(package)
        entries.append(Entry(package, group, tier, comment, source))
    return ListFile(source, meta, tuple(entries))


def load(path: Path | str) -> ListFile:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ListError(f"cannot read the list {path}: {error}") from error
    return parse(text, source=str(path))


def compose(lists: Iterable[ListFile]) -> tuple:
    """All entries in order; a package that appears again in a later list keeps its first entry."""
    seen: set = set()
    merged = []
    for parsed in lists:
        for entry in parsed.entries:
            if entry.package not in seen:
                seen.add(entry.package)
                merged.append(entry)
    return tuple(merged)


def render(entries: Iterable[Entry], header: Iterable[str] = ()) -> str:
    """Entries back to list text, one group header each time the group or tier changes."""
    lines = [f"# {line}".rstrip() for line in header]
    current = None
    for entry in entries:
        if (entry.group, entry.tier) != current:
            current = (entry.group, entry.tier)
            lines += ["", f"# == {entry.group} [{entry.tier}]"]
        lines.append(f"{entry.package:<48} # {entry.comment}" if entry.comment else entry.package)
    return "\n".join(lines) + "\n"
