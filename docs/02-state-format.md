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
start_at_login     = true
restore_on_open    = true       # apply remembered geometry when a window reappears
notify_on_restore  = false
theme              = "auto"     # "auto" | "light" | "dark"

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

`monitor` accepts:

- The output name as reported by the compositor (`DP-1`, `HDMI-1`, `eDP-1`).
- The strings `primary` (compositor's primary output), `current` (output containing the active window), or `all`.
- An integer index into the current profile's monitor list (`0`, `1`, …), stable across topology changes.

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

A separate "Include last-seen geometries" checkbox lets power users export state too, if they want to pre-seed a new machine.

## Log file

- Path: `$XDG_STATE_HOME/perch/perch.log`.
- Rotates at 1 MB; keeps two old files (`perch.log.1`, `perch.log.2`).
- Default level: `INFO`. `PERCH_DEBUG=1` in the environment bumps to `DEBUG`.
- Never contains window titles by default (privacy: many titles leak file paths, URLs, chat counterparties). `PERCH_LOG_TITLES=1` opts in.

## Flatpak considerations

Under Flatpak, XDG paths resolve inside the sandbox. `~/.config/perch/` becomes `~/.var/app/io.github.milnet01.Perch/config/perch/`.

That's fine for `state.json` but means `config.toml` lives somewhere users don't expect. Perch documents this location prominently in the config dialog's "Open config folder" button and in the manual. For users who want their config in `~/.config/`, the Flatpak manifest grants `--filesystem=xdg-config/perch:create` so the user can symlink — documented but not enforced.

## Schema reference

The exact schema (keys, types, defaults, validation rules) is authoritative in code once M1 lands: `perch/config/schema.py`. This document covers shape and intent; the code is the source of truth for the field list at any given version.
