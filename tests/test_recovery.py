"""The recovery record: the state before the first change, so that restore means restore."""
import json

import pytest

import recovery
from recovery import RecoveryError


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("CLEANYOURANDROID_HOME", str(tmp_path / "records"))
    return tmp_path / "records"


def test_save_writes_the_state_before_any_change(home, tmp_path):
    list_path = tmp_path / "my.txt"

    record = recovery.save("FAKE123", list_path, {"com.example.a": "enabled", "com.example.b": "disabled"})

    stored = json.loads(recovery.path_for("FAKE123", list_path).read_text())
    assert stored["version"] == 1
    assert stored["serial"] == "FAKE123"
    assert stored["created"].endswith("Z")
    assert stored["packages"]["com.example.a"] == {"before": "enabled", "method": None}
    assert record.packages["com.example.b"].before == "disabled"
    assert recovery.path_for("FAKE123", list_path).parent.parent == home


def test_a_changed_package_keeps_its_first_state(home, tmp_path):
    list_path = tmp_path / "my.txt"
    first = recovery.save("FAKE123", list_path, {"com.example.a": "enabled"})
    recovery.with_method(first, "com.example.a", "disable")

    # A retry after a half-applied run sees com.example.a disabled: it must not become the original state.
    record = recovery.save("FAKE123", list_path, {"com.example.a": "disabled", "com.example.c": "enabled"})

    assert record.packages["com.example.a"].before == "enabled"
    assert record.packages["com.example.c"].before == "enabled"


def test_an_untouched_package_takes_its_current_state(home, tmp_path):
    # Recorded absent while another group was applied, installed later, then disabled by a later run:
    # without a refresh, restore would think it was never there and leave it off for good.
    list_path = tmp_path / "my.txt"
    recovery.save("FAKE123", list_path, {"com.example.a": "absent", "com.example.b": "disabled"})

    record = recovery.save("FAKE123", list_path, {"com.example.a": "enabled", "com.example.b": "enabled"})

    assert record.packages["com.example.a"].before == "enabled"
    assert record.packages["com.example.b"].before == "enabled"
    assert recovery.load("FAKE123", list_path).packages["com.example.a"].before == "enabled"


def test_with_method_none_clears_a_change(home, tmp_path):
    list_path = tmp_path / "my.txt"
    record = recovery.with_method(recovery.save("FAKE123", list_path, {"com.example.a": "enabled"}),
                                  "com.example.a", "disable")

    cleared = recovery.with_method(record, "com.example.a", None)

    assert cleared.packages["com.example.a"].method is None


def test_a_record_with_a_name_that_is_not_a_package_is_refused(home, tmp_path):
    list_path = tmp_path / "my.txt"
    recovery.save("FAKE123", list_path, {"com.example.a": "enabled"})
    path = recovery.path_for("FAKE123", list_path)
    path.write_text(path.read_text().replace("com.example.a", "com.x; reboot"))

    with pytest.raises(RecoveryError, match="not a package name"):
        recovery.load("FAKE123", list_path)


def test_a_record_with_the_wrong_shape_is_an_error(home, tmp_path):
    list_path = tmp_path / "my.txt"
    path = recovery.path_for("FAKE123", list_path)
    path.parent.mkdir(parents=True)
    path.write_text('{"version": 1, "serial": "x", "list": "y", "created": "z", "packages": []}')

    with pytest.raises(RecoveryError, match="cannot read"):
        recovery.load("FAKE123", list_path)


def test_with_method_returns_a_new_record_and_persists_it(home, tmp_path):
    list_path = tmp_path / "my.txt"
    original = recovery.save("FAKE123", list_path, {"com.example.a": "enabled"})

    updated = recovery.with_method(original, "com.example.a", "uninstall")

    assert original.packages["com.example.a"].method is None
    assert updated.packages["com.example.a"].method == "uninstall"
    assert recovery.load("FAKE123", list_path).packages["com.example.a"].method == "uninstall"


def test_records_are_separate_per_phone_and_per_list(home, tmp_path):
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"

    assert recovery.path_for("ONE", a) != recovery.path_for("TWO", a)
    assert recovery.path_for("ONE", a) != recovery.path_for("ONE", b)


def test_load_returns_none_when_there_is_no_record(home, tmp_path):
    assert recovery.load("FAKE123", tmp_path / "never.txt") is None


def test_a_corrupt_record_is_an_error_not_an_empty_record(home, tmp_path):
    list_path = tmp_path / "my.txt"
    path = recovery.path_for("FAKE123", list_path)
    path.parent.mkdir(parents=True)
    path.write_text("{not json")

    with pytest.raises(RecoveryError, match="cannot read"):
        recovery.load("FAKE123", list_path)
