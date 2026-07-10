# Accessibility & i18n standard

How Perch's Qt Widgets UI stays keyboard-driveable, screen-reader-legible and
translatable. This is the conventions companion to [08-ui.md](08-ui.md)
§Accessibility / §Localization; that doc is authoritative on behaviour, this one
on the rules a new widget must satisfy. Where a11y today is partial, this doc
says so rather than overstating it.

## Accessibility

### What Perch does today (M7.a–M7.f, shipped)

- **Keyboard navigation is complete for the config dialog.** The section
  sidebar receives initial focus; an explicit `setTabOrder(sidebar → stack →
  buttons)` chain in `dialog.py` pins Tab order sidebar → active page →
  OK/Apply/Cancel; arrow keys move within the sidebar and list/table views.
- **Delete / Backspace removes the selected row** on the Rules table and the
  Exclusions list via the in-tree `_DeleteKeyTableView` / `_DeleteKeyListWidget`
  subclasses. A plain `QShortcut` does not work here — `QTableView.keyPressEvent`
  swallows the key for cell editing before a `WidgetWithChildrenShortcut`
  resolver sees it, so the key is handled in the subclass instead.
- **Accessible names/descriptions on key surfaces.** Use `setAccessibleName`
  and `setAccessibleDescription` so Orca and Qt's accessibility bridge announce
  widgets sensibly: sidebar → "Sections", rules table → "Rules table",
  exclusions list → "Exclusion patterns", plus Managed windows, Layouts, Layout
  entries, Profiles, Layout overrides. Check-box / combo-box widgets inherit
  their accessible name from their buddy label automatically, so a bare label +
  control needs no extra call.
- **Colour is never the sole signal.** Error rows carry an icon as well as red
  text; the tray warning/error icon variants overlay an amber/red badge on the
  silhouette *and* change the tooltip, so the state survives panel recolouring
  and colour-blind users.
- **System theme / contrast is respected.** `theme = auto` defers to the
  platform colour scheme (see [ui-standards.md](ui-standards.md) §Theming);
  widgets read colours from the active `QPalette`, so a high-contrast system
  palette flows through.
- **HiDPI:** icons are SVG; dialog geometry values are logical pixels.

### Rules for new controls

- Every interactive control must be reachable and operable by keyboard alone —
  if a new control needs a non-obvious key (delete-row, record-hotkey), handle
  it in a `keyPressEvent` override, and extend the Tab-order chain if the widget
  sits outside the sidebar → page → buttons flow.
- Give every non-trivial view/list/table a `setAccessibleName`; add a
  `setAccessibleDescription` where the name alone is ambiguous. Wrap both in
  `self.tr(...)` — accessible strings are user-facing.
- Do not encode meaning in colour alone; pair it with an icon, text or shape.

### Honestly partial

A broader **accessibility pass on the config dialog is still on the roadmap**
(see [11-roadmap.md](11-roadmap.md), deferred items). M7 covered keyboard nav +
accessible names on the primary surfaces; it did not audit every editor sub-dialog
(`EntryEditorDialog`, the match/geometry editors) for a full screen-reader pass,
and there is no automated a11y regression test beyond the keyboard tests in
`tests/ui/test_dialog_keyboard.py`. Treat sub-dialog a11y as best-effort until
that pass lands.

## Internationalization

### Marking strings

- **Every user-facing string is wrapped for translation.** On `QObject`
  subclasses use `self.tr("…")` (≈150 call sites); in non-`QObject` / module-level
  code use `QCoreApplication.translate("<context>", "…")`; mark
  deferred/table-driven literals with `QT_TR_NOOP("…")` and translate at display
  time against the same context.
- `pyside6-lupdate` extracts **only** these literal forms. Do not route a string
  through a Python wrapper/format helper before wrapping — extraction silently
  drops it. Keep the `tr` / `translate` / `QT_TR_NOOP` call on the literal.
- **Never concatenate translated fragments.** Use a single translatable string
  with named placeholders and `.format()`: e.g.
  `self.tr("Backend rejected set_geometry: {err}").format(err=str(exc))`. This
  keeps word order translatable for languages that reorder clauses. Building a
  sentence from `tr("A ") + value + tr(" B")` is forbidden.
- Log messages that are **shown to the user** are localizable; messages that
  only land in `perch.log` stay English (translating them adds noise to bug
  reports).

### `.ts` → `.qm` workflow

- Sources live at `translations/perch_<locale>.ts` (Qt Linguist XML). The Qt
  convention `translations/` is used deliberately — **not** `po/`, which signals
  gettext and is incompatible with Qt's `.ts`.
- **Extract / update** with `scripts/i18n-update.sh`, which runs
  `pyside6-lupdate -extensions py src/perch -ts translations/perch_en.ts
  -source-language en_US`. Run it after adding or changing any user-visible
  string and commit the updated `.ts` alongside the code (no-doc-debt); a
  translator fills the `<translation>` elements later.
- **Compile** to `.qm` with `pyside6-lrelease translations/*.ts` (or
  `lrelease-qt6`). Both ship with the PySide6 wheel — no extra build dep. `.qm`
  files are produced at **package build time**, not committed: the RPM spec
  (`packaging/rpm/perch.spec`) runs `lrelease-qt6` / `pyside6-lrelease` into
  `%{_datadir}/perch/translations/`, and the AUR `PKGBUILD` installs any
  `translations/*.qm` it finds.
- **Runtime loading** is `src/perch/i18n.py::install_translators`, using
  `QTranslator.load(...)` for both `qtbase` and `perch`. The `QTranslator`
  instances are **module-level on purpose** — Qt holds only weak references, so
  letting them fall out of scope makes the GC reclaim them and every string
  silently reverts to English (the #1 PySide6 i18n footgun). Directory lookup
  order: `$PERCH_TRANSLATIONS_DIR` → `/app/share/perch/translations` (Flatpak) →
  `$sys.prefix/share/perch/translations` → dev-checkout fallback. A missing
  locale is a graceful no-op: `load` returns False and English stays.

### Right-to-left

Perch does not add RTL-specific code, and relies on Qt's automatic mirroring:
`QApplication` flips layout direction for RTL locales and the widget layouts are
direction-agnostic (no hard-coded left/right margins in logic). This is
**untested** — no RTL locale ships yet — so treat RTL as "should work via Qt"
rather than verified. Avoid any layout that assumes left-to-right reading order.

## See also

- [08-ui.md](08-ui.md) — authoritative UI design (§Accessibility, §Localization).
- [ui-standards.md](ui-standards.md) — Qt 6 idioms, theming, async, `self.tr`.
- [coding-standards.md](coding-standards.md) — general Python/async conventions.
- [09-layouts-profiles.md](09-layouts-profiles.md) — the layout/profile editors
  whose sub-dialogs the deferred a11y pass still needs to cover.
- [../CLAUDE.md](../CLAUDE.md) — project-wide docs-first / current-idiom rules.
