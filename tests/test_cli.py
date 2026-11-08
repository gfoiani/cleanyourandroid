"""The command-line tools, end to end against FakePhone."""
import json

import pytest

import backup
import check
import compose
import disable
import probe
import recovery
import restore
import screenshot
from adb import AdbError
from helpers import oneplus_phone, write

STATE_CHANGING = ("pm disable-user", "pm enable", "pm uninstall", "cmd package install-existing")

LIST = """\
# == OnePlus telemetry [safe]
com.oplus.statistics.rom     # ROM statistics
com.heytap.mcs               # HeyTap push: promotional notifications

# == OnePlus community [ask]
com.oneplus.membership       # Red Cable Club

# == Preloaded partner apps [ask]
com.netflix.partner.activation

# == Unclear services [expert]
com.coloros.childrenspace
"""


def changes(phone):
    return [c for c in phone.commands if c.startswith(STATE_CHANGING)]


@pytest.fixture(autouse=True)
def records(tmp_path, monkeypatch):
    monkeypatch.setenv("CLEANYOURANDROID_HOME", str(tmp_path / "records"))


@pytest.fixture
def list_path(tmp_path):
    return write(tmp_path / "my-phone.txt", LIST)


# disable.py ------------------------------------------------------------------------------------

def test_disable_without_apply_is_a_dry_run(list_path, capsys):
    phone = oneplus_phone()

    code = disable.main([str(list_path)], phone=phone)

    assert code == 0
    assert changes(phone) == []
    assert recovery.load(phone.serial, list_path) is None
    out = capsys.readouterr().out
    assert "Dry run" in out and "com.heytap.mcs" in out


def test_disable_apply_records_first_then_changes(list_path, capsys):
    phone = oneplus_phone()

    code = disable.main([str(list_path), "--apply"], phone=phone)

    assert code == 0
    record = recovery.load(phone.serial, list_path)
    assert record.packages["com.heytap.mcs"].before == "enabled"
    assert record.packages["com.heytap.mcs"].method == "disable"
    assert record.packages["com.coloros.childrenspace"].before == "disabled"
    assert phone.packages["com.heytap.mcs"]["state"] == "disabled"
    assert "15 seconds" in capsys.readouterr().out


def test_disable_only_the_named_group(list_path):
    phone = oneplus_phone()

    disable.main([str(list_path), "--apply", "--group", "OnePlus community"], phone=phone)

    assert changes(phone) == ["pm disable-user --user 0 com.oneplus.membership"]
    # The record still holds the whole list, so a later batch is undone by the same restore.
    assert "com.heytap.mcs" in recovery.load(phone.serial, list_path).packages


def test_disable_refuses_an_unknown_group(list_path, capsys):
    assert disable.main([str(list_path), "--group", "Nope"], phone=oneplus_phone()) == 2
    assert "Nope" in capsys.readouterr().err


def test_disable_refuses_a_list_with_a_protected_package(tmp_path, capsys):
    bad = write(tmp_path / "bad.txt", "# == G [safe]\ncom.heytap.mcs\ncom.android.phone\n")
    phone = oneplus_phone()

    code = disable.main([str(bad), "--apply"], phone=phone)

    assert code == 2
    assert changes(phone) == []
    assert "com.android.phone" in capsys.readouterr().err


def test_disable_refused_without_fallback_says_how_to_go_on(list_path, capsys):
    phone = oneplus_phone(refuse_disable={"com.heytap.mcs"})

    code = disable.main([str(list_path), "--apply", "--group", "OnePlus telemetry"], phone=phone)

    assert code == 1
    assert not any(c.startswith("pm uninstall") for c in phone.commands)
    assert "--fallback-uninstall" in capsys.readouterr().out


def test_disable_with_fallback_uninstalls_for_user_0_only(list_path):
    phone = oneplus_phone(refuse_disable={"com.heytap.mcs"})

    code = disable.main([str(list_path), "--apply", "--fallback-uninstall", "--group", "OnePlus telemetry"],
                        phone=phone)

    assert code == 0
    assert "pm uninstall -k --user 0 com.heytap.mcs" in phone.commands


def test_disable_reports_an_unreadable_list(tmp_path, capsys):
    assert disable.main([str(tmp_path / "missing.txt")], phone=oneplus_phone()) == 2
    assert "cannot read" in capsys.readouterr().err


# restore.py ------------------------------------------------------------------------------------

def test_restore_undoes_a_run(list_path):
    phone = oneplus_phone(refuse_disable={"com.heytap.mcs"})
    disable.main([str(list_path), "--apply", "--fallback-uninstall"], phone=phone)

    code = restore.main([str(list_path)], phone=phone)

    assert code == 0
    for package in ("com.heytap.mcs", "com.oplus.statistics.rom", "com.oneplus.membership"):
        assert phone.packages[package]["state"] == "enabled", package
    assert phone.packages["com.coloros.childrenspace"]["state"] == "disabled"


def test_restore_only_the_last_batch(list_path):
    phone = oneplus_phone()
    disable.main([str(list_path), "--apply"], phone=phone)

    code = restore.main([str(list_path), "--group", "OnePlus community", "--package", "com.heytap.mcs"],
                        phone=phone)

    assert code == 0
    assert phone.packages["com.oneplus.membership"]["state"] == "enabled"
    assert phone.packages["com.heytap.mcs"]["state"] == "enabled"
    assert phone.packages["com.oplus.statistics.rom"]["state"] == "disabled"


def test_restore_refuses_a_package_not_in_the_list(list_path, capsys):
    phone = oneplus_phone()
    disable.main([str(list_path), "--apply"], phone=phone)

    assert restore.main([str(list_path), "--package", "com.not.listed"], phone=phone) == 2
    assert "com.not.listed" in capsys.readouterr().err


def test_restore_without_a_record_stops_and_explains(list_path, capsys):
    assert restore.main([str(list_path)], phone=oneplus_phone()) == 2
    assert "--without-record" in capsys.readouterr().err


def test_restore_without_record_enables_everything_listed(list_path):
    phone = oneplus_phone()
    phone.packages["com.heytap.mcs"]["state"] = "disabled"
    phone.packages["com.oneplus.membership"]["state"] = "uninstalled"

    code = restore.main([str(list_path), "--without-record"], phone=phone)

    assert code == 0
    assert phone.packages["com.heytap.mcs"]["state"] == "enabled"
    assert phone.packages["com.oneplus.membership"]["state"] == "enabled"


# check.py --------------------------------------------------------------------------------------

def test_check_reports_and_fixes_drift(list_path, capsys):
    phone = oneplus_phone()
    disable.main([str(list_path), "--apply"], phone=phone)
    phone.packages["com.heytap.mcs"]["state"] = "enabled"

    assert check.main([str(list_path)], phone=phone) == 1
    assert "com.heytap.mcs" in capsys.readouterr().out
    assert check.main([str(list_path), "--fix"], phone=phone) == 0
    assert phone.packages["com.heytap.mcs"]["state"] == "disabled"
    assert check.main([str(list_path)], phone=phone) == 0


def test_check_needs_the_record(list_path):
    assert check.main([str(list_path)], phone=oneplus_phone()) == 2


# compose.py ------------------------------------------------------------------------------------

def test_compose_checklist_shows_ask_groups_with_what_is_installed(list_path, capsys):
    code = compose.main([str(list_path), "--checklist"], phone=oneplus_phone())

    out = capsys.readouterr().out
    assert code == 0
    assert "OnePlus community" in out and "Red Cable Club" in out
    assert "Preloaded partner apps" in out
    assert "Unclear services" not in out.split("Expert")[0]


def test_compose_writes_a_list_without_dropped_groups_or_expert(list_path, tmp_path):
    out_path = tmp_path / "work" / "mine.txt"

    code = compose.main([str(list_path), "--drop-group", "Preloaded partner apps", "-o", str(out_path)],
                        phone=oneplus_phone())

    text = out_path.read_text()
    assert code == 0
    assert "com.heytap.mcs" in text and "com.oneplus.membership" in text
    assert "com.netflix.partner.activation" not in text
    assert "com.coloros.childrenspace" not in text
    assert "Dropped groups: Preloaded partner apps" in text


def test_compose_offline_keeps_packages_it_cannot_check(list_path, tmp_path):
    out_path = tmp_path / "mine.txt"

    assert compose.main([str(list_path), "--offline", "--include-expert", "-o", str(out_path)]) == 0
    assert "com.coloros.childrenspace" in out_path.read_text()


def test_compose_drops_packages_not_on_the_phone(tmp_path):
    source = write(tmp_path / "l.txt", "# == G [safe]\ncom.heytap.mcs\ncom.not.on.phone\n")
    out_path = tmp_path / "mine.txt"

    compose.main([str(source), "-o", str(out_path)], phone=oneplus_phone())

    body = [line for line in out_path.read_text().splitlines() if not line.startswith("#")]
    assert "com.not.on.phone" not in body


# probe.py --------------------------------------------------------------------------------------

def test_probe_suggests_matching_lists_and_examples(tmp_path, capsys):
    write(tmp_path / "lists" / "brands" / "oneplus" / "oxygenos-14.txt",
          "# @brands: oneplus\n# @sdk: 33-35\n# == G [safe]\ncom.heytap.mcs\n")
    write(tmp_path / "lists" / "brands" / "samsung" / "oneui-6.txt", "# @brands: samsung\n")
    write(tmp_path / "lists" / "carriers" / "it-tim.txt", "# @brands: any\n# @carriers: tim\n")
    write(tmp_path / "lists" / "carriers" / "it-vodafone.txt", "# @brands: any\n# @carriers: vodafone\n")
    write(tmp_path / "examples" / "oneplus-8t" / "phone.json",
          json.dumps({"phone": "OnePlus 8T", "brand": "OnePlus", "models": ["KB2003"], "device": "OnePlus8T",
                      "os": "Android 14", "notes": ""}))
    write(tmp_path / "examples" / "oneplus-8t" / "debloat.txt", "# == G [safe]\ncom.heytap.mcs\n")

    code = probe.main(["--root", str(tmp_path)], phone=oneplus_phone())

    out = capsys.readouterr().out
    assert code == 0
    assert "OxygenOS V14.0.0" in out
    assert "oxygenos-14.txt" in out and "it-tim.txt" in out
    assert "oneui-6.txt" not in out and "it-vodafone.txt" not in out
    assert "examples/oneplus-8t/debloat.txt" in out


def test_probe_warns_about_other_users(capsys):
    phone = oneplus_phone()
    phone.users = [(0, "Owner"), (10, "Work profile")]

    probe.main([], phone=phone)

    assert "user 0" in capsys.readouterr().out


# backup.py and screenshot.py ------------------------------------------------------------------

def test_backup_writes_packages_settings_and_props(tmp_path):
    out = tmp_path / "backup"

    code = backup.main(["--out", str(out)], phone=oneplus_phone())

    folder = next(out.iterdir())
    names = {p.name for p in folder.iterdir()}
    assert code == 0
    assert {"getprop.txt", "packages-enabled.txt", "packages-disabled.txt", "packages-system.txt",
            "settings-secure.txt", "in-use.txt", "info.json"} <= names
    assert "com.coloros.childrenspace" in (folder / "packages-disabled.txt").read_text()


def test_screenshot_saves_png_and_flags_a_blank_capture(tmp_path, capsys):
    phone = oneplus_phone()
    assert screenshot.main([str(tmp_path / "a.png")], phone=phone) == 0
    assert (tmp_path / "a.png").read_bytes().startswith(b"\x89PNG")

    phone.screen = b""
    assert screenshot.main([str(tmp_path / "b.png")], phone=phone) == 1
    assert "blocks" in capsys.readouterr().err


def test_after_a_restore_check_does_not_turn_things_off_again(list_path):
    phone = oneplus_phone()
    disable.main([str(list_path), "--apply"], phone=phone)

    restore.main([str(list_path), "--group", "OnePlus community"], phone=phone)

    assert recovery.load(phone.serial, list_path).packages["com.oneplus.membership"].method is None
    assert check.main([str(list_path), "--fix"], phone=phone) == 0
    assert phone.packages["com.oneplus.membership"]["state"] == "enabled"


def test_restore_a_package_that_is_in_the_record_but_no_longer_in_the_list(list_path):
    phone = oneplus_phone()
    disable.main([str(list_path), "--apply"], phone=phone)
    list_path.write_text(LIST.replace("com.oneplus.membership       # Red Cable Club\n", ""))

    assert restore.main([str(list_path), "--package", "com.oneplus.membership"], phone=phone) == 0
    assert phone.packages["com.oneplus.membership"]["state"] == "enabled"


def test_disable_reports_an_interrupted_run_and_how_to_undo_it(list_path, capsys):
    phone = oneplus_phone()
    original = phone._disable

    def unplugged(pkg):
        if pkg == "com.heytap.mcs":
            raise AdbError("the phone FAKE123 disconnected.")
        return original(pkg)
    phone._disable = unplugged

    code = disable.main([str(list_path), "--apply"], phone=phone)

    out = capsys.readouterr().out
    assert code == 1
    assert "interrupted" in out and "not attempted" in out
    assert "restore.py" in out
