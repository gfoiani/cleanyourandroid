"""Planning, applying and undoing a list. These are the tests that keep a phone safe."""
import pytest

import actions
import device
import guards
import listfile
import recovery
from adb import AdbError, ShellResult
from helpers import oneplus_phone, write

STATE_CHANGING = ("pm disable-user", "pm enable", "pm uninstall", "cmd package install-existing")


def changes(phone):
    return [c for c in phone.commands if c.startswith(STATE_CHANGING)]


@pytest.fixture
def guard_set(tmp_path):
    write(tmp_path / "g" / "core.txt", "android\ncom.android.phone   # calls and SIM\n")
    return guards.load(tmp_path / "g")


@pytest.fixture(autouse=True)
def records(tmp_path, monkeypatch):
    monkeypatch.setenv("CLEANYOURANDROID_HOME", str(tmp_path / "records"))


def entries(*packages):
    return listfile.parse("# == Test [safe]\n" + "\n".join(packages) + "\n").entries


def make_plan(phone, guard_set, *packages):
    return actions.plan(entries(*packages), device.read_states(phone), guard_set, device.in_use(phone))


def test_plan_sorts_every_package_into_exactly_one_bucket(guard_set):
    phone = oneplus_phone(packages={"com.android.phone": {"system": True, "state": "enabled"}})

    plan = make_plan(phone, guard_set, "com.heytap.mcs", "com.android.phone", "com.android.launcher",
                     "com.coloros.childrenspace", "com.not.installed", "com.example.userapp")

    assert plan.to_change == ("com.heytap.mcs", "com.example.userapp")
    assert plan.protected == {"com.android.phone": "calls and SIM"}
    assert "default home" in plan.in_use["com.android.launcher"]
    assert plan.already == ("com.coloros.childrenspace",)
    assert plan.absent == ("com.not.installed",)
    assert plan.user_apps == ("com.example.userapp",)


def test_apply_disables_and_records_the_method(guard_set, tmp_path):
    phone = oneplus_phone()
    plan = make_plan(phone, guard_set, "com.heytap.mcs", "com.oneplus.membership")
    record = recovery.save(phone.serial, tmp_path / "l.txt", {"com.heytap.mcs": "enabled",
                                                             "com.oneplus.membership": "enabled"})

    result = actions.apply(phone, plan, record, fallback_uninstall=False)

    assert [o.action for o in result.outcomes] == ["disabled", "disabled"]
    assert phone.packages["com.heytap.mcs"]["state"] == "disabled"
    assert result.record.packages["com.heytap.mcs"].method == "disable"
    assert result.ok


def test_a_refused_disable_without_fallback_never_uninstalls(guard_set, tmp_path):
    phone = oneplus_phone(refuse_disable={"com.heytap.mcs"})
    plan = make_plan(phone, guard_set, "com.heytap.mcs")
    record = recovery.save(phone.serial, tmp_path / "l.txt", {"com.heytap.mcs": "enabled"})

    result = actions.apply(phone, plan, record, fallback_uninstall=False)

    assert result.outcomes[0].action == "refused"
    assert not any(c.startswith("pm uninstall") for c in phone.commands)
    assert phone.packages["com.heytap.mcs"]["state"] == "enabled"
    assert not result.ok


def test_fallback_uninstall_keeps_data_and_is_recorded(guard_set, tmp_path):
    phone = oneplus_phone(refuse_disable={"com.heytap.mcs"})
    plan = make_plan(phone, guard_set, "com.heytap.mcs")
    record = recovery.save(phone.serial, tmp_path / "l.txt", {"com.heytap.mcs": "enabled"})

    result = actions.apply(phone, plan, record, fallback_uninstall=True)

    assert "pm uninstall -k --user 0 com.heytap.mcs" in phone.commands
    assert result.outcomes[0].action == "uninstalled"
    assert result.record.packages["com.heytap.mcs"].method == "uninstall"
    assert phone.packages["com.heytap.mcs"]["state"] == "uninstalled"


def test_fallback_never_uninstalls_a_user_installed_app(guard_set, tmp_path):
    # Removing an app that is not part of the system image deletes the APK: nothing could bring it back.
    phone = oneplus_phone(refuse_disable={"com.example.userapp"})
    plan = make_plan(phone, guard_set, "com.example.userapp")
    record = recovery.save(phone.serial, tmp_path / "l.txt", {"com.example.userapp": "enabled"})

    result = actions.apply(phone, plan, record, fallback_uninstall=True)

    assert not any(c.startswith("pm uninstall") for c in phone.commands)
    assert result.outcomes[0].action == "refused"
    assert "com.example.userapp" in phone.packages


def test_protected_and_in_use_packages_never_reach_the_phone(guard_set, tmp_path):
    phone = oneplus_phone(packages={"com.android.phone": {"system": True, "state": "enabled"}})
    plan = make_plan(phone, guard_set, "com.android.phone", "com.android.launcher",
                     "com.touchtype.swiftkey")
    record = recovery.save(phone.serial, tmp_path / "l.txt", {})

    actions.apply(phone, plan, record, fallback_uninstall=True)

    assert changes(phone) == []


def test_apply_reports_a_change_the_phone_did_not_keep(guard_set, tmp_path):
    phone = oneplus_phone()
    plan = make_plan(phone, guard_set, "com.heytap.mcs")
    record = recovery.save(phone.serial, tmp_path / "l.txt", {"com.heytap.mcs": "enabled"})
    original = phone._disable
    phone._disable = lambda pkg: (original(pkg), phone.packages[pkg].update(state="enabled"))[0]

    result = actions.apply(phone, plan, record, fallback_uninstall=False)

    assert result.outcomes[0].action == "unverified"
    assert not result.ok


def test_restore_puts_back_exactly_the_state_before(guard_set, tmp_path):
    phone = oneplus_phone(refuse_disable={"com.heytap.mcs"})
    list_path = tmp_path / "l.txt"
    plan = make_plan(phone, guard_set, "com.heytap.mcs", "com.oneplus.membership")
    before = {p: device.read_states(phone).state(p)
              for p in ("com.heytap.mcs", "com.oneplus.membership", "com.coloros.childrenspace")}
    record = recovery.save(phone.serial, list_path, before)
    actions.apply(phone, plan, record, fallback_uninstall=True)

    outcomes = actions.restore(phone, recovery.load(phone.serial, list_path))

    assert phone.packages["com.heytap.mcs"]["state"] == "enabled"
    assert phone.packages["com.oneplus.membership"]["state"] == "enabled"
    # Disabled before the run: restore leaves it as the owner had it.
    assert phone.packages["com.coloros.childrenspace"]["state"] == "disabled"
    assert "cmd package install-existing --user 0 com.heytap.mcs" in phone.commands
    assert {o.package: o.action for o in outcomes}["com.coloros.childrenspace"] == "unchanged"


def test_drift_lists_what_an_update_turned_back_on(guard_set, tmp_path):
    phone = oneplus_phone()
    list_path = tmp_path / "l.txt"
    plan = make_plan(phone, guard_set, "com.heytap.mcs", "com.oneplus.membership")
    record = recovery.save(phone.serial, list_path, {"com.heytap.mcs": "enabled",
                                                      "com.oneplus.membership": "enabled"})
    actions.apply(phone, plan, record, fallback_uninstall=False)
    phone.packages["com.heytap.mcs"]["state"] = "enabled"  # an OTA re-enabled it

    found = actions.drift(entries("com.heytap.mcs", "com.oneplus.membership"), device.read_states(phone))

    assert found == ("com.heytap.mcs",)


def saved(phone, tmp_path, *packages):
    return recovery.save(phone.serial, tmp_path / "l.txt",
                         {p: device.read_states(phone).state(p) for p in packages})


def test_fallback_never_uninstalls_an_updated_system_app(guard_set, tmp_path):
    # Removing it for user 0 would also drop the update: it would come back as the factory version.
    phone = oneplus_phone(refuse_disable={"com.google.android.youtube"})
    plan = make_plan(phone, guard_set, "com.google.android.youtube")

    result = actions.apply(phone, plan, saved(phone, tmp_path, "com.google.android.youtube"),
                           fallback_uninstall=True)

    assert plan.updated_system == ("com.google.android.youtube",)
    assert not any(c.startswith("pm uninstall") for c in phone.commands)
    assert result.outcomes[0].action == "refused"
    assert "updated" in result.outcomes[0].detail


def test_the_intent_is_recorded_before_the_command_is_sent(guard_set, tmp_path):
    phone = oneplus_phone()
    plan = make_plan(phone, guard_set, "com.heytap.mcs")
    record = saved(phone, tmp_path, "com.heytap.mcs")
    seen = []
    original = phone._disable

    def disable_and_peek(pkg):
        seen.append(recovery.load(phone.serial, tmp_path / "l.txt").packages[pkg].method)
        return original(pkg)
    phone._disable = disable_and_peek

    actions.apply(phone, plan, record, fallback_uninstall=False)

    assert seen == ["disable"]


def test_a_refusal_clears_the_recorded_intent(guard_set, tmp_path):
    phone = oneplus_phone(refuse_disable={"com.heytap.mcs"})
    plan = make_plan(phone, guard_set, "com.heytap.mcs")

    result = actions.apply(phone, plan, saved(phone, tmp_path, "com.heytap.mcs"), fallback_uninstall=False)

    assert result.record.packages["com.heytap.mcs"].method is None


def test_a_connection_lost_midway_reports_what_happened(guard_set, tmp_path):
    phone = oneplus_phone()
    plan = make_plan(phone, guard_set, "com.heytap.mcs", "com.oneplus.membership", "com.oplus.statistics.rom")
    record = saved(phone, tmp_path, "com.heytap.mcs", "com.oneplus.membership", "com.oplus.statistics.rom")
    original = phone._disable

    def unplugged(pkg):
        if pkg == "com.oneplus.membership":
            raise AdbError("the phone 0a1b2c3d disconnected.")
        return original(pkg)
    phone._disable = unplugged

    result = actions.apply(phone, plan, record, fallback_uninstall=False)

    actions_by_package = {o.package: o.action for o in result.outcomes}
    assert actions_by_package == {"com.heytap.mcs": "disabled", "com.oneplus.membership": "interrupted",
                                  "com.oplus.statistics.rom": "not attempted"}
    assert not result.ok
    # Unknown whether it changed: the record keeps the intent, so restore will check it.
    assert recovery.load(phone.serial, tmp_path / "l.txt").packages["com.oneplus.membership"].method == "disable"


def test_a_disable_that_worked_with_unusual_output_is_not_uninstalled(guard_set, tmp_path):
    phone = oneplus_phone()
    plan = make_plan(phone, guard_set, "com.heytap.mcs")
    original = phone._disable
    phone._disable = lambda pkg: (original(pkg), ShellResult(0, "ok\n"))[1]

    result = actions.apply(phone, plan, saved(phone, tmp_path, "com.heytap.mcs"), fallback_uninstall=True)

    assert result.outcomes[0].action == "disabled"
    assert not any(c.startswith("pm uninstall") for c in phone.commands)


def test_commands_refuse_anything_that_is_not_a_package_name():
    with pytest.raises(listfile.ListError):
        actions.command(actions.ENABLE, "com.x; reboot")
