"""What the phone is, what state each package is in, and what the person is using right now.

Everything here only reads. Nothing in this module changes the phone.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

import tweakfile
from adb import ShellResult

PROPS = (
    "ro.product.brand", "ro.product.manufacturer", "ro.product.model", "ro.product.device",
    "ro.build.version.release", "ro.build.version.sdk", "ro.build.display.id",
    "ro.build.version.oplusrom", "ro.build.version.oneui", "ro.miui.ui.version.name",
    "ro.mi.os.version.name", "gsm.sim.operator.alpha",
)
PACKAGE_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+")
# Apps the person is using right now. A list entry naming one of them is skipped, never changed.
ROLES = {
    "HOME": "the default home screen",
    "DIALER": "the default phone app",
    "SMS": "the default SMS app",
    "ASSISTANT": "the default digital assistant",
    "CALL_SCREENING": "the call screening app",
    "CALL_REDIRECTION": "the call redirection app",
    "EMERGENCY": "the emergency information app",
}
# Without an answer for these, nothing is changed. Optional roles may be missing on older Android.
REQUIRED_ROLES = ("HOME", "DIALER", "SMS")
ROLE_FALLBACKS = {
    "HOME": "cmd package resolve-activity --brief -a android.intent.action.MAIN -c android.intent.category.HOME",
    "DIALER": "telecom get-default-dialer",
    "SMS": "settings get secure sms_default_application",
}
SECURE_SETTINGS = {
    "default_input_method": "the keyboard in use",
    "enabled_accessibility_services": "an accessibility service that is on",
    "autofill_service": "the password manager (autofill)",
    "enabled_notification_listeners": "an app that reads notifications (watch, car, automation)",
    "voice_interaction_service": "the voice assistant",
    "nfc_payment_default_component": "the default tap-to-pay app",
    "always_on_vpn_app": "the always-on VPN (with lockdown on, all data stops without it)",
}
OPLUS_SKINS = {"oneplus": "OxygenOS", "oppo": "ColorOS", "realme": "realme UI"}


class Phone(Protocol):
    serial: str

    def shell(self, command: str) -> ShellResult: ...


@dataclass(frozen=True)
class DeviceInfo:
    serial: str
    brand: str
    manufacturer: str
    model: str
    device: str
    android: str
    sdk: int
    build: str
    skin: str
    carrier: str


@dataclass(frozen=True)
class PackageStates:
    known: frozenset      # every package on the phone, also the ones uninstalled for user 0
    installed: frozenset  # installed for user 0
    disabled: frozenset
    system: frozenset
    updated: frozenset = frozenset()  # system packages running an update from /data/app

    def state(self, package: str) -> str:
        if package in self.disabled:
            return "disabled"
        if package in self.installed:
            return "enabled"
        if package in self.known:
            return "uninstalled"
        return "absent"


def getprops(phone: Phone) -> dict:
    return {name: phone.shell(f"getprop {name}").out.strip() for name in PROPS}


def detect_skin(props: dict) -> str:
    brand = props.get("ro.product.brand", "").lower()
    if props.get("ro.build.version.oneui"):
        code = props["ro.build.version.oneui"].rjust(5, "0")
        return f"One UI {int(code[:-4])}.{int(code[-4:-2])}.{int(code[-2:])}"
    if props.get("ro.mi.os.version.name"):
        return f"HyperOS {props['ro.mi.os.version.name']}"
    if props.get("ro.miui.ui.version.name"):
        return f"MIUI {props['ro.miui.ui.version.name']}"
    if props.get("ro.build.version.oplusrom"):
        return f"{OPLUS_SKINS.get(brand, 'ColorOS')} {props['ro.build.version.oplusrom']}"
    return "stock Android"


def read_info(phone: Phone) -> DeviceInfo:
    props = getprops(phone)
    sdk = props.get("ro.build.version.sdk", "")
    return DeviceInfo(
        serial=phone.serial,
        brand=props.get("ro.product.brand", ""),
        manufacturer=props.get("ro.product.manufacturer", ""),
        model=props.get("ro.product.model", ""),
        device=props.get("ro.product.device", ""),
        android=props.get("ro.build.version.release", ""),
        sdk=int(sdk) if sdk.isdigit() else 0,
        build=props.get("ro.build.display.id", ""),
        skin=detect_skin(props),
        carrier=props.get("gsm.sim.operator.alpha", "").strip(",").strip(),
    )


def parse_packages(text: str) -> frozenset:
    return frozenset(line[len("package:"):].strip() for line in text.splitlines()
                     if line.startswith("package:"))


def parse_package_paths(text: str) -> dict:
    """`pm list packages -f` output -> package -> APK path."""
    found = {}
    for line in text.splitlines():
        if line.startswith("package:") and "=" in line:
            path, _, name = line[len("package:"):].strip().rpartition("=")
            found[name] = path
    return found


def _shell_ok(phone: Phone, command: str, what: str) -> str:
    result = phone.shell(command)
    if not result.ok:
        raise RuntimeError(f"could not read {what}: {result.out.strip()}")
    return result.out


def read_states(phone: Phone) -> PackageStates:
    system_paths = parse_package_paths(_shell_ok(phone, "pm list packages --user 0 -s -u -f", "system packages"))
    return PackageStates(
        known=parse_packages(_shell_ok(phone, "pm list packages --user 0 -u", "all packages")),
        installed=parse_packages(_shell_ok(phone, "pm list packages --user 0", "installed packages")),
        disabled=parse_packages(_shell_ok(phone, "pm list packages --user 0 -d", "disabled packages")),
        system=frozenset(system_paths),
        updated=frozenset(name for name, path in system_paths.items() if path.startswith("/data/")),
    )


def read_setting(phone: Phone, namespace: str, key: str) -> str | None:
    """One setting's value; None when it is not set (`settings get` prints "null"). An empty value stays
    "", which is not "not set": callers that cannot record it leave the setting alone."""
    value = _shell_ok(phone, tweakfile.command("get", namespace, key), f"the setting {namespace}/{key}").strip()
    return None if value == "null" else value


def parse_admins(text: str) -> frozenset:
    """Packages listed under "Enabled Device Admins" in `dumpsys device_policy`, whatever the indent."""
    admins = set()
    header_indent = None
    for line in text.splitlines():
        indent = len(line) - len(line.lstrip())
        if "Enabled Device Admins" in line:
            header_indent = indent
            continue
        if header_indent is None or not line.strip():
            continue
        if indent <= header_indent:
            break
        match = re.match(r"^\s+([A-Za-z_][\w.]*)/\S+:\s*$", line)
        if match:
            admins.add(match.group(1))
    return frozenset(admins)


def _packages_in(value: str) -> list:
    """Package names in a setting: `pkg/cls`, `pkg/cls:pkg2/cls2`, or a bare `pkg`; nothing for null."""
    names = []
    for item in value.strip().split(":"):
        name = item.split("/")[0].strip()
        if name and name != "null" and PACKAGE_NAME_RE.fullmatch(name):
            names.append(name)
    return names


def _role_holders(phone: Phone, role: str) -> list | None:
    """Holders of a role; None when the phone could not say (no `cmd role`, an error)."""
    result = phone.shell(f"cmd role get-role-holders --user 0 android.app.role.{role}")
    if result.ok:
        return [p for p in result.out.split() if PACKAGE_NAME_RE.fullmatch(p)]
    fallback = ROLE_FALLBACKS.get(role)
    if fallback is None:
        return None
    answer = phone.shell(fallback)
    if not answer.ok:
        return None
    return [line.split("/")[0].strip() for line in answer.out.splitlines()
            if PACKAGE_NAME_RE.fullmatch(line.split("/")[0].strip())]


def _owners(phone: Phone) -> list:
    result = phone.shell("dpm list-owners")
    return re.findall(r"admin=([A-Za-z_][\w.]*)/", result.out) if result.ok else []


def in_use(phone: Phone) -> dict:
    """package -> why it must stay. Stops (RuntimeError) when it cannot tell what the home screen is,
    or what the phone and SMS apps are: doubt means do nothing."""
    found: dict = {}

    def add(package: str, reason: str) -> None:
        found[package] = f"{found[package]}; {reason}" if package in found else reason

    for role, reason in ROLES.items():
        holders = _role_holders(phone, role)
        if holders is None and role in REQUIRED_ROLES:
            raise RuntimeError(f"could not tell which app is {reason}; stopping so nothing it needs is touched")
        if role == "HOME" and not holders:
            raise RuntimeError("could not tell which app is the home screen; stopping so it is not touched")
        for package in holders or []:
            add(package, reason)
    for setting, reason in SECURE_SETTINGS.items():
        for package in _packages_in(phone.shell(f"settings get secure {setting}").out):
            add(package, reason)
    for package in sorted(parse_admins(phone.shell("dumpsys device_policy").out)):
        add(package, "an active device admin")
    for package in _owners(phone):
        add(package, "the device or profile owner (a managed phone)")
    return found
