# Font Engineering Checklist

A QA checklist for your font, living in a floating window inside [Glyphs](https://glyphsapp.com). Tick off what you've verified, run built-in checkers where automation makes sense, and get pointed to the right specialist tool where one already exists. Your progress is saved inside the `.glyphs` file, so it travels with the font.

By **Michal Chrastina & Kasper Pyndt**.

> **Status: in development, v0.11.0.** Everything described below works. What is left is polish, an icon, screenshots, outside testing, and Plugin Manager registration.

## How it works

The checklist has 7 categories — Font Setup, Vertical Metrics, Drawing, Components & Diacritics, Spacing & Kerning, Features, Final QA — with 53 checks, 26 of which can verify themselves. Every check has an info box explaining what it is about.

There are three kinds of checks:

- **Checker checks** have a *Run Check* button in their info box that verifies the font programmatically. Only deterministic checks get one — nothing that could cry wolf. If a check fails, a new tab opens with the offending glyphs plus a short report of what failed. If it passes, the checkmark ticks itself in green, so you can tell verified from manually ticked.
- **Tool checks** point you to an existing plugin or script that already does the job well (Red Arrow, Touché, mekkablue scripts…). We deliberately don't reinvent those — the info box opens the tool directly if it's installed, and links to where to get it if not.
- **Manual checks** are your eyes and judgment. The info box explains what to look for.

Other behavior:

- **Progress bar** shows the percentage of visible checks that are ticked.
- **Show/hide**: click *Edit* above the list and every checkbox becomes an eye icon (like the Reporters palette) — click eyes to hide checks that don't apply to you, then *Done*. Global, per user.
- **Custom checks**: add your own entries to any category, each with an optional web link and an optional tool picked by searching every command in your Glyphs menus. Stored per machine, not in the font file.
- **State is saved per font** in `font.userData`, inside the `.glyphs` file. State for checks the current machine doesn't know (e.g. a collaborator's custom checks) is preserved, never pruned.
- Checker verification is a snapshot — if you edit the font afterwards, re-run the button. It's a checklist, not CI.

## Requirements

- Glyphs 3.2 or later, including the Glyphs 4 public beta
- The **Vanilla** module — one click in *Window → Plugin Manager → Modules*

## Install

Not yet in the Plugin Manager (that comes later). For now:

1. Download or clone this repository.
2. Double-click `FontEngineeringChecklist.glyphsPlugin`, confirm the install, relaunch Glyphs.
3. Find it under *Window → Font Engineering Checklist*.

## Development setup

Clone the repo and symlink the plugin into your Plugins folder(s), then relaunch Glyphs:

```bash
git clone https://github.com/Chrastina/Font-Engineering-Checklist.git ~/Documents/FontEngineeringChecklist
ln -s ~/Documents/FontEngineeringChecklist/FontEngineeringChecklist.glyphsPlugin ~/Library/"Application Support"/"Glyphs 3"/Plugins/
ln -s ~/Documents/FontEngineeringChecklist/FontEngineeringChecklist.glyphsPlugin ~/Library/"Application Support"/"Glyphs 4"/Plugins/
```

The checklist content lives in [`checks.json`](FontEngineeringChecklist.glyphsPlugin/Contents/Resources/checks.json) — ids, titles, categories, info texts, links, and which checker function backs a check. Rewording a check or adding one is a data edit, not a code change. **Check ids and the `com.michalchrastina.FontEngineeringChecklist` userData key are stable forever** — saved state in users' files depends on them.

## Roadmap

- **Phase 0 — scaffold** ✓ repo, plugin bundle, full checklist data
- **Phase 1 — usable checklist** ✓ window UI with categories, checkboxes, progress bar, info popovers, per-font persistence, show/hide, custom checks
- **Phase 2 — first checkers** ✓ Run Check in the info box, plus the pass/fail machinery (green verified ticks, failure report tabs)
- **Phase 3 — all checkers** ✓ 26 of them, each validated against a production family
- **Phase 4 — release**: icon, screenshots, beta testers, Plugin Manager registration

## Feedback welcome

Useful things to try: run the checkers against a real family and see whether any finding is wrong or noisy, add a custom check with a tool attached, hide a category and watch the progress bar, and save a file then reopen it to confirm the ticks come back. Wording of the checks and info boxes is still open to argument — they follow one convention (imperative title, then what to do and why, in plain language), so a change to one should fit the rest.

## Tools this checklist recommends

These are the specialist tools the checklist points to instead of reimplementing them — all credit to their authors:

- [Red Arrow](https://github.com/jenskutilek/RedArrow.glyphs) by Jens Kutilek — outline problems (extrema, zero handles, almost-straight segments)
- [Touché](https://github.com/yanone/Touche) by Yanone — touching pairs
- [mekkablue scripts](https://github.com/mekkablue/Glyphs-Scripts) by Rainer Erich Scheichelbauer — kink finder, overkerns, component problems, space glyphs, kerning cleanup
- [Stem Thickness](https://github.com/RafalBuchner/StemThickness) by Rafał Buchner — live stem measuring
- [Hyperglot](https://hyperglot.rosettatype.com/) by Rosetta — language coverage
- [Fontspector](https://github.com/fonttools/fontspector) — binary-level QA

## License

[MIT](LICENSE)
