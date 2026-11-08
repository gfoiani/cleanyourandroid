# AGENTS.md

Instructions for coding agents (Claude Code, Codex, Gemini CLI, Cursor, Copilot and others) working in
this repository. People start with [README.md](README.md) and [CONTRIBUTING.md](CONTRIBUTING.md).

## First: which job are you doing?

| You were asked to | Do this |
|---|---|
| Clean up a phone | Follow [PROMPT.md](PROMPT.md) exactly, on the real phone, with the tools in `tools/`. Write only under `work/`, `backup/` and `shots/`. Do not edit lists, guards, tools, docs or tests, and do not open issues or pull requests unless the person asks. |
| Change this repo: a list, a guard, a fix, docs | Read on from [Repo map](#repo-map). |

## The requirement above all others

**The person must not lose data, and the phone must not be damaged.** Every rule below follows from it.
When a choice is unclear, the safe default is to change nothing and ask.

### Cleaning a phone: rules that are not negotiable

- **Only through the tools.** Package changes go through `tools/disable.py` (dry run unless `--apply`),
  undo through `tools/restore.py`; setting changes through `tools/tune.py`, undo with `--restore`.
  No hand-typed `pm disable-user`, `pm uninstall`, `pm hide`, `pm suspend`, `pm clear`, `cmd package` or
  `settings put` (Private DNS from PROMPT.md, with consent, is the only exception).
- **Disable first; uninstall only as a fallback, only with consent.** `--fallback-uninstall` removes a
  package for user 0 with `-k` (data kept) and only for system packages; ask the person each time,
  explaining that `restore.py` reinstalls it.
- **Never touch `guards/`** to get a package through. A refusal is the answer.
- **Never** root, unlock, flash, reboot into recovery/bootloader, factory reset, `rm` on the phone,
  touch accounts, or launch an unknown package to find out what it is (`dumpsys package` instead).
- **Data first.** Ask the person to confirm their data is backed up before the first change;
  run `tools/backup.py`.
- **Ask before anything they might use.** `[ask]` groups become checklist questions; only what is not
  ticked is applied. `[expert]` groups only when the person asks for more.
- **Small batches.** `--group` one at a time, a screenshot after each (`tools/screenshot.py`), Home and
  Settings still open. Something wrong: `tools/restore.py <list> --group "<name>"` and stop.
- **Managed phones:** if the phone belongs to an employer or school, stop.
- **Test with the person** after the reboot: calls, SMS, mobile data, Wi-Fi, notifications, unlock,
  camera, alarm, banking/payment app.

## Repo map

| Path | What it is |
|---|---|
| `PROMPT.md` | The procedure an assistant follows with the person. |
| `tools/` | Python 3.9+, standard library only. `adb.py` (adb wrapper), `device.py` (reads only), `actions.py` (the only module that sends state-changing commands), `listfile.py`, `guards.py`, `recovery.py`, `tweakfile.py`, `tweakrecord.py`, and the CLIs `probe`, `backup`, `compose`, `disable`, `restore`, `check`, `tune`, `screenshot`, `gen_tables`. |
| `guards/*.txt` | Packages no list may touch, with the reason. All files apply to every phone. |
| `lists/brands/<brand>/<skin>-<version>.txt` | Brand and skin lists. `# @brands:` and optional `# @sdk:` say where they fit. |
| `lists/google/`, `lists/common/`, `lists/carriers/` | Lists that fit any brand (`# @brands: any`); carrier lists add `# @carriers:`. |
| `tweaks/*.txt` | Battery settings `tools/tune.py` may change: `<namespace> <key> [<=\|>=]<value> [default=<value>]  # comment` (`default=` only when Android's value for an unwritten setting is certain), grouped and tiered like the lists. Only files here are accepted; `tweakfile.NEVER` refuses settings such as USB debugging, lock screen and location. |
| `examples/<brand>-<model>/` | Tested lists: `debloat.txt`, `phone.json`, optional `README.md`. |
| `tests/` | pytest; `tests/helpers.py` has `FakePhone`, an in-memory phone. |

## Changing the repo

- **List format** (see `tools/listfile.py`): one package per line, under `# == Group name [safe|ask|expert]`,
  with a trailing `# comment` that says what the package is and what stops working without it.
  `safe` only for packages no person would miss (telemetry, diagnostics, activation stubs).
  Anything a person might use is `ask`. Anything you could not verify is `expert`.
- **Guards**: adding a pattern is welcome, with a reason. Removing or narrowing one needs evidence from
  real devices in the pull request.
- **Tests first.** Every behaviour change in `tools/` comes with a test in `tests/` that fails before
  the change. Run `python3 -m pytest` (dev deps: `pip install -r requirements-dev.txt`).
- **Generated tables**: `examples/README.md` and the brand block in `README.md` come
  from `tools/gen_tables.py`; do not edit them by hand.
- **Language**: the repo is English only.
