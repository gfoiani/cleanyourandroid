"""Debloat list format: groups with a tier, metadata, and refusal of anything that is not a package name."""
import pytest

import listfile
from helpers import write
from listfile import ListError

SAMPLE = """\
# OnePlus 8T, OxygenOS 14
# @brands: oneplus oppo
# @sdk: 33-35

# == OnePlus telemetry [safe]
com.oplus.statistics.rom          # ROM statistics uploader
com.oplus.logkit

# == OnePlus community app [ask]
com.oneplus.membership

# == Unclear system services [expert]
com.oplus.nas
"""


def test_parses_groups_tiers_and_trailing_comments():
    parsed = listfile.parse(SAMPLE, source="sample.txt")

    assert [e.package for e in parsed.entries] == [
        "com.oplus.statistics.rom", "com.oplus.logkit", "com.oneplus.membership", "com.oplus.nas"]
    first = parsed.entries[0]
    assert (first.group, first.tier, first.comment) == ("OnePlus telemetry", "safe", "ROM statistics uploader")
    assert parsed.entries[2].tier == "ask"
    assert parsed.entries[3].tier == "expert"
    assert parsed.entries[0].source == "sample.txt"


def test_reads_metadata_lines():
    parsed = listfile.parse(SAMPLE)

    assert parsed.meta == {"brands": "oneplus oppo", "sdk": "33-35"}


def test_entries_before_any_group_default_to_ask():
    parsed = listfile.parse("com.example.bloat\n")

    assert parsed.entries[0].tier == "ask"
    assert parsed.entries[0].group == "Ungrouped"


def test_strips_bom_and_crlf_from_windows_editors():
    parsed = listfile.parse("﻿# == Group [safe]\r\ncom.example.one\r\n")

    assert [e.package for e in parsed.entries] == ["com.example.one"]


@pytest.mark.parametrize("line", [
    "com.example.ok; reboot",
    "rm -rf /",
    "$(id)",
    "android",          # no dot: never a list entry
    "com.example.ok extra",
])
def test_refuses_lines_that_are_not_a_package_name(line):
    with pytest.raises(ListError) as error:
        listfile.parse(f"# == G [safe]\n{line}\n", source="bad.txt")

    assert "bad.txt:2" in str(error.value)


def test_refuses_duplicates_in_one_list():
    with pytest.raises(ListError, match="twice"):
        listfile.parse("# == G [safe]\ncom.example.a\ncom.example.a\n")


def test_refuses_unknown_or_missing_tier():
    with pytest.raises(ListError, match="tier"):
        listfile.parse("# == G [maybe]\ncom.example.a\n")
    with pytest.raises(ListError, match="tier"):
        listfile.parse("# == G\ncom.example.a\n")


def test_load_reads_a_file_and_names_it_as_source(tmp_path):
    path = write(tmp_path / "x.txt", "# == G [safe]\ncom.example.a\n")

    parsed = listfile.load(path)

    assert parsed.entries[0].source == str(path)


def test_load_reports_a_missing_file_as_a_list_error(tmp_path):
    with pytest.raises(ListError, match="cannot read"):
        listfile.load(tmp_path / "missing.txt")


def test_compose_keeps_the_first_occurrence_of_a_package():
    a = listfile.parse("# == Brand [safe]\ncom.example.a\ncom.example.b\n", source="a")
    b = listfile.parse("# == Model [ask]\ncom.example.b\ncom.example.c\n", source="b")

    entries = listfile.compose([a, b])

    assert [(e.package, e.source) for e in entries] == [
        ("com.example.a", "a"), ("com.example.b", "a"), ("com.example.c", "b")]


def test_render_round_trips_through_parse():
    entries = listfile.parse(SAMPLE).entries

    text = listfile.render(entries, header=["Composed for a test"])
    again = listfile.parse(text)

    assert again.entries == tuple(e._replace(source="<text>") for e in entries)
    assert text.startswith("# Composed for a test\n")
