# The prompt

Paste this into Claude Code (or another coding assistant with shell access) on a computer with the
phone plugged in over USB, from a clone of this repo.

Before you start:
- **Back up your data** (photos, chats, contacts, authenticator codes) the way you normally do.
- On the phone: Settings → About phone → tap **Build number** seven times (Xiaomi: *MIUI/HyperOS
  version*; Samsung: *Software information → Build number*), then Developer options → **USB debugging**
  on. Xiaomi also needs **USB debugging (Security settings)**, which asks for a SIM and a Mi account.
- Charge the phone above 50% and keep it unlocked while the assistant works. In Developer options,
  turn on **Stay awake** too, so the screen does not lock while the phone charges over USB.

---

I want to remove the bloat from my Android phone. My phone is: <MODEL HERE>. Work on the real phone,
step by step, and check every step. Talk to me in my language. Ask me before anything that depends on
what I use. Use the tools in `tools/` for every change; if they are not in your working folder, clone
this repository and work from there rather than writing your own.

Rule zero: do not lose my data and do not damage the phone
- Every app change goes through `tools/disable.py` and every undo through `tools/restore.py`; every
  setting change through `tools/tune.py`, undone with `tools/tune.py <file> --restore`. Do not send
  `pm disable-user`, `pm uninstall`, `pm hide`, `pm suspend`, `pm clear`, `cmd package` or `settings put`
  by hand, except the Private DNS commands below and only after I agree.
- Never: root, unlock the bootloader, flash, reboot into recovery or bootloader, factory reset, wipe,
  `rm` on the phone, touch accounts, or remove an app that is not part of the system image.
- Never edit `guards/` to get a package through, and never "work around" a refusal. A refusal is the
  answer: tell me what was refused and why.
- When you are not sure what a package does, find out read-only (`dumpsys package <name>`: its
  activities, services, permissions). Never launch an unknown package to see what it is. If it is
  still unclear, leave it, or ask me.
- If anything looks wrong at any point (a crash dialog, no signal, no notifications, the home screen
  missing), stop, undo the last batch with `tools/restore.py <list> --group "<name>"`, and tell me.

Connect
- `adb devices` must list the phone as `device`. `unauthorized` means I have to unlock the phone and
  tap Allow on "Allow USB debugging?": tell me when to look. `no devices` usually means a charge-only
  cable or the USB mode: ask me to pick "File transfer" in the USB notification.
- Then `python3 tools/probe.py`. It tells you the brand, model, Android version, skin, carrier, users
  and which lists fit. If it reports more than one user or profile (work profile, Secure Folder,
  second space), tell me that only the main profile is changed.
- Ask me whether the phone is managed by an employer or school. If it is, stop: that is for them to decide.

Before anything changes
- Ask me to confirm that my data is backed up. Do not go on without a yes.
- `python3 tools/backup.py`, then `python3 tools/screenshot.py shots/00-before.png` from the home screen.

Choose, with me
- `python3 tools/compose.py <the lists probe.py suggested> --checklist`. Read the output yourself
  first; it lists only packages that are on this phone.
- **Safe** groups (telemetry, diagnostics, partner activation stubs): show me the group names in one
  short list and ask for one OK for all of them.
- **Ask** groups: put them to me as checklist questions, grouped by theme (Google apps; the phone
  maker's apps and features; partner apps like Facebook, Microsoft, Netflix), at most four questions,
  "tick what you use". Mention in a few words what stops working when a group is off (the comments
  in the list say it). Everything I tick stays.
- **Expert** groups: do not offer them unless I ask for more. If I do, check each package with
  `dumpsys package` first and tell me what you found.
- Packages that are on the phone but in no list: do not add them on your own. If I ask you to look
  for more, find candidates read-only, explain each, and add only what I agree to, in a group of
  its own in my personal list.
- Write my personal list: `python3 tools/compose.py <same lists> --drop-group "<each ticked group>"
  -o work/<model>.txt` (add `--include-group` for expert groups I agreed to). Show me the file.

Apply, in small batches
- Dry run first: `python3 tools/disable.py work/<model>.txt`. Show me the summary, including what is
  skipped because I am using it right now (home screen, phone, SMS, keyboard) or because it is protected.
- Then one group at a time: `python3 tools/disable.py work/<model>.txt --apply --group "<name>"`.
  After each batch: `python3 tools/screenshot.py shots/NN-<group>.png`, look at it, and check the
  phone still opens Home and Settings. A screenshot that comes back empty means the app on screen
  blocks capture, not damage: go Home and capture again. One that is all black usually means the
  screen went off or locked: ask me to unlock the phone, then capture again.
- If the phone refuses to disable some packages ("refused"), do not retry. Explain the difference to
  me: with `--fallback-uninstall` they are removed for my user only, their data is kept, they stay in
  the system image, and `restore.py` reinstalls them; without it they stay as they are. Run it with
  the flag only if I say yes, and only for that group.

Save battery (ask me first)
- Ask whether I also want to go through the battery settings. If I do: `python3 tools/tune.py
  tweaks/power.txt`. It is a dry run: for each group it shows the value now and the new one, or
  "already" where nothing would change.
- Put the **ask** groups that would change something to me as one checklist, "tick what you want",
  with what each one costs in a few words (the comments in the file say it: the screen turns off
  sooner, indoor location gets less precise, rarely used apps notify later). Nothing I do not tick
  changes. Do not offer **expert** groups unless I ask for more.
- Apply what I ticked, one group at a time: `python3 tools/tune.py tweaks/power.txt --apply --group
  "<name>"`, then check the phone (a screenshot, or ask me). Some phones keep their own switch for a
  setting and ignore the value: if so, tell me and point me to the switch in Settings that the comment
  names. Anything I do not like: `python3 tools/tune.py tweaks/power.txt --restore --group "<name>"`.
- If the phone refuses for a missing permission (`WRITE_SECURE_SETTINGS`), nothing changed: tell me
  how to set it by hand where the comment says. Never ask me to lower a protection to get a setting
  through, such as "Disable permission monitoring" on OnePlus, OPPO and realme.
- Point me to what saves battery that you do not change: the phone maker's own battery saver and
  screen refresh rate (Settings → Display, Settings → Battery), and Settings → Battery to see which
  apps use the most.

Reboot and check
- Wait at least 15 seconds after the last change (Android writes package state about ten seconds after
  a change), then ask me before rebooting: `adb reboot`. After the reboot, unlock the phone and run
  `python3 tools/check.py work/<model>.txt`: anything the firmware turned back on by itself is noted,
  not fought; tell me.

Test with me
- Ask me to check, one by one: a phone call in and out, an SMS, mobile data with Wi-Fi off, Wi-Fi,
  a notification from a chat app, fingerprint or face unlock, the camera, an alarm, and my banking or
  payment app if I use one. Anything broken: undo the group most likely behind it with
  `tools/restore.py --group`, reboot if needed, and check again.

Optional extras (ask first, one by one)
- Ad-blocking Private DNS (Android 9+): `settings put global private_dns_mode hostname` and
  `settings put global private_dns_specifier dns.adguard-dns.com`. Say that it does not block YouTube
  ads, that it can break captive portals of hotel Wi-Fi, and that I can turn it off in Settings →
  Network → Private DNS. Ask first whether I use a VPN, Pi-hole or a router that filters by DNS:
  Private DNS bypasses those. Check that a web page and an app still load afterwards.
- Privacy toggles I can switch myself, which you only point me to: Settings → Google → Ads (delete
  advertising ID); Settings → Privacy → Ads privacy (Privacy Sandbox off); the phone maker's
  "user experience programme" or diagnostics switch.

Finish
- Give me a summary: what was turned off, what was kept and why, what was refused, what came back
  after the reboot, and which battery settings changed.
- Tell me where my personal list (`work/<model>.txt`) and the recovery record
  (`~/.cleanyourandroid/<serial>/`) are, how to undo everything (`python3 tools/restore.py
  work/<model>.txt`) or one group (`--group`), how to put the battery settings back (`python3
  tools/tune.py tweaks/power.txt --restore`), and to run `tools/check.py` after a system update.
- Ask whether I want to keep USB debugging on. If not, tell me to turn it off in Developer options
  and to tap "Revoke USB debugging authorisations". Either way, remind me to turn **Stay awake** off
  again.
- Ask whether I want to share the list (CONTRIBUTING.md): after a few days of use, not today.

---

Expect four or five questions: which apps you use, from Google, the phone maker and partners, which
battery settings you want, and whether to add the optional extras. Everything is reversible.
