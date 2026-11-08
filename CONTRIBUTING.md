# Contributing

Thanks for helping more phones lose their bloat. Coding agents: [AGENTS.md](AGENTS.md) has the same
rules in the form you need.

The first requirement of this project is that **nobody loses data and no phone is damaged**. A
contribution that makes the tools faster or the lists longer at the cost of that will come back.

## Where does my change go?

| Your change | Where |
|---|---|
| A tested list for your exact phone | `examples/<brand>-<model>/` (section 1) |
| Packages that fit every phone of a brand and skin version | `lists/brands/<brand>/<skin>-<version>.txt` |
| A carrier's preloads | `lists/carriers/<country>-<carrier>.txt` with `# @carriers:` |
| A package that must never be touched | `guards/<platform>.txt`, with the reason |
| A setting that saves battery | `tweaks/power.txt` (or `tweaks/<brand>.txt` with `# @brands:`), a comment saying what the person loses and where the switch is in Settings; `ask` unless tested on a real phone |
| A fix or feature in the tools | `tools/` plus a test in `tests/` (section 3) |

## 1. Add your phone, step by step

A tested list for your exact model is the most useful contribution: the next person with the same
phone starts from what you already checked. It takes one afternoon for the cleanup, a few days of
normal use, and about half an hour for the pull request.

### Clean your phone first

1. Fork this repository on GitHub and clone your fork:
   ```bash
   git clone https://github.com/<you>/cleanyourandroid.git && cd cleanyourandroid
   ```
2. Clean your phone with the guided procedure in [PROMPT.md](PROMPT.md), from this clone. The
   assistant writes your personal list to `work/<model>.txt` and applies it one group at a time.
   Back up your data before you start, as the prompt says.
3. Use the phone normally for **a few days**. Write down anything that broke, and what you turned
   back on (`python3 tools/restore.py work/<model>.txt --group "<name>"`). After a reboot, run
   `python3 tools/check.py work/<model>.txt` and note anything the phone turned back on by itself.

### Prepare your folder

4. Make a branch: `git checkout -b add-<brand>-<model>` (lower case, hyphens: `add-oneplus-8t`).
5. Run `python3 tools/probe.py` with the phone connected and keep its output: the next steps use it.
6. Create `examples/<brand>-<model>/debloat.txt`. Start from a copy of `work/<model>.txt`, then:
   - put the exact model, Android version, skin and build in the first comment lines (probe.py prints
     them), and the carrier only if the phone came from a carrier;
   - remove the groups you turned back on, and every package the phone refused, so the file holds
     only what is off on your phone today;
   - keep the groups, tiers and comments as they are (the format is in
     [AGENTS.md](AGENTS.md#changing-the-repo)).
7. Add `examples/<brand>-<model>/phone.json`:
   ```json
   {
     "phone": "OnePlus 8T",
     "brand": "OnePlus",
     "models": ["KB2003"],
     "device": "OnePlus8T",
     "os": "Android 14, OxygenOS 14.0",
     "notes": "Telemetry, HeyTap push, Game Space, home search; Google apps and Weather kept"
   }
   ```
   `models` and `device` are what `tools/probe.py` matches on: `adb shell getprop ro.product.model`
   and `adb shell getprop ro.product.device` print them. List every model code you know runs the
   same list (regional variants), but only codes you are sure of. `notes` is one line for the table.
8. Add `examples/<brand>-<model>/README.md`: how many days you used the list, what you kept and why,
   what the phone refused, what came back after a reboot or an update, and anything you noticed
   (a button gone from the home screen, a setting the phone would not take).
   [examples/oneplus-8t/README.md](examples/oneplus-8t/README.md) is an example.
9. Found something that concerns every phone of your brand, not just yours? A package the phone
   refuses, or one whose comment is wrong? Fix it in the shared list too (section 2), in the same pull
   request, and say so in its description.

### Check

10. Regenerate the tables and run the tests:
    ```bash
    python3 tools/gen_tables.py
    python3 -m pytest
    ```
    `gen_tables.py` adds your phone to `examples/README.md` and to the brand line in `README.md`;
    CI fails while those tables are out of date, so they belong in your pull request.
    `pytest` checks your list parses and names no protected package.
11. With the phone connected, `python3 tools/probe.py` should now print your folder under
    "Tested lists for this model".
12. Check that nothing private goes out. `git status` should show only your folder,
    `examples/README.md` and `README.md` (plus a shared list if you did step 9). `backup/`, `work/` and
    `shots/` are ignored by git on purpose: they hold your serial number, your choices and screenshots
    of your phone. Do not copy the serial number, IMEI, phone number or account names into any file
    or into the pull request.

### Open the pull request

13. Commit and push:
    ```bash
    git add examples/<brand>-<model> examples/README.md README.md
    git commit -m "feat: add <Brand> <Model> example"
    git push -u origin add-<brand>-<model>
    ```
14. Open the pull request on GitHub against `main`. The template asks for the probe.py output
    (remove the `serial` from it), how many days you used the list, what broke and what you turned
    back on.
15. CI runs the tests on Python 3.9 and 3.13. A reviewer may ask what a package does: answer with
    `adb shell dumpsys package <name>`, never by opening an app you do not know.

Never list a package to *uninstall*: lists say what to turn off, and `tools/disable.py` decides how.
A list that names a package from `guards/` is refused by the tools and by CI.

### When no list fits your phone

If probe.py finds no list for your brand or Android version, the cleanup in step 2 has little to
offer. You can start one; it goes through review like any shared list (section 2):

- Copy the closest list (same skin, nearest version) to
  `lists/brands/<brand>/<skin>-<version>.txt`, with `# @brands:` and `# @sdk:` saying where it fits.
  The skin name and SDK level come from probe.py.
- Find candidates read-only: `adb shell pm list packages -s` lists the system apps, and
  `adb shell dumpsys package <name>` shows what each one does (activities, services, permissions).
  Never launch an unknown app to find out.
- Everything you did not test on your own phone is `[expert]`. Move a group to `[ask]` or `[safe]`
  only after applying it with `disable.py --group`, rebooting and living with it.
- A package whose loss broke something important (calls, SMS, unlock, Home, updates) goes into
  `guards/` with the reason, so no list can touch it again.

## 2. Lists for a brand, Google or a carrier

- `[safe]` is only for packages nobody would miss: telemetry, diagnostics uploads, activation stubs.
- Anything a person might use (an app, a feature, a sync) is `[ask]`, one group per thing a person
  recognises, with a comment that says what stops working.
- Anything not verified on a real phone is `[expert]`.
- Every package has a trailing comment saying what it is.

## 3. The tools

Plain Python 3.9+, standard library only; dev dependencies in `requirements-dev.txt`.

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest --cov=tools --cov-report=term-missing
```

- Write the test first (`tests/helpers.py` has `FakePhone`), see it fail, then change the code.
- Only `tools/actions.py` sends commands that change the phone. Keep it that way.
- Error messages are for the person: say what happened and what to do next.
- Exit codes: 0 done, 1 needs a look, 2 did not run.

## Pull requests

Describe what you tested and on which phone; for a new phone, follow section 1 to the end.
CI runs the tests and checks every list against the guards.
