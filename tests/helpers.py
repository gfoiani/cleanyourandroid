"""Shared test helpers: puts tools/ on the import path and provides a fake phone.

FakePhone answers the handful of shell commands the tools send, from an in-memory package table, so the
tests exercise the real parsing and the real safety checks without a device. Anything it does not
recognise raises, so a tool that starts sending a new command fails loudly here instead of passing.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from adb import ShellResult

HOME_RESOLVE = (r"cmd package resolve-activity --brief -a android\.intent\.action\.MAIN "
                r"-c android\.intent\.category\.HOME")
PM_ERROR = ("\nException occurred while executing 'disable-user':\n"
            "java.lang.SecurityException: Shell cannot change component state for {pkg} to 3\n")


class FakePhone:
    """An in-memory phone. packages: name -> dict(system=bool, state='enabled'|'disabled'|'uninstalled')."""

    def __init__(self, packages=None, props=None, roles=None, ime="", a11y="null", admins=(),
                 refuse_disable=(), refuse_uninstall=(), secure=None, owners=(), roles_unsupported=False,
                 settings=None, refuse_settings=(), ignore_settings=()):
        self.packages = {name: dict(info) for name, info in (packages or {}).items()}
        self.props = dict(props or {})
        self.roles = dict(roles or {})
        self.secure = {"default_input_method": ime, "enabled_accessibility_services": a11y, **(secure or {})}
        # namespace -> key -> value; a missing key reads as "null", like on a phone
        self.settings = {"global": {}, "system": {}, **{ns: dict(v) for ns, v in (settings or {}).items()}}
        self.settings["secure"] = self.secure
        self.refuse_settings = set(refuse_settings)   # "ns/key" the phone answers with an error
        self.ignore_settings = set(ignore_settings)   # "ns/key" the phone accepts and then does not keep
        self.admins = list(admins)
        self.owners = list(owners)
        self.roles_unsupported = roles_unsupported
        self.refuse_disable = set(refuse_disable)
        self.refuse_uninstall = set(refuse_uninstall)
        self.commands = []
        self.serial = "FAKE123"
        self.users = [(0, "Owner")]
        self.screen = b"\x89PNG fake"

    # The interface the tools use -------------------------------------------------------------
    def shell(self, command):
        self.commands.append(command)
        for pattern, handler in self._routes():
            match = re.fullmatch(pattern, command)
            if match:
                return handler(*match.groups())
        raise AssertionError(f"FakePhone does not know the command: {command!r}")

    # Routes ----------------------------------------------------------------------------------
    def _routes(self):
        return (
            (r"getprop ([\w.]+)", self._getprop),
            (r"pm list packages --user 0((?: -[dsuf3])*)", self._list),
            (r"pm disable-user --user 0 ([\w.]+)", self._disable),
            (r"pm enable --user 0 ([\w.]+)", self._enable),
            (r"pm uninstall -k --user 0 ([\w.]+)", self._uninstall),
            (r"cmd package install-existing --user 0 ([\w.]+)", self._install_existing),
            (r"cmd role get-role-holders --user 0 android\.app\.role\.(\w+)", self._role),
            (r"settings get (global|secure|system) ([\w.]+)", self._setting_get),
            (r"settings put (global|secure|system) ([\w.]+) ([\w.:-]+)", self._setting_put),
            (r"settings delete (global|secure|system) ([\w.]+)", self._setting_delete),
            (HOME_RESOLVE, self._resolve_home),
            (r"telecom get-default-dialer", lambda: ShellResult(0, self.roles.get("DIALER", "") + "\n")),
            (r"dpm list-owners", self._owners),
            (r"dumpsys device_policy", self._device_policy),
            (r"pm list users", self._users),
            (r"getprop", lambda: ShellResult(0, "".join(f"[{k}]: [{v}]\n" for k, v in self.props.items()))),
            (r"settings list (global|secure|system)", lambda ns: ShellResult(0, f"{ns}_key=1\n")),
        )

    def _setting_get(self, namespace, key):
        if namespace == "secure" and key == "sms_default_application":
            return ShellResult(0, self.roles.get("SMS", "null") + "\n")
        value = self.settings[namespace].get(key)
        return ShellResult(0, ("null" if value is None else value) + "\n")

    def _setting_put(self, namespace, key, value):
        name = f"{namespace}/{key}"
        if name in self.refuse_settings:
            return ShellResult(255, "\nException occurred while executing 'put':\n"   # as on a OnePlus 8T
                                    "java.lang.SecurityException: Permission denial, must have one of: "
                                    "[android.permission.WRITE_SECURE_SETTINGS]\n")
        if name not in self.ignore_settings:
            self.settings[namespace][key] = value
        return ShellResult(0, "")

    def _setting_delete(self, namespace, key):
        removed = self.settings[namespace].pop(key, None)
        return ShellResult(0, f"Deleted {0 if removed is None else 1} rows\n")

    def _resolve_home(self):
        home = self.roles.get("HOME", "")
        if not home:
            return ShellResult(0, "No activity found\n")
        return ShellResult(0, f"priority=0 preferredOrder=0 match=0x108000 isDefault=true\n{home}/.Launcher\n")

    def _owners(self):
        if not self.owners:
            return ShellResult(0, "no owners\n")
        lines = [f"{len(self.owners)} owner(s):"]
        lines += [f"User  0: admin={pkg}/.Receiver,DeviceOwner" for pkg in self.owners]
        return ShellResult(0, "\n".join(lines) + "\n")

    def _users(self):
        lines = ["Users:"] + [f"\tUserInfo{{{uid}:{name}:c13}} running" for uid, name in self.users]
        return ShellResult(0, "\n".join(lines) + "\n")

    def screenshot(self, destination):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self.screen)
        return len(self.screen)

    def _getprop(self, name):
        return ShellResult(0, self.props.get(name, "") + "\n")

    def _list(self, flags):
        flags = set(flags.split())
        names = []
        for name, info in sorted(self.packages.items()):
            if info["state"] == "uninstalled" and "-u" not in flags:
                continue
            if "-d" in flags and info["state"] != "disabled":
                continue
            if "-s" in flags and not info["system"]:
                continue
            if "-3" in flags and info["system"]:
                continue
            if "-f" in flags:
                # Updated system apps and user apps live under /data/app; factory system apps under /system.
                on_data = info.get("updated") or not info["system"]
                path = f"/data/app/~~x/{name}-1/base.apk" if on_data else f"/system/app/{name}/{name}.apk"
                names.append(f"package:{path}={name}")
                continue
            names.append(f"package:{name}")
        return ShellResult(0, "\n".join(names) + ("\n" if names else ""))

    def _unknown(self, verb, pkg):
        return ShellResult(255, f"\nException occurred while executing '{verb}':\n"
                                f"java.lang.IllegalArgumentException: Unknown package: {pkg}\n")

    def _disable(self, pkg):
        info = self.packages.get(pkg)
        if info is None or info["state"] == "uninstalled":
            return self._unknown("disable-user", pkg)
        if pkg in self.refuse_disable:
            return ShellResult(255, PM_ERROR.format(pkg=pkg))
        info["state"] = "disabled"
        return ShellResult(0, f"Package {pkg} new state: disabled-user\n")

    def _enable(self, pkg):
        info = self.packages.get(pkg)
        if info is None or info["state"] == "uninstalled":
            return self._unknown("enable", pkg)
        info["state"] = "enabled"
        return ShellResult(0, f"Package {pkg} new state: enabled\n")

    def _uninstall(self, pkg):
        info = self.packages.get(pkg)
        if info is None or pkg in self.refuse_uninstall:
            return ShellResult(1, "Failure [DELETE_FAILED_INTERNAL_ERROR]\n")
        if not info["system"]:
            # A user app removed for its only user is gone for good; the tools must never get here.
            del self.packages[pkg]
            return ShellResult(0, "Success\n")
        info["state"] = "uninstalled"
        return ShellResult(0, "Success\n")

    def _install_existing(self, pkg):
        info = self.packages.get(pkg)
        if info is None:
            return ShellResult(1, f"Package {pkg} doesn't exist\n")
        info["state"] = "enabled"
        return ShellResult(0, f"Package {pkg} installed for user: 0\n")

    def _role(self, role):
        if self.roles_unsupported:
            return ShellResult(255, "cmd: Can't find service: role\n")
        holder = self.roles.get(role, "")
        return ShellResult(0, holder + ("\n" if holder else ""))

    def _device_policy(self):
        lines = ["Current Device Policy Manager state:",
                 "  Enabled Device Admins (User 0, provisioningState: 3):"]
        for admin in self.admins:
            lines += [f"    {admin}/.AdminReceiver:", "      uid=10123"]
        lines += ["  ", "  Constants:", "    DAS_DIED_SERVICE_RECONNECT_BACKOFF_SEC: 3600"]
        return ShellResult(0, "\n".join(lines) + "\n")


def oneplus_phone(**overrides):
    """A small OnePlus 8T-shaped phone used across tests."""
    packages = {
        "android": {"system": True, "state": "enabled"},
        "com.android.launcher": {"system": True, "state": "enabled"},
        "com.google.android.dialer": {"system": True, "state": "enabled"},
        "com.google.android.apps.messaging": {"system": True, "state": "enabled"},
        "com.oplus.statistics.rom": {"system": True, "state": "enabled"},
        "com.oneplus.membership": {"system": True, "state": "enabled"},
        "com.heytap.mcs": {"system": True, "state": "enabled"},
        "com.netflix.partner.activation": {"system": True, "state": "enabled"},
        "com.coloros.childrenspace": {"system": True, "state": "disabled"},
        "com.google.android.youtube": {"system": True, "updated": True, "state": "enabled"},
        "com.touchtype.swiftkey": {"system": False, "state": "enabled"},
        "com.example.userapp": {"system": False, "state": "enabled"},
    }
    packages.update(overrides.pop("packages", {}))
    props = {
        "ro.product.brand": "OnePlus", "ro.product.manufacturer": "OnePlus",
        "ro.product.model": "KB2003", "ro.product.device": "OnePlus8T",
        "ro.build.version.release": "14", "ro.build.version.sdk": "34",
        "ro.build.display.id": "KB2003_14.0.0.1311(EX01)", "ro.build.version.oplusrom": "V14.0.0",
        "gsm.sim.operator.alpha": "TIM",
    }
    props.update(overrides.pop("props", {}))
    roles = {"HOME": "com.android.launcher", "DIALER": "com.google.android.dialer",
             "SMS": "com.google.android.apps.messaging"}
    roles.update(overrides.pop("roles", {}))
    defaults = {"ime": "com.touchtype.swiftkey/com.touchtype.KeyboardService"}
    defaults.update(overrides)
    return FakePhone(packages=packages, props=props, roles=roles, **defaults)


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path
