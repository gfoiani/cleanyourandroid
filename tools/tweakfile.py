"""Setting files (tweaks/*.txt): one Android setting per line, grouped and tiered like the debloat lists.

    # @brands: any
    # == Screen turns off sooner [ask]
    system screen_off_timeout <=30000      # trailing comment: what changes for the person

A line is `<namespace> <key> <value>`, namespace one of global, secure, system. A number may carry a
bound: `<=30000` means "at most 30000", so a phone already set shorter is left alone, and `>=20` means
"at least 20". A bound never makes a setting worse than the person already has it. Numbers compare
with a tiny tolerance: some phones store 60 Hz as 60.000004.

An optional `default=<value>` says what Android uses while the setting has never been written: a phone
where it is not set, and the default already is the value, is left alone instead of written.

    global adaptive_battery_management_enabled 1 default=1   # on unless someone turned it off

Names and values go into a shell command on the phone, so anything outside a small character set
refuses the whole file, with the file and line. Some settings are refused whatever the file says
(NEVER): the ones that keep the phone reachable, locked, updated, located or set up.
"""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import NamedTuple

import listfile
from listfile import ListError

NAMESPACES = ("global", "secure", "system")
VERBS = ("get", "put", "delete")
KEY_RE = re.compile(r"[a-z][a-z0-9_]*(\.[a-z0-9_]+)*")
VALUE_RE = re.compile(r"[A-Za-z0-9_.:-]{1,64}")
NUMBER_RE = re.compile(r"-?\d+(\.\d+)?", re.ASCII)
BOUNDS = ("<=", ">=")
DEFAULT = "default="
RELATIVE_TOLERANCE = 1e-6   # 60.000004 is 60
# Never changed by this repo, whatever a file says. A name ending in a dot or an underscore is a prefix;
# any other name also covers its numbered per-SIM copies (mobile_data -> mobile_data1, mobile_data2).
NEVER = {
    "adb_": "USB debugging: the way back to the phone",
    "usb_mass_storage_enabled": "USB storage",
    "development_settings_enabled": "Developer options",
    "airplane_mode_": "airplane mode: calls and emergency calls",
    "device_provisioned": "the phone's setup state",
    "user_setup_complete": "the phone's setup state",
    "private_dns_": "Private DNS is set from PROMPT.md, with the person's consent",
    "package_verifier_": "Play Protect app scanning",
    "verifier_verify_adb_installs": "Play Protect app scanning",
    "install_non_market_apps": "installing apps from unknown sources",
    "lockscreen.": "the lock screen",
    "lock_screen_": "the lock screen",
    "lock_pattern_": "the lock screen",
    "lock_biometric_": "fingerprint and face unlock",
    "lock_to_app_enabled": "app pinning",
    "location_": "location: emergency calls and Find My Device use it",
    "assisted_gps_enabled": "location: emergency calls and Find My Device use it",
    "emergency_": "emergency calls and alerts",
    "accessibility_enabled": "accessibility services the person relies on",
    "enabled_accessibility_services": "accessibility services the person relies on",
    "default_input_method": "the keyboard in use",
    "enabled_input_methods": "the keyboards in use",
    "enabled_notification_listeners": "apps that read notifications (watch, car)",
    "sms_default_application": "the default SMS app",
    "http_proxy": "a proxy would send all traffic elsewhere",
    "global_http_proxy_": "a proxy would send all traffic elsewhere",
    "auto_time": "the clock: wrong time breaks HTTPS, banking apps and alarms",
    "auto_time_zone": "the clock: wrong time breaks HTTPS, banking apps and alarms",
    "install_unknown_": "installing apps from unknown sources",
    "mobile_data": "mobile data",
    "data_roaming": "mobile data abroad",
    "wifi_on": "Wi-Fi",
    "bluetooth_on": "Bluetooth",
    "stay_on_while_plugged_in": "the screen staying on while charging",
}


class Tweak(NamedTuple):
    namespace: str
    key: str
    bound: str     # "", "<=" or ">="
    value: str
    group: str
    tier: str
    comment: str
    source: str
    default: str | None = None   # what Android uses while the setting is not set; None: unknown

    @property
    def name(self) -> str:
        return f"{self.namespace}/{self.key}"

    def satisfied_by(self, current: str | None) -> bool:
        """True when the phone already has this value, or a better one for a bounded setting."""
        if current is None:
            current = self.default
        if current is None or not self.bound or not NUMBER_RE.fullmatch(current):
            return same(current, self.value)
        now, wanted = float(current), float(self.value)
        if self.bound == "<=":
            # 0 and -1 mean "default" or "never" (never time out), not "very short"
            return 0 < now and (now <= wanted or _close(now, wanted))
        return now >= wanted or _close(now, wanted)


def _close(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=RELATIVE_TOLERANCE)


def same(current: str | None, value: str | None) -> bool:
    """Equal as settings: 0.5 and 0.50 are the same number; None is "not set"."""
    if current is None or value is None:
        return current == value
    if NUMBER_RE.fullmatch(current) and NUMBER_RE.fullmatch(value):
        return _close(float(current), float(value))
    return current == value


class TweakFile(NamedTuple):
    source: str
    meta: dict
    entries: tuple


def never_reason(key: str) -> str | None:
    for name, reason in NEVER.items():
        if name.endswith((".", "_")):
            if key.startswith(name):
                return reason
        elif re.fullmatch(re.escape(name) + r"\d*", key):
            return reason
    return None


def command(verb: str, namespace: str, key: str, value: str | None = None) -> str:
    """The one place a setting goes into a shell command: anything unexpected is refused."""
    if verb not in VERBS or namespace not in NAMESPACES or not KEY_RE.fullmatch(key):
        raise ListError(f"refusing to send `settings {verb} {namespace} {key}`: not a plain setting")
    if (verb == "put") != (value is not None) or (value is not None and not VALUE_RE.fullmatch(value)):
        raise ListError(f"refusing to send `settings {verb} {namespace} {key}` with value {value!r}")
    reason = never_reason(key)
    if verb != "get" and reason:
        raise ListError(f"refusing to change {key}: a setting this repo never changes ({reason})")
    return " ".join(part for part in ("settings", verb, namespace, key, value) if part is not None)


def _tweak(line: str, where: str, group: str, tier: str, source: str) -> Tweak:
    body, _, comment = line.partition("#")
    parts = body.split()
    if len(parts) not in (3, 4):
        raise ListError(f"{where}: expected `<namespace> <key> <value> [default=<value>]`: {body.strip()!r}")
    namespace, key, raw = parts[:3]
    default = _default(parts[3:], where, body)
    bound = next((b for b in BOUNDS if raw.startswith(b)), "")
    value = raw[len(bound):]
    if namespace not in NAMESPACES:
        raise ListError(f"{where}: the namespace is one of {', '.join(NAMESPACES)}: {namespace!r}")
    if not KEY_RE.fullmatch(key) or not VALUE_RE.fullmatch(value) or (bound and not NUMBER_RE.fullmatch(value)):
        raise ListError(f"{where}: not a plain setting and value: {body.strip()!r}")
    reason = never_reason(key)
    if reason:
        raise ListError(f"{where}: {key} is a setting this repo never changes ({reason})")
    return Tweak(namespace, key, bound, value, group, tier, comment.strip(), source, default)


def _default(extra: list, where: str, body: str) -> str | None:
    if not extra:
        return None
    word = extra[0]
    if not word.startswith(DEFAULT) or not VALUE_RE.fullmatch(word[len(DEFAULT):]):
        raise ListError(f"{where}: the only word after the value is {DEFAULT}<value>: {body.strip()!r}")
    return word[len(DEFAULT):]


def parse(text: str, source: str = "<text>") -> TweakFile:
    meta, lines = listfile.walk(text, source)
    entries: list = []
    seen: set = set()
    for where, line, group, tier in lines:
        tweak = _tweak(line, where, group, tier, source)
        if tweak.name in seen:
            raise ListError(f"{where}: {tweak.name} is listed twice")
        seen.add(tweak.name)
        entries.append(tweak)
    return TweakFile(source, meta, tuple(entries))


def load(path: Path | str) -> TweakFile:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ListError(f"cannot read the settings file {path}: {error}") from error
    return parse(text, source=str(path))
