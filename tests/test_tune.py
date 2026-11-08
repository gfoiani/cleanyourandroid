"""tune.py end to end against FakePhone: battery settings, dry run first, every change undoable."""
import pytest

import tune
import tweakrecord
from adb import AdbError, ShellResult
from helpers import oneplus_phone, write

TWEAKS = """\
# @brands: any

# == Screen turns off sooner [ask]
system screen_off_timeout <=30000      # 30 seconds without a touch

# == Shorter animations [ask]
global window_animation_scale 0.5
global transition_animation_scale 0.5

# == Scanning while Wi-Fi is off [ask]
global wifi_scan_always_enabled 0
"""


def puts(phone):
    return [c for c in phone.commands if c.startswith(("settings put", "settings delete"))]


@pytest.fixture(autouse=True)
def records(tmp_path, monkeypatch):
    monkeypatch.setenv("CLEANYOURANDROID_HOME", str(tmp_path / "records"))


@pytest.fixture
def catalog(tmp_path):
    return tmp_path / "tweaks"


@pytest.fixture
def power(catalog):
    return write(catalog / "power.txt", TWEAKS)


def phone_with(refuse_settings=(), ignore_settings=(), **settings):
    """A phone with these settings namespaces; a namespace given here replaces the default one."""
    defaults = {"system": {"screen_off_timeout": "60000"},
                "global": {"window_animation_scale": "1.0", "transition_animation_scale": "1.0",
                           "wifi_scan_always_enabled": "1"}}
    return oneplus_phone(settings={**defaults, **settings}, refuse_settings=refuse_settings,
                         ignore_settings=ignore_settings)


def run(argv, phone, catalog):
    return tune.main(argv, phone=phone, catalog=catalog)


def test_without_apply_it_shows_each_value_and_changes_nothing(power, catalog, capsys):
    phone = phone_with()

    assert run([str(power)], phone, catalog) == 0

    assert puts(phone) == []
    assert tweakrecord.load(phone.serial, power) is None
    out = capsys.readouterr().out
    assert "Screen turns off sooner [ask]" in out
    assert "60000 -> 30000" in out and "Dry run" in out


def test_apply_needs_named_groups(power, catalog, capsys):
    phone = phone_with()

    assert run([str(power), "--apply"], phone, catalog) == 2

    assert puts(phone) == []
    assert "--group" in capsys.readouterr().err


def test_apply_changes_only_the_named_groups_and_records_the_values_first(power, catalog):
    phone = phone_with()

    code = run([str(power), "--apply", "--group", "shorter animations"], phone, catalog)

    assert code == 0
    assert puts(phone) == ["settings put global window_animation_scale 0.5",
                           "settings put global transition_animation_scale 0.5"]
    record = tweakrecord.load(phone.serial, power)
    assert record.settings["global/window_animation_scale"] == tweakrecord.SettingRecord("1.0", "0.5")
    assert phone.settings["system"]["screen_off_timeout"] == "60000"


def test_a_bound_never_makes_a_setting_worse(power, catalog, capsys):
    phone = phone_with(system={"screen_off_timeout": "15000"})

    assert run([str(power), "--apply", "--group", "Screen turns off sooner"], phone, catalog) == 0

    assert puts(phone) == []
    assert "already" in capsys.readouterr().out


def test_a_file_outside_the_reviewed_folder_is_refused(tmp_path, catalog, capsys):
    stray = write(tmp_path / "mine.txt", TWEAKS)
    phone = phone_with()

    assert run([str(stray), "--apply", "--group", "Shorter animations"], phone, catalog) == 2

    assert puts(phone) == []
    assert "tweaks/" in capsys.readouterr().err


def test_restore_puts_back_values_and_deletes_what_was_not_set(power, catalog):
    phone = phone_with(**{"global": {"window_animation_scale": "1.0"}})  # transition scale not set at all
    run([str(power), "--apply", "--group", "Shorter animations"], phone, catalog)

    assert run([str(power), "--restore"], phone, catalog) == 0

    assert phone.settings["global"]["window_animation_scale"] == "1.0"
    assert "transition_animation_scale" not in phone.settings["global"]
    assert "settings delete global transition_animation_scale" in phone.commands
    record = tweakrecord.load(phone.serial, power)
    assert all(s.applied is None for s in record.settings.values())


def test_restore_leaves_a_setting_the_person_changed_since(power, catalog, capsys):
    phone = phone_with()
    run([str(power), "--apply", "--group", "Screen turns off sooner"], phone, catalog)
    phone.settings["system"]["screen_off_timeout"] = "120000"   # changed in Settings afterwards

    assert run([str(power), "--restore"], phone, catalog) == 0

    assert phone.settings["system"]["screen_off_timeout"] == "120000"
    assert "changed since" in capsys.readouterr().out


def test_restore_without_a_record_changes_nothing(power, catalog, capsys):
    phone = phone_with()

    assert run([str(power), "--restore"], phone, catalog) == 2

    assert puts(phone) == []
    assert "No settings record" in capsys.readouterr().err


def test_a_refused_setting_is_reported_and_not_left_as_changed(power, catalog, capsys):
    phone = phone_with(refuse_settings={"global/wifi_scan_always_enabled"})

    code = run([str(power), "--apply", "--group", "Scanning while Wi-Fi is off"], phone, catalog)

    assert code == 1
    assert "refused" in capsys.readouterr().out
    assert tweakrecord.load(phone.serial, power).settings["global/wifi_scan_always_enabled"].applied is None


def test_a_permission_refusal_explains_the_switch_by_hand_not_the_protection(power, catalog, capsys):
    phone = phone_with(refuse_settings={"global/window_animation_scale", "global/transition_animation_scale"})

    code = run([str(power), "--apply", "--group", "Shorter animations"], phone, catalog)

    assert code == 1
    out = capsys.readouterr().out
    assert out.count("does not let a computer change") == 1
    assert "by hand" in out and "permission monitoring" in out
    assert phone.settings["global"]["window_animation_scale"] == "1.0"


def test_a_setting_not_written_yet_that_android_already_defaults_right_is_left_alone(catalog, capsys):
    tweaks = write(catalog / "power.txt", "# == Adaptive battery [ask]\n"
                                          "global adaptive_battery_management_enabled 1 default=1  # on by default\n")
    phone = phone_with()   # the key is not set at all, as on a OnePlus 8T

    assert run([str(tweaks), "--apply", "--group", "Adaptive battery"], phone, catalog) == 0

    assert puts(phone) == []
    assert "already 1 (not set: Android's default)" in capsys.readouterr().out


def test_a_setting_the_phone_does_not_keep_is_unverified(power, catalog, capsys):
    phone = phone_with(ignore_settings={"global/wifi_scan_always_enabled"})

    code = run([str(power), "--apply", "--group", "Scanning while Wi-Fi is off"], phone, catalog)

    assert code == 1
    assert "unverified" in capsys.readouterr().out


def test_a_cable_pulled_mid_run_stops_and_the_record_still_undoes_it(power, catalog, capsys):
    phone = phone_with()
    real_shell = phone.shell

    def shell(command):
        if command == "settings put global transition_animation_scale 0.5":
            raise AdbError("the phone did not answer within 90s")
        return real_shell(command)

    phone.shell = shell

    code = run([str(power), "--apply", "--group", "Shorter animations"], phone, catalog)

    assert code == 1
    assert "interrupted" in capsys.readouterr().out
    record = tweakrecord.load(phone.serial, power)
    assert record.settings["global/window_animation_scale"].applied == "0.5"
    assert record.settings["global/transition_animation_scale"].applied == "0.5"   # intent, for restore


def test_a_current_value_that_could_not_be_put_back_is_skipped(power, catalog, capsys):
    phone = phone_with(**{"global": {"wifi_scan_always_enabled": "on now"}})

    assert run([str(power), "--apply", "--group", "Scanning while Wi-Fi is off"], phone, catalog) == 0

    assert puts(phone) == []
    assert "cannot be recorded" in capsys.readouterr().out


def test_restore_one_group_leaves_the_others_changed(power, catalog):
    phone = phone_with()
    run([str(power), "--apply", "--group", "Shorter animations", "--group", "Screen turns off sooner"],
        phone, catalog)

    assert run([str(power), "--restore", "--group", "Screen turns off sooner"], phone, catalog) == 0

    assert phone.settings["system"]["screen_off_timeout"] == "60000"
    assert phone.settings["global"]["window_animation_scale"] == "0.5"


def test_a_restore_the_phone_refuses_is_reported_and_kept_for_next_time(power, catalog, capsys):
    phone = phone_with()
    run([str(power), "--apply", "--group", "Scanning while Wi-Fi is off"], phone, catalog)
    phone.refuse_settings.add("global/wifi_scan_always_enabled")

    assert run([str(power), "--restore"], phone, catalog) == 1

    assert "refused" in capsys.readouterr().out
    assert tweakrecord.load(phone.serial, power).settings["global/wifi_scan_always_enabled"].applied == "0"


def test_a_put_that_answers_with_an_error_but_changed_the_phone_stays_undoable(power, catalog):
    phone = phone_with()
    real_shell = phone.shell

    def shell(command):
        answer = real_shell(command)
        return ShellResult(255, "error: closed\n") if command.startswith("settings put") else answer

    phone.shell = shell
    run([str(power), "--apply", "--group", "Scanning while Wi-Fi is off"], phone, catalog)
    phone.shell = real_shell

    assert tweakrecord.load(phone.serial, power).settings["global/wifi_scan_always_enabled"].applied == "0"
    assert run([str(power), "--restore"], phone, catalog) == 0
    assert phone.settings["global"]["wifi_scan_always_enabled"] == "1"


def test_applying_again_after_the_person_changed_a_setting_restores_their_value(power, catalog):
    phone = phone_with()
    run([str(power), "--apply", "--group", "Screen turns off sooner"], phone, catalog)
    phone.settings["system"]["screen_off_timeout"] = "120000"   # chosen in Settings afterwards
    run([str(power), "--apply", "--group", "Screen turns off sooner"], phone, catalog)

    assert run([str(power), "--restore"], phone, catalog) == 0

    assert phone.settings["system"]["screen_off_timeout"] == "120000"


def test_kept_on_restore_does_not_lose_the_record(power, catalog):
    phone = phone_with()
    run([str(power), "--apply", "--group", "Screen turns off sooner"], phone, catalog)
    phone.settings["system"]["screen_off_timeout"] = "120000"

    run([str(power), "--restore"], phone, catalog)

    assert tweakrecord.load(phone.serial, power).settings["system/screen_off_timeout"].applied == "30000"


def test_an_empty_value_is_not_mistaken_for_not_set(power, catalog, capsys):
    phone = phone_with(**{"global": {"wifi_scan_always_enabled": ""}})

    assert run([str(power), "--apply", "--group", "Scanning while Wi-Fi is off"], phone, catalog) == 0

    assert puts(phone) == []
    assert "cannot be recorded" in capsys.readouterr().out


def test_an_interrupted_restore_reports_what_it_did_not_reach(power, catalog, capsys):
    phone = phone_with()
    run([str(power), "--apply", "--group", "Shorter animations"], phone, catalog)
    real_shell = phone.shell

    def shell(command):
        if command.startswith("settings put"):
            raise AdbError("the phone did not answer within 90s")
        return real_shell(command)

    phone.shell = shell

    assert run([str(power), "--restore"], phone, catalog) == 1

    out = capsys.readouterr().out
    assert "interrupted" in out and "not attempted" in out


def test_only_the_chosen_groups_are_read(power, catalog):
    phone = phone_with()

    run([str(power), "--group", "Shorter animations"], phone, catalog)

    assert not any("screen_off_timeout" in c for c in phone.commands)
