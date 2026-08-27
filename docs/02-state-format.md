# 02 — State format

Everything Perch persists, where it lives, and how it's versioned.

## File layout

Perch follows the XDG Base Directory spec strictly.

```
$XDG_CONFIG_HOME/perch/                   (default: ~/.config/perch/)
├── config.toml                           ← hand-editable; preferences, rules, layouts
├── config.toml.bak                       ← previous known-good config (rotated on write)
└── (nothing else)

$XDG_STATE_HOME/perch/                    (default: ~/.local/state/perch/)
├── state.json                            ← machine-written; last-seen geometries
├── state.json.bak                        ← previous known-good
└── perch.log                             ← rolling log file (size-capped)

$XDG_CACHE_HOME/perch/                    (default: ~/.cache/perch/)
└── icons/                                ← cached app icons for the config dialog
```

### Why split config and state

- **config.toml** is the *user's intent*: rules, preferences, layouts. Belongs in dotfile repos. Never written by Perch without user action.
- **state.json** is *what Perch observed*: last-seen geometries, current profile. Machine-written, frequently rewritten, not interesting to put in a dotfile repo.

Splitting them means a user can symlink `config.toml` to their dotfiles without also syncing transient runtime state.

## `config.toml` — user-facing, hand-editable

TOML was chosen because:

- Widely understood by end users (familiar from `pyproject.toml`, Cargo, many others).
- Comment-preserving round-trips are possible (we use `tomlkit` for writes, stdlib `tomllib` for reads).
- Typed primitives — no "is `1` a number or a string?" ambiguity as in YAML.

### Read / write split

- **Read**: stdlib `tomllib` (available since Python 3.11; Perch floors 3.12). Fast, strict. Used at startup and whenever Perch re-parses its own config.
- **Write**: `tomlkit>=0.13,<1`. Preserves user-authored comments, table ordering, and formatting whenever Perch rewrites the file via "Add rule" / "Rename layout" / etc.

Phase 2.5 research found no comment-preserving alternative in 2026. `tomli_w` is non-preserving and unsuitable for `config.toml`. Pin `tomlkit` to `<1` because the 1.0 release is expected to reshape the API.

**Known tomlkit footgun**: deep inline-table rewrites can occasionally drop comments that live mid-table. The test suite must include a round-trip fixture that loads a config with comments at every level, mutates it, writes it back, and asserts the comments survive. Any regression here blocks a release — silently dropping a user's comments would be an unacceptable trust violation.

### Sketch

```toml
schema_version = 1

[general]
start_at_login       = true
restore_on_open      = true     # apply remembered geometry when a window reappears
notify_on_restore    = false
theme                = "auto"   # "auto" | "light" | "dark"
onboarding_completed = false    # illustrative only — NOT emitted in the seed; absent ⇒ false. Set true once the setup wizard is dismissed (docs/08-ui.md)

[exclusions]
# Never manage these. Matched as [07-rules-engine.md] patterns.
patterns = [
  { app_id = "plasmashell" },
  { wm_class = "Plasma*",   type = "splash" },
  { title   = "^Open File$", type = "dialog" },
]

# ─── Snap presets ────────────────────────────────────────────────────────────
# Built-ins are shipped in code; this section only adds user customisation.
[snaps]
[snaps."center-60"]
geometry = { x = "20%", y = "20%", w = "60%", h = "60%", monitor = "current" }
hotkey   = "Meta+C"

# ─── Rules ───────────────────────────────────────────────────────────────────
# Evaluated top-to-bottom. First match wins. See [07-rules-engine.md].
[[rules]]
name  = "Firefox on external"
match = { app_id = "firefox" }
apply = { geometry = "maximize", monitor = "HDMI-1" }

[[rules]]
name  = "Signal top-right quarter"
match = { app_id = "signal" }
apply = { snap = "top-right-quarter" }

# ─── Layouts ─────────────────────────────────────────────────────────────────
# A named set of (match, target) pairs.  Switched on demand from the tray.
[layouts.coding]
description = "Editor left, browser right, terminal bottom."
[[layouts.coding.windows]]
match    = { app_id = "code" }
geometry = { x = "0%", y = "0%", w = "60%", h = "70%", monitor = "primary" }
[[layouts.coding.windows]]
match    = { app_id = "firefox" }
geometry = { x = "60%", y = "0%", w = "40%", h = "100%", monitor = "primary" }
[[layouts.coding.windows]]
match    = { app_id = "konsole" }
geometry = { x = "0%", y = "70%", w = "60%", h = "30%", monitor = "primary" }

# ─── Profiles (per monitor topology) ─────────────────────────────────────────
# A profile activates automatically when the topology matches.
# Topology key format:  "<output>:<w>x<h>@<x>,<y>[;<output>:...]"  sorted.
[[profiles]]
name     = "Docked (dual external)"
topology = "DP-1:2560x1440@0,0;HDMI-1:1920x1080@2560,360"
default_layout = "coding"

[[profiles]]
name     = "Laptop only"
topology = "eDP-1:1920x1200@0,0"
default_layout = "writing"
```

### Geometry expressions

A geometry can be written three ways:

1. **Absolute pixels** — `{ x = 120, y = 40, w = 1600, h = 900, monitor = "primary" }`
2. **Percent of monitor work area** — `{ x = "25%", y = "0%", w = "50%", h = "100%", monitor = "primary" }`
3. **Named preset** — `"maximize"`, `"center"`, `"left-half"`, `"top-right-quarter"`, or any user-defined preset under `[snaps]`.

The named preset `"maximize"` writes a work-area-filling rectangle as geometry — it is not the same as asking the compositor to put the window into its native *maximized state*. For that, use `maximized = true` in `apply` (see §Apply actions below). The geometry preset is universal; the state toggle is more natural for the user but depends on backend support.

`monitor` accepts:

- The output name as reported by the compositor (`DP-1`, `HDMI-1`, `eDP-1`).
- The strings `primary` (compositor's primary output), `current` (output containing the active window), or `all`.
- An integer index into the current profile's monitor list (`0`, `1`, …), stable across topology changes.

### Apply actions

Rules, layouts, and the snap-preset CLI all emit an *apply action* — a description of what to do once a match is found. Fields:

| Field | Type | Effect |
|---|---|---|
| `geometry` | geometry expression (see above) or named preset string | Place the window at this geometry. |
| `snap` | built-in snap name or user-defined `[snaps]` key | Shorthand for a geometry preset. |
| `monitor` | output name / `"primary"` / `"current"` / index | Target output for the geometry. |
| `desktop` | integer, or `"current"` / `"all"` | Virtual-desktop placement. |
| `maximized` | `true` \| `false` | Set the compositor's native maximize state (see below). |

#### `maximized` — compositor state vs. geometry preset

Perch exposes two mechanisms that look superficially similar:

1. `apply = { geometry = "maximize" }` — Perch writes `x/y/w/h` spanning the target monitor's work area. The window appears full-work-area but the compositor does not mark it as maximized: the user's maximize/restore toggle button and drag-to-unmaximize are unaffected.
2. `apply = { maximized = true }` — Perch calls `WindowBackend.set_state(wid, WindowState.MAXIMIZED)` (see [03-backend-interface.md](03-backend-interface.md) §Data types). The compositor sets its native maximized state; the user's maximize/restore affordances behave naturally; a subsequent drag-to-unmaximize restores the pre-maximize geometry.

Use `maximized = true` whenever you want the window to behave as if the user themselves had clicked "maximize." Use the `"maximize"` geometry preset when you want a specific pixel rectangle equivalent to the work area regardless of compositor state — e.g. for a pinned-by-rule position inside a layout.

**Backend support.** `maximized` needs `Capabilities.can_set_state = True` *and* the backend's `set_state(wid, WindowState.MAXIMIZED)` implementation to succeed. X11, KWin, and Mutter all implement native maximize. Sway and Hyprland declare `can_set_state = True` (they support minimize and fullscreen) but raise `BackendUnsupported` for `MAXIMIZED` specifically — their tiling models have no equivalent state. When Perch catches `BackendUnsupported`, it falls back to geometry equivalent to the `"maximize"` preset against the target monitor's work area and emits a DEBUG log line naming the rule. The fallback is documented per-backend in [04-backend-x11.md](04-backend-x11.md), [05-backend-kwin.md](05-backend-kwin.md), and [06-backend-stubs.md](06-backend-stubs.md).

**Interaction with `geometry`.** `maximized = true` together with an explicit `geometry` is a contradiction; the config loader rejects it. `maximized = false` with `geometry = ...` is permitted and means "unmaximize first, then move/resize" — useful for layouts that reposition a previously-maximized window (on backends where setting geometry on a maximized window is a no-op; see [06-backend-stubs.md](06-backend-stubs.md) §Mutter).

Example:

```toml
[[rules]]
name  = "Firefox maximised on external"
match = { app_id = "firefox" }
apply = { maximized = true, monitor = "HDMI-1" }
```

### Match patterns

Used by `exclusions`, `rules`, and `layouts.*.windows`. Fields:

| Field | Matches against | Wildcard |
|---|---|---|
| `app_id` | Wayland `app_id`, or X11 `WM_CLASS` instance | glob |
| `wm_class` | X11 `WM_CLASS` class (fallback for cross-compat) | glob |
| `title` | Window title | regex (anchored with `^`/`$` if the user wants) |
| `pid` | Process id (rarely used; for one-shot targeting) | exact |
| `type` | Window type (`normal`, `dialog`, `splash`, `utility`, …) | exact, comma list |

All specified fields must match (`AND`). An empty match object matches everything (useful in layouts as a "fallback for unmatched windows" entry).

## `state.json` — machine-written, rewritten often

JSON because:

- Fast to parse, trivial to round-trip without worrying about comments.
- No human has any business editing this file.

### Sketch

```json
{
  "schema_version": 1,
  "active_profile": "Docked (dual external)",
  "active_layout":  "coding",
  "windows": {
    "app:firefox::primary": {
      "identity": { "app_id": "firefox" },
      "last_seen": "2026-05-01T14:22:03Z",
      "geometry": { "x": 0,   "y": 0,    "w": 2560, "h": 1440, "monitor": "DP-1",  "desktop": 1 }
    },
    "app:code::title:~/perch": {
      "identity": { "app_id": "code", "title_regex": "^~/perch" },
      "last_seen": "2026-05-01T14:22:59Z",
      "geometry": { "x": 0,   "y": 0,    "w": 1600, "h": 1000, "monitor": "DP-1",  "desktop": 1 }
    }
  },
  "topology_history": [
    { "key": "eDP-1:1920x1200@0,0",
      "first_seen": "2026-04-10T08:00:00Z",
      "last_seen":  "2026-04-30T18:01:00Z" }
  ]
}
```

### Identity keying

Each entry in `windows` is keyed by a stable **identity string**. Construction rule:

```
identity = "app:<app_id>" [ "::title:<title_regex>" ] [ "::rolespecific:<X>" ]
```

- The *first* segment is always `app:<app_id>` (falling back to `app:<wm_class>` on X11 when `app_id` is not known).
- Extra segments are added when the user (or a rule) pins on title / role / pid.

This ensures two Firefox windows with different profiles can be remembered separately if the user has asked for title-based distinction, but otherwise collapse into one remembered geometry.

## Atomic writes

Every disk write follows the same recipe to survive crashes and power loss:

1. Write the new content to `path.tmp` in the same directory.
2. `fsync` the temp file.
3. Rename `path` → `path.bak` (if it exists).
4. Rename `path.tmp` → `path`.
5. `fsync` the directory.

`path.bak` is the last known-good. Perch never deletes it; it is overwritten only by the next successful write. If `path` fails to parse on next start, Perch loads `path.bak` and logs a warning.

## Write cadence

- **`config.toml`** — only written in response to an explicit user action (editing in the dialog, import, "Forget this window"). Never auto-written.
- **`state.json`** — written on a debounced schedule: no more often than every 5 s, and always on clean shutdown. A single geometry change does not trigger an immediate flush.

## Versioning and migration

- `schema_version = 1` at the top of both files.
- Perch refuses to load a file whose `schema_version` is higher than it understands (forward-compat: the user probably installed a newer Perch, then rolled back).
- A file with a lower version is **migrated in memory**, and the migrated version is **not written back** until the user makes a change. This keeps a user's dotfiles repo stable across Perch upgrades — the file only changes when the user changes something.
- Migrations live in a small registry: `migrations/v1_to_v2.py`, etc. Each migration is a pure function `dict → dict`.

## Export / import

- **Export**: writes `config.toml` as-is to a user-chosen path. Does *not* include `state.json` — last-seen geometries are machine-local and not worth shipping.
- **Import**: reads a TOML file, validates its schema, offers a dry-run diff in the UI ("5 rules added, 2 layouts changed, 1 rule conflict"), and on confirmation replaces the current `config.toml` atomically.

### Round-trip criterion

Goal 8 of [`00-overview.md`](00-overview.md) — *"user config survives a reinstall or moves to a new machine"* — is met when exporting on machine A and importing on machine B leaves B's `config.toml` byte-identical to the exported file, and B's behaviour differs from A's only where the hardware does.

Three classes, named so the bar is falsifiable:

- **Must come across** — the whole of `config.toml`: `schema_version`, `[general]`, `[exclusions]`, `[snaps]`, every `[[rules]]`, every `[layouts.*]`, every `[[profiles]]`. Export copies the file verbatim and import replaces it atomically, so a partial transfer is a defect, not a design choice.
- **Need not come across** — `state.json`: last-seen geometries, active profile, active layout. B restores nothing until it has observed a window itself. An imported machine that places no windows on first launch has succeeded, not failed.
- **Comes across but may not fire** — anything keyed to hardware: a rule or layout naming `monitor = "HDMI-1"`, a profile `topology` string. The entry must be present and valid on B; it stays inert until B has an output of that name. Perch never rewrites output names on import, and an unmatched topology leaves B on "unknown topology" ([`09-layouts-profiles.md`](09-layouts-profiles.md)).

Coverage: both halves are exercised by `tests/ui/test_import_export_pane.py` — import through validation, dry-run diff and atomic replace; export by calling `ImportExportPage._on_export` with the file picker stubbed, and asserting the written file is byte-identical to `config.toml`.

## Log file

- Path: `$XDG_STATE_HOME/perch/perch.log`.
- Rotates at 1 MB; keeps two old files (`perch.log.1`, `perch.log.2`).
- Default level: `INFO`. `PERCH_DEBUG=1` in the environment bumps to `DEBUG`.
- Never contains window titles by default (privacy: many titles leak file paths, URLs, chat counterparties). `PERCH_LOG_TITLES=1` opts in.

## Flatpak considerations

Under Flatpak, XDG paths resolve inside the sandbox. `~/.config/perch/` becomes `~/.var/app/io.github.milnet01.Perch/config/perch/`.

That's fine for `state.json` but means `config.toml` lives somewhere users don't expect. Perch documents this location prominently in the config dialog's "Open config folder" button and in the manual. For users who want their config in `~/.config/`, the Flatpak manifest grants `--filesystem=xdg-config/perch:create` so the user can symlink — documented but not enforced.

## Schema reference

The exact schema (keys, types, defaults, validation rules) is authoritative in code: [`src/perch/config/schema.py`](../src/perch/config/schema.py). This document covers shape and intent; the code is the source of truth for the field list at any given version.

Read / validate / seed logic lives in [`src/perch/config/loader.py`](../src/perch/config/loader.py). The atomic-write recipe described above in §Atomic writes is implemented in [`src/perch/config/writer.py`](../src/perch/config/writer.py). The migration registry lives at [`src/perch/config/migrations/__init__.py`](../src/perch/config/migrations/__init__.py); it is wired but empty at schema version 1. A failing migration — or a document whose `schema_version` exceeds what this Perch understands — surfaces as a `ConfigError` that produces a non-zero exit and a pinpoint log line.

Comment preservation across `config.toml` round-trips is enforced by `tests/test_config_roundtrip.py`, which exercises the representative document shapes (top-level, `[general]`, `[exclusions]`, nested `[snaps.*]`, `[[rules]]`, `[layouts.<name>.windows]`, `[[profiles]]`). A failure in that test is treated as release-blocking per the trust-violation note above.

`state.json` persistence lives in [`src/perch/core/state_store.py`](../src/perch/core/state_store.py) — `StateStore` owns load / atomic-write-with-`.bak`-rotation / debounced flush. The reducer ([`src/perch/core/reducer.py`](../src/perch/core/reducer.py)) calls `record_window` after every backend `set_geometry` and on user-initiated drag events, and schedules a debounced flush via `mark_dirty`. The 5-second debounce and the clean-shutdown flush promise of §Write cadence are both implemented here.
