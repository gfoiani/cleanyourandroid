## What this changes

<!-- A list for a phone, a guard, a tool fix, docs... -->

## Tested on

<!-- Paste the output of python3 tools/probe.py without the serial number.
     For a list: how many days you used it, what broke, what you re-enabled, what the phone refused.
     Adding a phone: CONTRIBUTING.md section 1 has the steps. -->

## Checklist

- [ ] Nothing in this change can delete data or touch a package in `guards/`
- [ ] New list entries have a group with a tier and a comment saying what they are
- [ ] Tools changes come with a test that failed before the change
- [ ] `python3 tools/gen_tables.py` was run and `python3 -m pytest` passes
- [ ] No serial number, IMEI, phone number, account name or file from `backup/`, `work/`, `shots/`
