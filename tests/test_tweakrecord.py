"""The settings record: the value each setting had before tune.py changed it."""
import json

import pytest

import tweakrecord
from recovery import RecoveryError


@pytest.fixture(autouse=True)
def records(tmp_path, monkeypatch):
    monkeypatch.setenv("CLEANYOURANDROID_HOME", str(tmp_path / "records"))


def test_save_records_values_and_the_path_is_per_phone_and_file(tmp_path):
    file = tmp_path / "power.txt"

    record = tweakrecord.save("SER", file, {"system/screen_off_timeout": "60000", "global/a_b": None})

    path = tweakrecord.path_for("SER", file)
    assert path.parent.name == "SER" and path.name.startswith("tweaks-power-")
    assert record.settings["global/a_b"] == tweakrecord.SettingRecord(None, None)
    assert tweakrecord.load("SER", file) == record


def test_a_changed_setting_keeps_its_first_value_and_unchanged_ones_refresh(tmp_path):
    file = tmp_path / "power.txt"
    record = tweakrecord.save("SER", file, {"system/x_y": "60000", "global/a_b": "1"})
    tweakrecord.with_applied(record, "system/x_y", "30000")

    again = tweakrecord.save("SER", file, {"system/x_y": "30000", "global/a_b": "0"})

    assert again.settings["system/x_y"] == tweakrecord.SettingRecord("60000", "30000")
    assert again.settings["global/a_b"] == tweakrecord.SettingRecord("0", None)


def test_with_applied_writes_to_disk_and_refuses_unknown_settings(tmp_path):
    file = tmp_path / "power.txt"
    record = tweakrecord.save("SER", file, {"system/x_y": "60000"})

    tweakrecord.with_applied(record, "system/x_y", "30000")

    assert tweakrecord.load("SER", file).settings["system/x_y"].applied == "30000"
    with pytest.raises(RecoveryError):
        tweakrecord.with_applied(record, "system/other", "1")


@pytest.mark.parametrize("settings", [
    {"system/x_y": {"before": "1; reboot", "applied": None}},
    {"bad name": {"before": "1", "applied": None}},
    {"system/x_y": {"before": "1"}},
])
def test_load_refuses_a_record_that_cannot_be_trusted(tmp_path, settings):
    file = tmp_path / "power.txt"
    path = tweakrecord.path_for("SER", file)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"version": 1, "serial": "SER", "file": str(file), "created": "",
                                "settings": settings}))

    with pytest.raises(RecoveryError):
        tweakrecord.load("SER", file)


def test_save_refuses_a_value_that_could_not_be_put_back(tmp_path):
    with pytest.raises(RecoveryError):
        tweakrecord.save("SER", tmp_path / "power.txt", {"system/x_y": "a b"})


def test_a_value_the_person_set_since_becomes_the_new_before(tmp_path):
    file = tmp_path / "power.txt"
    record = tweakrecord.save("SER", file, {"system/x_y": "60000"})
    tweakrecord.with_applied(record, "system/x_y", "30000")

    again = tweakrecord.save("SER", file, {"system/x_y": "120000"})   # chosen in Settings afterwards

    assert again.settings["system/x_y"] == tweakrecord.SettingRecord("120000", None)
