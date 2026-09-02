# UI standard

Conventions every widget under `src/perch/ui/` follows. This is the *how we
write UI code* companion to [08-ui.md](08-ui.md), which is the authoritative
design doc for what the tray and dialog actually contain. When the two
disagree, 08-ui.md wins on behaviour and this file wins on idiom; fix whichever
is stale in the same change (no-doc-debt rule).

## Toolkit

- **Qt 6 Widgets via PySide6** (Qt ≥ 6.8), never QML. Widgets render correctly
  on X11, Wayland, HiDPI and every theme without a QML runtime, and Perch is
  not animation-heavy. See [08-ui.md](08-ui.md) §Principles.
- One asyncio event loop drives both Qt and asyncio through **qasync**.
- UI code reads from `perch.core.state` and fires `perch.core.intents`; it
  **never imports `perch.backend.*` directly**.

## Mandatory Qt 6 idioms

These are hard requirements — the global rule in [../CLAUDE.md](../CLAUDE.md)
mandates current-version idioms, and `audit_config.yaml` carries drift
detectors for several of them.

- **New-style signal/slot connect only.** Bind the typed member signal to a
  callable: `sender.triggered.connect(self._on_thing)`. Every connect in the
  tree already uses this form (`tray.py`, `dialog.py`, `status.py`). Never use
  the string-based `connect(sender, SIGNAL("..."), ...)` / `SLOT(...)` macros —
  they are unchecked at import time and are treated as build-breaking.
- **Overloaded signals** are disambiguated the PySide6 way — connect the
  specific typed member (e.g. `combo.currentIndexChanged` /
  `activated[int]`), not a stringly-typed overload. Reach for `QOverload`-style
  selection only where an overload is genuinely ambiguous.
- **QObject lifetime:** rely on Qt parent-ownership plus a strong Python
  attribute for objects Qt does not own. `TrayIcon` keeps its menu alive with
  `self._menu` and its actions in `self._menu_actions` because
  `QSystemTrayIcon` does not take menu ownership on every platform. Where a
  bare non-owning handle to a QObject is genuinely needed, `QPointer` (which
  auto-nulls when the object is destroyed) is the tool — but in PySide6, Python
  refcounting plus parent-ownership almost always suffices, so reach for it
  rarely. (The C++ `QWeakPointer` lifetime foot-gun doesn't arise here — it
  isn't exposed to Python.)
- **String literals:** Python has no `QStringLiteral`; the equivalent
  discipline here is that every user-visible literal is wrapped for translation
  (below) rather than passed raw.
- Prefer `QAction` for menu/toolbar items (the tray menu is built entirely from
  `menu.addAction(...)` returning `QAction`s), and set `setToolTip` /
  `setCheckable` / `setChecked` on the action, not on ad-hoc state.

## Async in the UI

- Long or awaitable work runs through **`qasync.asyncSlot`**, never a blocking
  call on the Qt thread. The dialog's apply-preset path wraps its coroutine as
  `slot = qasync.asyncSlot()(_apply); slot()`; the reducer binds backend
  signals via `qasync.asyncSlot(object)(self._on_window_opened)`.
- **Never block the event loop** — no synchronous D-Bus round-trips, no
  `time.sleep`, no long CPU loops in a slot. (The one deliberate exception is
  `sni_probe.py`, which uses `sdbus_block` *because it runs before the qasync
  loop is live*; it is documented as such.)
- **Forbidden:** `asyncio.get_event_loop()`. Under qasync the loop is Qt's;
  acquire it via qasync/`asyncio.get_running_loop()` inside a running slot. The
  `audit_config.yaml` drift detectors flag `get_event_loop()`.
- Import qasync locally in modules that must stay importable without it (the
  reducer does `import qasync` inside `bind_signals` so pure-core tests need no
  qasync dependency).

## Structure

- `tray.py` — `TrayIcon(QSystemTrayIcon)` + the pure `build_tray_menu(state,
  controller)` builder + `TrayController(QObject)` that emits `Intent`s. The
  menu is a pure function of state and is rebuilt on every state change
  (`setContextMenu(new_menu)`); `QMenu.aboutToShow` is deliberately unused
  (QTBUG-55911). Keep the builder pure so it stays testable without a tray host.
- `dialog.py` — `ConfigDialog(QDialog)` and one page widget per section
  (General / Windows / Rules / Layouts / Profiles / Hotkeys / Exclusions /
  Import-Export). Section content is specified in [08-ui.md](08-ui.md); do not
  re-document it here.
- `widgets/` — reusable pieces (match editor, geometry editor, key capture).
- Models are `QAbstractTableModel` subclasses (`rules_model.py`,
  `windows_model.py`) backed by working copies of the dataclasses; `QTableView`
  over `QTableWidget` so presentation stays separate from state.

## Theming

- Palette/style application lives in `theming.py::apply_theme(app, theme)`, run
  once at startup from `app.py`. `[general].theme` is `auto | light | dark`.
- **Be palette-aware, never hard-code colours.** `auto` reads
  `QGuiApplication.styleHints().colorScheme()` (Qt 6.5+) and leaves the palette
  untouched when the platform reports `Qt.ColorScheme.Unknown` (correct on
  Plasma/Breeze); `light`/`dark` force Fusion + a Breeze-inspired `QPalette`.
  New widgets must read their colours from the active `QPalette`
  (`QPalette.ColorRole.*`) so both themes render correctly.
- Icons are symbolic SVG resolved via `QIcon.fromTheme(...)` with a bundled
  fallback (`icons.py`); no raster variants — Qt's SVG renderer covers every
  HiDPI scale factor.

## Translatability

- **Every user-visible string is wrapped for translation.** The marking rules
  (`self.tr` / `QCoreApplication.translate`, the `QT_TRANSLATE_NOOP`
  context-matching caveat, and the one known-broken exception — the tray
  snap-preset labels) and the `.ts` → `.qm` workflow live in one place:
  [accessibility-i18n-standards.md](accessibility-i18n-standards.md) §Marking
  strings.

## See also

- [08-ui.md](08-ui.md) — authoritative UI design (tray, dialog panes,
  interaction model).
- [accessibility-i18n-standards.md](accessibility-i18n-standards.md) —
  keyboard nav, accessible names, and the `.ts` → `.qm` translation workflow.
- [coding-standards.md](coding-standards.md) — the general Python/async
  conventions these UI rules build on.
- [../CLAUDE.md](../CLAUDE.md) — the project-wide current-idiom rule these
  conventions enforce.
