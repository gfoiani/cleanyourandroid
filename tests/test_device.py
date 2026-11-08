"""Reading the phone: identity, package states and what is in use right now."""
import pytest

import device
from adb import AdbError, choose_device, parse_devices
from helpers import oneplus_phone


def test_read_info_identifies_a_oneplus():
    info = device.read_info(oneplus_phone())

    assert (info.brand, info.model, info.device, info.sdk) == ("OnePlus", "KB2003", "OnePlus8T", 34)
    assert info.skin == "OxygenOS V14.0.0"
    assert info.carrier == "TIM"


@pytest.mark.parametrize("props, skin", [
    ({"ro.product.brand": "samsung", "ro.build.version.oneui": "60101"}, "One UI 6.1.1"),
    ({"ro.product.brand": "Xiaomi", "ro.mi.os.version.name": "OS2.0"}, "HyperOS OS2.0"),
    ({"ro.product.brand": "Redmi", "ro.miui.ui.version.name": "V14"}, "MIUI V14"),
    ({"ro.product.brand": "OPPO", "ro.build.version.oplusrom": "V14.0.0"}, "ColorOS V14.0.0"),
    ({"ro.product.brand": "realme", "ro.build.version.oplusrom": "V5.0"}, "realme UI V5.0"),
    ({"ro.product.brand": "google"}, "stock Android"),
])
def test_detect_skin(props, skin):
    assert device.detect_skin(props) == skin


def test_read_states_sorts_packages_by_state():
    phone = oneplus_phone(packages={"com.example.gone": {"system": True, "state": "uninstalled"}})

    states = device.read_states(phone)

    assert states.state("com.heytap.mcs") == "enabled"
    assert states.state("com.coloros.childrenspace") == "disabled"
    assert states.state("com.example.gone") == "uninstalled"
    assert states.state("com.not.there") == "absent"
    assert "com.heytap.mcs" in states.system
    assert "com.example.userapp" not in states.system


def test_in_use_names_roles_keyboard_accessibility_and_admins():
    phone = oneplus_phone(a11y="com.example.reader/com.example.reader.Service:com.other/.S",
                          admins=["com.google.android.gms"])

    found = device.in_use(phone)

    assert "default home" in found["com.android.launcher"]
    assert "default phone" in found["com.google.android.dialer"]
    assert "default SMS" in found["com.google.android.apps.messaging"]
    assert "keyboard" in found["com.touchtype.swiftkey"]
    assert "accessibility" in found["com.example.reader"]
    assert "accessibility" in found["com.other"]
    assert "device admin" in found["com.google.android.gms"]


def test_in_use_covers_passwords_vpn_payments_notifications_assistant_and_owners():
    phone = oneplus_phone(
        roles={"ASSISTANT": "com.google.android.googlequicksearchbox"},
        owners=["com.example.mdm"],
        secure={"autofill_service": "com.bitwarden/.Autofill",
                "always_on_vpn_app": "com.example.vpn",
                "nfc_payment_default_component": "com.google.android.apps.walletnfcrel/.Pay",
                "enabled_notification_listeners": "com.example.watch/.Listener:com.example.car/.L",
                "voice_interaction_service": "com.example.voice/.Service"})

    found = device.in_use(phone)

    assert "password manager" in found["com.bitwarden"]
    assert "VPN" in found["com.example.vpn"]
    assert "tap-to-pay" in found["com.google.android.apps.walletnfcrel"]
    assert "notifications" in found["com.example.watch"] and "com.example.car" in found
    assert "assistant" in found["com.google.android.googlequicksearchbox"]
    assert "voice" in found["com.example.voice"]
    assert "owner" in found["com.example.mdm"]


def test_in_use_falls_back_when_cmd_role_is_missing():
    phone = oneplus_phone(roles_unsupported=True)

    found = device.in_use(phone)

    assert "home" in found["com.android.launcher"]
    assert "phone" in found["com.google.android.dialer"]
    assert "SMS" in found["com.google.android.apps.messaging"]


def test_in_use_stops_when_the_home_screen_cannot_be_found():
    phone = oneplus_phone(roles={"HOME": ""})

    with pytest.raises(RuntimeError, match="home screen"):
        device.in_use(phone)


def test_read_states_knows_updated_system_apps():
    states = device.read_states(oneplus_phone())

    assert "com.google.android.youtube" in states.updated
    assert "com.google.android.youtube" in states.system
    assert "com.heytap.mcs" not in states.updated


def test_parse_admins_tolerates_other_indentation_and_trailing_spaces():
    text = ("Current Device Policy Manager state:\n"
            "   Enabled Device Admins (User 0, provisioningState: 3):\n"
            "      com.example.mdm/.Receiver:  \n"
            "        uid=10123\n"
            "   Constants:\n")

    assert device.parse_admins(text) == frozenset({"com.example.mdm"})


def test_parse_admins_reads_only_the_enabled_admins_block():
    text = ("  Enabled Device Admins (User 0, provisioningState: 3):\n"
            "    com.example.mdm/.Receiver:\n"
            "      uid=10123\n"
            "  \n"
            "  Constants:\n"
            "    com.not.admin/.X:\n")

    assert device.parse_admins(text) == frozenset({"com.example.mdm"})


def test_parse_devices_and_choose():
    text = ("List of devices attached\n"
            "0a1b2c3d               device usb:20-1.2 product:OnePlus8T_EEA model:KB2003\n"
            "emulator-5554          unauthorized\n")
    devices = parse_devices(text)

    assert devices == (("0a1b2c3d", "device"), ("emulator-5554", "unauthorized"))
    assert choose_device(devices, "0a1b2c3d") == "0a1b2c3d"
    with pytest.raises(AdbError, match="Allow USB debugging"):
        choose_device(devices, "emulator-5554")
    with pytest.raises(AdbError, match="more than one"):
        choose_device((("a", "device"), ("b", "device")), None)
    with pytest.raises(AdbError, match="No phone"):
        choose_device((), None)
    assert choose_device((("a", "device"), ("b", "unauthorized")), None) == "a"
