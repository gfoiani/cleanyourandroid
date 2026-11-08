"""Setting files (tweaks/*.txt): what tune.py may change, and the refusals that keep it safe."""
import pytest

import tweakfile
from listfile import ListError

TEXT = """\
# @brands: any

# == Screen turns off sooner [ask]
system screen_off_timeout <=30000      # 30 seconds without a touch

# == Shorter animations [ask]
global window_animation_scale 0.5      # half-length window animations
global animator_duration_scale 0.5
"""


def test_parse_reads_settings_groups_and_bounds():
    parsed = tweakfile.parse(TEXT, "power.txt")

    assert parsed.meta == {"brands": "any"}
    first = parsed.entries[0]
    assert (first.namespace, first.key, first.bound, first.value) == ("system", "screen_off_timeout", "<=", "30000")
    assert first.name == "system/screen_off_timeout"
    assert (first.group, first.tier, first.comment) == ("Screen turns off sooner", "ask", "30 seconds without a touch")
    assert first.default is None
    assert tweakfile.parse("# == G [ask]\nglobal a_b 1 default=0\n").entries[0].default == "0"
    assert [e.key for e in parsed.entries[1:]] == ["window_animation_scale", "animator_duration_scale"]


@pytest.mark.parametrize("line", [
    "local screen_off_timeout 30000",          # not a settings namespace
    "system screen_off_timeout",               # no value
    "system screen_off_timeout 30000 extra",   # one value only
    "system screen_off_timeout 30000;reboot",  # shell syntax in the value
    "system screen$(id) 1",                    # shell syntax in the key
    "system screen_off_timeout <=fast",        # a bound needs a number
    "global a_b 1 default=1;id",               # shell syntax in the default
    "global a_b 1 default=",                   # a default needs a value
    "global a_b 1 fallback=1",                 # the only extra word is default=
])
def test_parse_refuses_lines_that_are_not_one_safe_setting(line):
    with pytest.raises(ListError, match="power.txt:2"):
        tweakfile.parse(f"# == G [ask]\n{line}\n", "power.txt")


@pytest.mark.parametrize("key", ["adb_enabled", "private_dns_mode", "location_mode", "airplane_mode_on",
                                 "package_verifier_enable", "lockscreen.disabled", "mobile_data1", "data_roaming2",
                                 "lock_pattern_autolock", "default_input_method", "enabled_accessibility_services",
                                 "auto_time", "http_proxy", "emergency_tone", "install_unknown_apps"])
def test_parse_refuses_settings_this_repo_never_changes(key):
    with pytest.raises(ListError, match="never changes"):
        tweakfile.parse(f"# == G [ask]\nglobal {key} 0\n", "power.txt")


def test_a_similar_name_that_is_not_protected_is_accepted():
    assert tweakfile.parse("# == G [ask]\nglobal mobile_data_always_on 0\n").entries[0].key == "mobile_data_always_on"


def test_command_refuses_protected_settings_even_when_built_by_hand():
    with pytest.raises(ListError, match="never changes"):
        tweakfile.command("put", "global", "adb_enabled", "0")
    with pytest.raises(ListError, match="never changes"):
        tweakfile.command("delete", "secure", "lock_screen_owner_info")
    assert tweakfile.command("get", "global", "adb_enabled") == "settings get global adb_enabled"


def test_parse_refuses_the_same_setting_twice():
    with pytest.raises(ListError, match="twice"):
        tweakfile.parse("# == G [ask]\nglobal a_b 1\n# == H [ask]\nglobal a_b 0\n", "power.txt")


def test_parse_needs_a_tier_on_every_group():
    with pytest.raises(ListError, match="tier"):
        tweakfile.parse("# == G\nglobal a_b 1\n", "power.txt")


@pytest.mark.parametrize(("current", "line", "done"), [
    ("0.5", "global window_animation_scale 0.5", True),
    ("0.50", "global window_animation_scale 0.5", True),
    ("1.0", "global window_animation_scale 0.5", False),
    (None, "global window_animation_scale 0.5", False),
    ("15000", "system screen_off_timeout <=30000", True),    # already shorter: never made longer
    ("60000", "system screen_off_timeout <=30000", False),
    (None, "system screen_off_timeout <=30000", False),
    ("30", "global low_power_trigger_level >=20", True),     # already earlier: never made later
    ("5", "global low_power_trigger_level >=20", False),
    ("-1", "system screen_off_timeout <=30000", False),      # -1 and 0 mean "never" / "default", not "short"
    ("0", "system peak_refresh_rate <=60", False),
    ("٣", "system screen_off_timeout <=30000", False),        # not an ASCII number
    ("60.000004", "system peak_refresh_rate <=60", True),     # how a OnePlus 8T stores 60 Hz
    ("60.1", "system peak_refresh_rate <=60", False),
    ("19.9999999", "global low_power_trigger_level >=20", True),
    ("0.5000001", "global window_animation_scale 0.5", True),
    (None, "global adaptive_battery_management_enabled 1 default=1", True),   # not set: Android uses 1
    (None, "global adaptive_battery_management_enabled 1 default=0", False),
    ("0", "global adaptive_battery_management_enabled 1 default=1", False),   # set: the default is moot
])
def test_satisfied_by_compares_numbers_and_respects_bounds(current, line, done):
    tweak = tweakfile.parse(f"# == G [ask]\n{line}\n").entries[0]

    assert tweak.satisfied_by(current) is done


def test_command_refuses_anything_but_a_safe_name_and_value():
    assert tweakfile.command("put", "system", "screen_off_timeout", "30000") == \
        "settings put system screen_off_timeout 30000"
    assert tweakfile.command("get", "global", "a_b") == "settings get global a_b"
    with pytest.raises(ListError):
        tweakfile.command("put", "system", "screen_off_timeout", "1; rm -rf /")
    with pytest.raises(ListError):
        tweakfile.command("put", "vendor", "a_b", "1")
    with pytest.raises(ListError):
        tweakfile.command("reset", "global", "a_b")
