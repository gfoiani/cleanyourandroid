# Security

## Reporting

If you find a way for a list, a tool or an instruction in this repo to delete data, leave a phone
unable to boot or call, run an unintended command on the phone, or expose something private, please
report it privately through GitHub's "Report a vulnerability" on this repository rather than a public
issue.

## What the tools defend against

- **Command injection from lists.** A package name ends up in a shell command on the phone; every
  list line must be a bare package name or the whole list is refused (`tools/listfile.py`).
- **Disabling what a phone needs.** `guards/*.txt` is checked before anything is sent; there is no
  override switch.
- **Losing the way back.** The state before each change is written to `~/.cleanyourandroid/` before the
  first command, and after every change. Uninstall is only `pm uninstall -k --user 0` (data kept), only
  for system packages, only with `--fallback-uninstall`.
- **Private files.** `backup/` holds device identifiers and `work/` personal choices; both are in
  `.gitignore`.

USB debugging gives a computer full shell access to the phone. Turn it off and revoke the
authorisations when you are done (PROMPT.md asks you).
