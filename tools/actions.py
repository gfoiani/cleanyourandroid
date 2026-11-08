"""Plan, apply, undo and check a list. The only module that sends state-changing commands.

The commands it may send, and nothing else:

    pm disable-user --user 0 <pkg>              the default: reversible, keeps all data
    pm uninstall -k --user 0 <pkg>              only with fallback on, only for system packages, -k keeps data
    pm enable --user 0 <pkg>                    restore
    cmd package install-existing --user 0 <pkg> restore after an uninstall
    settings put <namespace> <key> <value>      a setting from tweaks/, after its old value is recorded
    settings delete <namespace> <key>           restore a setting that was not set before

Never `pm clear`, never `pm uninstall` without `-k --user 0`, never on a package outside the system
image (that would delete the APK and nothing could bring it back).
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import NamedTuple

import device
import guards
import listfile
import recovery
import tweakfile
import tweakrecord
from adb import AdbError, ShellResult

DISABLE = "pm disable-user --user 0 {}"
UNINSTALL_KEEP_DATA = "pm uninstall -k --user 0 {}"
ENABLE = "pm enable --user 0 {}"
INSTALL_EXISTING = "cmd package install-existing --user 0 {}"
SUCCESSFUL = ("disabled", "uninstalled")
# What can go wrong while talking to the phone or writing the record, mid-run.
RUN_ERRORS = (AdbError, RuntimeError, OSError, recovery.RecoveryError)


class Outcome(NamedTuple):
    package: str
    action: str   # disabled, uninstalled, refused, unverified, interrupted, not attempted,
                  # enabled, reinstalled, unchanged, missing
    detail: str = ""


@dataclass(frozen=True)
class Plan:
    to_change: tuple
    protected: Mapping
    in_use: Mapping
    already: tuple
    absent: tuple
    user_apps: tuple
    updated_system: tuple = ()


@dataclass(frozen=True)
class ApplyResult:
    outcomes: tuple
    record: recovery.Record

    @property
    def ok(self) -> bool:
        return all(o.action in SUCCESSFUL for o in self.outcomes)


def command(template: str, package: str) -> str:
    """The one place a package name goes into a shell command: anything but a package name is refused."""
    if not listfile.PACKAGE_RE.fullmatch(package):
        raise listfile.ListError(f"refusing to send a command for {package!r}: not a package name")
    return template.format(package)


def plan(entries: Iterable[listfile.Entry], states: device.PackageStates, guard_set: tuple,
         using: Mapping) -> Plan:
    to_change, already, absent = [], [], []
    protected_found, in_use_found = {}, {}
    for entry in entries:
        package = entry.package
        guard = guards.match(package, guard_set)
        state = states.state(package)
        if guard is not None:
            protected_found[package] = guard.reason
        elif package in using:
            in_use_found[package] = using[package]
        elif state == "enabled":
            to_change.append(package)
        elif state in ("disabled", "uninstalled"):
            already.append(package)
        else:
            absent.append(package)
    user_apps = tuple(p for p in to_change if p not in states.system)
    updated_system = tuple(p for p in to_change if p in states.updated)
    return Plan(tuple(to_change), protected_found, in_use_found, tuple(already), tuple(absent), user_apps,
                updated_system)


def _why(out: str) -> str:
    lines = [line.strip() for line in out.splitlines() if line.strip() and not line.strip().startswith("at ")]
    for line in lines:
        if line.startswith(("java.", "Failure", "Error")):
            return line
    return lines[-1] if lines else "no answer"


def _no_uninstall_reason(package: str, the_plan: Plan) -> str:
    if package in the_plan.user_apps:
        return "not uninstalled: it is not a system app, so removing it would delete it for good"
    if package in the_plan.updated_system:
        return ("not uninstalled: it is an updated system app, and removing it would also remove the update "
                "(it would come back as the factory version)")
    return ""


def _change_one(phone: device.Phone, package: str, may_uninstall: bool) -> Outcome:
    answer = phone.shell(command(DISABLE, package))
    if answer.ok and "new state: disabled" in answer.out:
        return Outcome(package, "disabled")
    if answer.ok and device.read_states(phone).state(package) == "disabled":
        return Outcome(package, "disabled")  # worked, with output this firmware words differently
    refusal = _why(answer.out)
    if not may_uninstall:
        return Outcome(package, "refused", refusal)
    answer = phone.shell(command(UNINSTALL_KEEP_DATA, package))
    if answer.ok and "Success" in answer.out:
        return Outcome(package, "uninstalled", f"disable was refused: {refusal}")
    return Outcome(package, "refused", f"{refusal}; uninstall for user 0 also failed: {_why(answer.out)}")


def apply(phone: device.Phone, the_plan: Plan, record: recovery.Record, fallback_uninstall: bool) -> ApplyResult:
    """Change every package in the plan, one command each; the record must already hold all of them.

    The intent is written to the record before each command, so a crash or a pulled cable at any point
    leaves a record that restore can act on. A failure mid-run stops the run and is reported per package.
    """
    outcomes: list = []
    pending = list(the_plan.to_change)
    while pending:
        package = pending.pop(0)
        if package not in record.packages:
            outcomes.append(Outcome(package, "refused", "not in the recovery record, so it could not be undone"))
            continue
        blocked = _no_uninstall_reason(package, the_plan)
        may_uninstall = fallback_uninstall and not blocked
        try:
            record = recovery.with_method(record, package, "uninstall" if may_uninstall else "disable")
        except RUN_ERRORS as error:
            outcomes += [Outcome(p, "not attempted", f"could not write the recovery record: {error}")
                         for p in [package, *pending]]
            break
        try:
            outcome = _change_one(phone, package, may_uninstall)
        except RUN_ERRORS as error:
            outcomes.append(Outcome(package, "interrupted", f"{error}; restore.py will check it"))
            outcomes += [Outcome(p, "not attempted", "the run stopped before it") for p in pending]
            break
        record = _note(record, outcome)
        if outcome.action == "refused" and fallback_uninstall and blocked:
            outcome = outcome._replace(detail=f"{outcome.detail}; {blocked}")
        outcomes.append(outcome)
    return ApplyResult(_verify(phone, outcomes), record)


def _note(record: recovery.Record, outcome: Outcome) -> recovery.Record:
    method = {"disabled": "disable", "uninstalled": "uninstall"}.get(outcome.action)
    try:
        return recovery.with_method(record, outcome.package, method)
    except RUN_ERRORS:
        return record  # the intent written before the command still lets restore check this package


def _verify(phone: device.Phone, outcomes: list) -> tuple:
    """Read the phone again: a change it did not keep is reported, not counted."""
    if not any(o.action in SUCCESSFUL for o in outcomes):
        return tuple(outcomes)
    try:
        states = device.read_states(phone)
    except RUN_ERRORS as error:
        return tuple(o._replace(action="unverified", detail=f"could not read the phone back: {error}")
                     if o.action in SUCCESSFUL else o for o in outcomes)
    checked = []
    for outcome in outcomes:
        now = states.state(outcome.package)
        if outcome.action in SUCCESSFUL and now != outcome.action:
            outcome = Outcome(outcome.package, "unverified", f"the phone reports it {now} after the change")
        checked.append(outcome)
    return tuple(checked)


def restore(phone: device.Phone, record: recovery.Record) -> tuple:
    """Put back the state each package had before; never disables or removes anything."""
    states = device.read_states(phone)
    outcomes = []
    for package, entry in record.packages.items():
        now = states.state(package)
        if entry.before != "enabled" or now == "enabled":
            outcomes.append(Outcome(package, "unchanged"))
        elif now == "disabled":
            answer = phone.shell(command(ENABLE, package))
            outcomes.append(Outcome(package, "enabled" if answer.ok else "refused", _why(answer.out)))
        elif now == "uninstalled":
            answer = phone.shell(command(INSTALL_EXISTING, package))
            outcomes.append(Outcome(package, "reinstalled" if answer.ok else "refused", _why(answer.out)))
        else:
            outcomes.append(Outcome(package, "missing", "no longer on the phone (removed by an update?)"))
    after = device.read_states(phone)
    return tuple(Outcome(o.package, "unverified", f"still {after.state(o.package)}")
                 if o.action in ("enabled", "reinstalled") and after.state(o.package) != "enabled" else o
                 for o in outcomes)


def drift(entries: Iterable[listfile.Entry], states: device.PackageStates,
          record: recovery.Record | None = None) -> tuple:
    """Listed packages that are enabled again; with a record, only the ones this repo had changed."""
    changed = None if record is None else {n for n, p in record.packages.items() if p.method}
    return tuple(e.package for e in entries
                 if states.state(e.package) == "enabled" and (changed is None or e.package in changed))


# Settings (tweaks/) -----------------------------------------------------------------------------

class SettingOutcome(NamedTuple):
    name: str
    action: str   # set, refused, unverified, interrupted, not attempted, restored, kept
    detail: str = ""


def _write_setting(phone: device.Phone, name: str, value: str | None) -> ShellResult:
    """Put `value`, or delete the setting when `value` is None (it was not set before)."""
    namespace, _, key = name.partition("/")
    if value is None:
        return phone.shell(tweakfile.command("delete", namespace, key))
    return phone.shell(tweakfile.command("put", namespace, key, value))


def _read_setting(phone: device.Phone, name: str) -> str | None:
    namespace, _, key = name.partition("/")
    return device.read_setting(phone, namespace, key)


def _after_error(phone: device.Phone, tweak: tweakfile.Tweak, record: tweakrecord.Record,
                 answer: ShellResult) -> tuple:
    """An error answer does not prove nothing changed: read the phone before forgetting the intent."""
    try:
        now = _read_setting(phone, tweak.name)
    except RUN_ERRORS:
        return SettingOutcome(tweak.name, "refused", f"{_why(answer.out)}; --restore will check it"), record
    if tweakfile.same(now, tweak.value):
        return SettingOutcome(tweak.name, "set", f"{tweak.value} (the phone answered with an error)"), record
    if tweakfile.same(now, record.settings[tweak.name].before):
        record = _forget(record, tweak.name)
    return SettingOutcome(tweak.name, "refused", _why(answer.out)), record


def _forget(record: tweakrecord.Record, name: str) -> tweakrecord.Record:
    try:
        return tweakrecord.with_applied(record, name, None)
    except RUN_ERRORS:
        return record  # the intent stays; restore reads the phone before it acts


def apply_settings(phone: device.Phone, tweaks: Iterable[tweakfile.Tweak],
                   record: tweakrecord.Record) -> tuple:
    """Write each setting, the intent recorded first; returns (outcomes, record)."""
    outcomes: list = []
    pending = list(tweaks)
    wanted = {t.name: t.value for t in pending}
    while pending:
        tweak = pending.pop(0)
        try:
            record = tweakrecord.with_applied(record, tweak.name, tweak.value)
        except RUN_ERRORS as error:
            outcomes += [SettingOutcome(t.name, "not attempted", f"could not write the settings record: {error}")
                         for t in [tweak, *pending]]
            break
        try:
            answer = _write_setting(phone, tweak.name, tweak.value)
        except RUN_ERRORS as error:
            outcomes.append(SettingOutcome(tweak.name, "interrupted", f"{error}; --restore will check it"))
            outcomes += [SettingOutcome(t.name, "not attempted", "the run stopped before it") for t in pending]
            break
        if answer.ok:
            outcomes.append(SettingOutcome(tweak.name, "set", tweak.value))
        else:
            outcome, record = _after_error(phone, tweak, record, answer)
            outcomes.append(outcome)
    return _verify_settings(phone, outcomes, wanted), record


def _verify_settings(phone: device.Phone, outcomes: list, wanted: Mapping) -> tuple:
    """Read each written setting back: a value the phone did not keep is reported, not counted."""
    checked = []
    for outcome in outcomes:
        if outcome.action in ("set", "restored"):
            try:
                now = _read_setting(phone, outcome.name)
            except RUN_ERRORS as error:
                outcome = outcome._replace(action="unverified", detail=f"could not read it back: {error}")
            else:
                if not tweakfile.same(now, wanted[outcome.name]):
                    outcome = outcome._replace(action="unverified", detail=f"the phone reports {now or 'not set'}")
        checked.append(outcome)
    return tuple(checked)


def restore_settings(phone: device.Phone, record: tweakrecord.Record, names: frozenset | None = None) -> tuple:
    """Put back each setting this repo changed (all, or `names`); returns (outcomes, record).

    A setting the person changed since is left as they set it: their choice is newer than ours. It stays
    in the record, so the next run still reports it, and the next --apply takes their value as "before".
    """
    outcomes: list = []
    wanted = {}
    pending = [(name, entry) for name, entry in record.settings.items()
               if entry.applied is not None and (names is None or name in names)]
    while pending:
        name, entry = pending.pop(0)
        try:
            now = _read_setting(phone, name)
            if not tweakfile.same(now, entry.applied):
                outcomes.append(SettingOutcome(name, "kept", f"changed since (now {now or 'not set'}); left as is"))
                continue
            answer = _write_setting(phone, name, entry.before)
        except RUN_ERRORS as error:
            outcomes.append(SettingOutcome(name, "interrupted", f"{error}; run --restore again"))
            outcomes += [SettingOutcome(n, "not attempted", "the run stopped before it") for n, _ in pending]
            break
        if not answer.ok:
            outcomes.append(SettingOutcome(name, "refused", _why(answer.out)))
            continue
        wanted[name] = entry.before
        outcomes.append(SettingOutcome(name, "restored", entry.before or "not set"))
    checked = _verify_settings(phone, outcomes, wanted)
    for outcome in checked:
        if outcome.action == "restored":
            record = _forget(record, outcome.name)
    return checked, record
