"""Protected packages: the guard files the tools refuse to touch, with no override."""
import pytest

import guards
from guards import GuardError
from helpers import ROOT, write


def test_exact_and_prefix_patterns(tmp_path):
    write(tmp_path / "core.txt", "android   # the framework\ncom.android.providers.*   # all providers\n")
    loaded = guards.load(tmp_path)

    assert guards.match("android", loaded).reason == "the framework"
    assert guards.match("com.android.providers.contacts", loaded).source.endswith("core.txt")
    assert guards.match("com.android.providersx", loaded) is None
    assert guards.match("com.example.app", loaded) is None


def test_refuses_a_malformed_pattern(tmp_path):
    write(tmp_path / "bad.txt", "com.example.*.x\n")

    with pytest.raises(GuardError, match="bad.txt:1"):
        guards.load(tmp_path)


def test_refuses_an_empty_guard_directory(tmp_path):
    with pytest.raises(GuardError, match="no guard"):
        guards.load(tmp_path)


def test_protected_returns_only_guarded_packages(tmp_path):
    write(tmp_path / "core.txt", "com.android.phone   # calls\n")
    loaded = guards.load(tmp_path)

    found = guards.protected(["com.android.phone", "com.example.bloat"], loaded)

    assert list(found) == ["com.android.phone"]


@pytest.mark.parametrize("package", [
    "android", "com.android.systemui", "com.android.phone", "com.android.server.telecom",
    "com.android.providers.contacts", "com.android.providers.telephony", "com.google.android.gms",
    "com.android.vending", "com.google.android.webview", "com.google.android.cellbroadcastreceiver",
    "com.google.android.permissioncontroller", "com.google.android.overlay.modules.ext.services",
    "com.qualcomm.qti.ims", "org.codeaurora.ims", "vendor.qti.iwlan", "com.mediatek.ims",
    "oplus", "com.oplus.securitypermission", "com.oplus.ota", "com.oplus.apprecover",
    "com.miui.securitycenter", "com.lbe.security.miui", "com.samsung.android.providers.media",
    "com.sec.imsservice",
    # Found missing in review: Wi-Fi, Bluetooth, eSIM, dialers, contacts, messaging, launchers, installers.
    "com.android.wifi", "com.google.android.wifi", "com.android.bluetooth.services", "com.google.android.bluetooth",
    "com.android.euicc", "com.google.android.euicc", "com.android.contacts", "com.android.dialer",
    "com.google.android.dialer", "com.google.android.contacts", "com.google.android.apps.messaging",
    "com.android.launcher", "com.android.launcher3", "com.android.systemui.plugin.globalactions",
    "com.android.captiveportallogin", "com.android.managedprovisioning", "com.android.calllogbackup",
    "com.google.android.backuptransport", "com.google.android.syncadapters.contacts",
    "com.sec.epdg", "com.sec.android.app.launcher", "com.samsung.android.dialer", "com.samsung.android.messaging",
    "com.miui.packageinstaller", "com.xiaomi.xmsf", "com.coloros.safecenter", "com.heytap.cloud",
])
def test_repo_guards_protect_what_a_phone_needs(package):
    assert guards.match(package, guards.load(ROOT / "guards")) is not None, package


@pytest.mark.parametrize("package", [
    "com.oplus.statistics.rom", "com.heytap.mcs", "com.oneplus.membership",
    "com.netflix.partner.activation", "com.facebook.appmanager",
])
def test_repo_guards_leave_known_bloat_alone(package):
    assert guards.match(package, guards.load(ROOT / "guards")) is None, package
