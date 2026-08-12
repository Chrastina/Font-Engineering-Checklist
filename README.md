# Font Engineering Checklist

A QA checklist for your font, living in a floating window inside [Glyphs](https://glyphsapp.com). Tick off what you've verified, run built-in checkers where automation makes sense, and get pointed to the right specialist tool where one already exists. Your progress is saved inside the `.glyphs` file, so it travels with the font.

By **Michal Chrastina & Kasper Pyndt**.

> **Status: in development (Phase 1).** The checklist window is functional — categories, checkboxes, progress bar, info popovers, per-font saved state, show/hide, custom checks. The checker buttons land in Phase 2.

## How it works

The checklist has 7 categories — Font Setup, Vertical Metrics, Drawing, Components & Diacritics, Spacing & Kerning, Features, Final QA — with 49 checks. Every check has an info box explaining what it's about.

There are three kinds of checks:

- **Checker checks** have a button that verifies the font programmatically. Only deterministic checks get a button — nothing that could cry wolf. If a check fails, a new tab opens with the offending glyphs plus a short report of what failed. If it passes, the checkmark ticks itself (in a distinct color, so you can tell verified from manually ticked).
- **Tool checks** point you to an existing plugin or script that already does the job well (Red Arrow, Touché, mekkablue scripts…). We deliberately don't reinvent those — the info box opens the tool directly if it's installed, and links to where to get it if not.
- **Manual checks** are your eyes and judgment. The info box explains what to look for.

Other behavior:

- **Progress bar** shows the percentage of visible checks that are ticked.
- **Show/hide**: click *Edit* above the list and every checkbox becomes an eye icon (like the Reporters palette) — click eyes to hide checks that don't apply to you, then *Done*. Global, per user.
- **Custom checks**: add your own entries to any category. Stored per machine, not in the font file.
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
- **Phase 2 — first checkers**: the pure data queries (font info, PS name length, metrics keys in sync, tabular widths, small caps coverage…) plus the failure-report pattern
- **Phase 3 — remaining checkers**: vertical metrics comparisons, anchors, carets, contour directions…
- **Phase 4 — release**: polish, docs, beta testers, Plugin Manager registration

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
