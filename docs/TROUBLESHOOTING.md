# Troubleshooting

## Connecting

| What you see | What it means | What to do |
|---|---|---|
| `adb devices` lists nothing | Charge-only cable, USB mode, or USB debugging off | Use a data cable; pick "File transfer" in the USB notification; check Developer options → USB debugging. |
| `unauthorized` | The phone has not accepted this computer | Unlock the phone, tap **Allow** on "Allow USB debugging?" (tick "Always allow"). No prompt: Developer options → Revoke USB debugging authorisations, replug. |
| `offline` | The connection is half up | Unplug and replug; toggle USB debugging. |
| Xiaomi: "Permission denial" on every change | MIUI/HyperOS needs a second switch | Developer options → **USB debugging (Security settings)** on (needs a SIM and Mi account). |
| `the phone did not answer within 90s` | The phone locked or the cable moved | Unlock it, check the cable, run the same command again: the record keeps the original state. |

## Applying

| What you see | What it means | What to do |
|---|---|---|
| `refusing the list: it names packages this repo never touches` | A line names a protected package (`guards/`) | Remove the line. There is no override. |
| `refused ... SecurityException: Shell cannot change component state` | This firmware does not let the shell disable that package | Leave it, or with the person's consent run that group with `--fallback-uninstall` (removed for user 0, data kept, reinstallable). |
| `unverified` | The phone said yes, then reported the package still on | Some firmware turns certain packages back on at once. Leave it and note it. |
| `Skipped, in use right now` | It is the default home, phone, SMS app or assistant, the keyboard, the password manager, the always-on VPN, the tap-to-pay app, an app reading notifications, an accessibility service, a device admin or the device owner | Expected. Change the default in Settings first if the person really wants it gone. |
| `stopped: could not tell which app is the home screen` | The phone did not answer which apps are its defaults | Nothing was changed. Unlock the phone and run again; if it repeats, report it with `probe.py` output. |
| `interrupted` / `not attempted` | The cable moved or the phone locked mid-run | Packages already changed are in the record. Run the same command again to continue, or `restore.py` to undo. |
| `not uninstalled: it is an updated system app` | Removing it for user 0 would also drop its update | Leave it on, or turn it off from Settings → Apps if the phone allows. |
| `tune.py`: `unverified` right after a setting | The phone keeps its own switch for it and put the value back | Leave it; use the switch in Settings that the comment in `tweaks/` names. |
| `tune.py`: `cannot be recorded safely; left as is` | The current value has characters the tool does not send to a shell | Expected; nothing was changed. Change it in Settings if wanted. |
| `tune.py`: `refused` with `WRITE_SECURE_SETTINGS` | OnePlus, OPPO, realme and Xiaomi keep these settings from a computer unless a protection in Developer options is off | Leave the protection on; change the setting by hand where the comment in `tweaks/` says. Nothing was changed. |
| `tune.py`: `kept ... changed since` on restore | The person changed that setting after `tune.py` | Expected: their newer choice is kept. |
| A screenshot comes back empty | The app on screen blocks capture (banking, DRM, password field) | Go to the home screen and capture again. |

## After a change

| What you see | What to do |
|---|---|
| Notifications from an app stopped | Undo the last groups one at a time (`tools/restore.py <list> --group "<name>"`); push services such as HeyTap or a Google app are the usual suspects. |
| Weather or clock widget empty | Undo the Weather group. |
| A Google app asks to be enabled | It is one of the `[ask]` groups; enable it from the prompt or with `--group`. |
| Something came back after a reboot or an update | `python3 tools/check.py <list>` lists it, `--fix` turns it off again. Firmware that re-enables a package at every boot wins: note it in the list. |

## Undo everything

```bash
python3 tools/restore.py work/<model>.txt                    # the state from before, from the record
python3 tools/restore.py work/<model>.txt --without-record   # no record: enable everything listed
```

Without a computer: Settings → Apps → show system apps → the app → **Enable**. A package removed for
your user (fallback) needs the computer: `restore.py`, or by hand
`adb shell cmd package install-existing --user 0 <package>`.

## The phone does not start normally

This should not happen: the packages that can stop a phone from booting are protected. If it does:

1. Leave it on the charger and let it try for a few minutes; the first boot after a change can be slow.
2. If the lock screen or home screen appears, connect the cable and run `python3 tools/restore.py <list>`.
   With USB debugging already authorised, `adb wait-for-device` then `restore.py` also works while
   the phone shows a crash dialog.
3. Still stuck: report it (SECURITY.md) with the list, `probe.py` output and what you saw, before trying
   anything else. A factory reset deletes data and is the very last resort; that is why the backup
   comes first.
