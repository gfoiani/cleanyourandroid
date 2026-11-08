# OnePlus 8T (KB2003)

Android 14, OxygenOS 14.0, build `KB2003_14.0.0.1311(EX01)`, EEA, not carrier branded.
Applied on 2026-11-08; one day of use so far. Update this note after a few days.

## What changed

22 packages disabled for user 0, none uninstalled: see [debloat.txt](debloat.txt).
After `adb reboot`, `tools/check.py` found everything still off.

What you notice:

- The **Search** button at the bottom of the home screen is gone (the page dots take its place).
  The Google search bar still works.
- No OnePlus promotions or Community notifications. Weather alerts from OnePlus Weather may stop.
- The smart sidebar and the floating ball are gone.

## Kept

Every Google app, OnePlus Weather (with the clock and lock screen widgets), Instagram, LinkedIn,
Amazon Shopping and Booking.com: the person uses them.

## Refused by the phone

- `com.coloros.assistantscreen` (Shelf): OxygenOS answers the disable with `new state: default`.
  It was left on. `--fallback-uninstall` would remove it for user 0; not tried.

## Battery settings

- `tools/tune.py` cannot write global settings over USB on this phone: the answer is
  `SecurityException ... WRITE_SECURE_SETTINGS` unless "Disable permission monitoring" in Developer
  options is on. It was left off. The animation scales can be set by hand in Developer options.
- Screen timeout 30 s, adaptive brightness and the dark theme were already on.
- Adaptive battery and the automatic Battery Saver were never written: Android's defaults apply.
- `peak_refresh_rate` reads `120.00001` at 120 Hz and `60.000004` at 60 Hz.
