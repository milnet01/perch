# 09 — Layouts and profiles

Two orthogonal concepts, often confused, kept separate on purpose.

| | **Layout** | **Profile** |
|---|---|---|
| **What it is** | A named arrangement of windows ("coding") | A set of window geometries tied to a specific monitor topology ("docked") |
| **Triggered by** | User (tray menu / hotkey) | Perch itself, on topology change |
| **Scope** | A handful of explicitly named apps | All managed windows |
| **Lifetime** | "Until the user picks another layout" | "Until the monitor topology changes" |
| **Contains** | match → geometry pairs | references a default layout + per-topology overrides |
| **Lives in config** | `[layouts.<name>]` | `[[profiles]]` |
| **Fails gracefully if a monitor is missing** | Yes — skips windows whose target monitor is absent | No — profile won't activate if its topology doesn't match the current one |

If it helps: **a profile is "where am I (dock, laptop, TV)?"; a layout is "what am I doing (coding, watching a film, writing)?"** A user may have one of each active at once.

## Layouts

### Intent

A layout is the user saying *"when I pick 'Coding', put VS Code here, Firefox there, a terminal at the bottom."*

### Structure

(Schema sketch in [02-state-format.md](02-state-format.md); semantic details here.)

```toml
[layouts.coding]
description = "Editor left, browser right, terminal bottom."

# Order matters: windows are placed top-to-bottom, last one wins if two match.
[[layouts.coding.windows]]
match    = { app_id = "code" }
geometry = { x = "0%",  y = "0%",  w = "60%", h = "70%", monitor = "primary" }

[[layouts.coding.windows]]
match    = { app_id = "firefox" }
geometry = { x = "60%", y = "0%",  w = "40%", h = "100%", monitor = "primary" }

[[layouts.coding.windows]]
match    = { app_id = "konsole" }
geometry = { x = "0%",  y = "70%", w = "60%", h = "30%", monitor = "primary" }
```

### Apply semantics

When a layout is selected (tray menu or hotkey):

1. For every entry in the layout, find all currently-open windows matching `match`.
2. If multiple windows match one entry (two Firefox windows), apply the geometry to the **most-recently-focused** one. The others are left alone.
3. If no window matches, the entry is skipped silently. (Should Perch *launch* the app if it isn't open? Not in v1. That's session-management territory.)
4. If an entry's target monitor is not currently present, the entry is skipped and a notification lists the skipped entries.

### Partial matching

A layout entry whose `match` includes only `app_id = "firefox"` matches any Firefox window. For windows where that's not specific enough (two Firefox profiles), the user can refine with `title` regex. Identity keying in `state.json` is independent — a layout's scope is "apply to any current match," not "apply to the remembered instance."

### "Save current as layout"

The tray's *Save current window arrangement as new layout* does:

1. Snapshots every managed window's current geometry.
2. Builds a `match = { app_id = … }` entry per window.
3. Offers the user the generated TOML in a preview pane — they can edit match criteria and delete entries they don't want captured.
4. On OK, writes the new layout block into `config.toml`.

### Activating / deactivating

- Activating a layout sets `state.active_layout = "<name>"` and applies it.
- Selecting "(none)" in the tray sets `active_layout = None` — *no windows are moved* (Perch doesn't try to invert the layout). If the user wants their windows "back to before", they use "Revert layout" which is only available within the same activation (held in RAM, dropped on Perch quit).
- Activating a different layout simply applies the new one on top; windows under the new layout's matches are moved, others are not touched.

## Profiles

### Intent

*"When I dock my laptop to the desk, monitors rearrange. Perch, adapt."*

### Topology key

The **topology key** is a canonical string describing the currently connected outputs. Format:

```
<output>:<w>x<h>@<x>,<y>[;<output>:<w>x<h>@<x>,<y>][;...]
```

Segments are sorted alphabetically by output name. Example:

```
DP-1:2560x1440@0,0;HDMI-1:1920x1080@2560,360
```

This string is:

- **Stable** across reboots and cable reconnects (as long as outputs report the same name + mode).
- **Hash-friendly** — profiles are looked up by exact string match.
- **Human-readable** — users can copy it and read it.

### What it does *not* include

- Refresh rate (topologies shouldn't switch just because 60 Hz becomes 59.997 Hz).
- Scale factor (a profile's semantic is "this is my docked setup," not "this is my docked setup at 1.5× scale").
- Output serial numbers (not universally available; would make the key less portable).

This is a deliberate trade-off. If two different physical monitors report identical name + size + position, Perch treats them as the same topology. Worst case: user has two monitors of the same model and swaps them — the geometry carries over cleanly, which is probably what they wanted anyway.

### Activation

On every `output_added` / `output_removed` / `output_changed` event (debounced 300 ms):

1. Recompute the topology key.
2. If it matches an existing profile, activate it: `state.active_profile = "<name>"`. If the profile declares a `default_layout`, apply that layout too.
3. If no profile matches, activate the implicit *unnamed* profile — "running without a named profile." Last-seen restore and rules still work; layouts still work. The tray just shows *"Perch — unknown topology"*.
4. Either way, re-evaluate rules for all currently-open windows (their `context.profile` may now match or stop matching).

### Creating a profile

The config dialog's **Profiles** section lists known topologies. The current one is shown at the top with a *Name this profile…* button. The user does not type a topology key; Perch fills it in.

### Per-profile overrides for layouts

A profile can declare per-topology tweaks to shared layouts:

```toml
[[profiles]]
name     = "Docked (dual external)"
topology = "DP-1:2560x1440@0,0;HDMI-1:1920x1080@2560,360"
default_layout = "coding"

# Optional: override the coding layout's editor placement for this topology.
[[profiles.override]]
layout = "coding"
[[profiles.override.windows]]
match    = { app_id = "code" }
geometry = { x = "0%", y = "0%", w = "100%", h = "100%", monitor = "DP-1" }
```

When the layout `coding` is activated on this profile, override entries replace the corresponding entries in the base layout by `match` equality. Anything the override doesn't touch is inherited unchanged.

This allows one layout name ("coding") to mean different pixel-precise arrangements on different setups, without the user duplicating layouts.

## Interactions

- **Rules vs layouts**: rules evaluate on window events. Activating a layout is a user action, not an event — it does not trigger rules (otherwise a rule for `app_id = "code"` would fight the layout's placement). Instead, activating a layout replaces rule decisions for the windows it covers, for as long as the layout is active.
- **Layouts vs last-seen restore**: when a layout is active, a newly opened window covered by the layout's matches gets the layout's geometry, not the last-seen one. Rules still win over layout if they match (explicit user intent beats a named mode).
- **Profiles vs rules**: profiles can gate rules via `context.profile = "<name>"`. See [07-rules-engine.md](07-rules-engine.md).

## Edge cases

- **Rapid dock/undock** (cable wiggle): the 300 ms output debounce prevents thrash. Profile activation is idempotent anyway.
- **Profile matches but monitors are in a temporary "reconfiguring" state** (KWin reports outputs mid-transition): the backend queues topology changes until a 200 ms quiet period; Perch only sees the settled state.
- **User has two profiles with the same topology key**: the first one in config order wins. The dialog flags this as a validation error.
- **Adding a third monitor that changes the key**: the old profile stops matching; Perch switches to "unknown topology" until the user names the new one. Last-seen restores still work because `state.json` records geometries with explicit monitor names, not profile names.

## What profiles are *not*

- Not a way to group rules. Rules live at top level; use `context.profile` for scope.
- Not a way to persist "current window arrangement for this topology automatically." That would be a *topology-scoped last-seen* feature — plausible, but out of v1 scope. Open question tracked in [11-roadmap.md](11-roadmap.md).

## Implementation pointers

- [`src/perch/core/profiles.py`](../src/perch/core/profiles.py) — `Profile` and `ProfileOverride` dataclasses, `compute_topology_key(outputs)`, `parse_profiles(raw)` (validates duplicate names, duplicate topologies, malformed segment strings, and unknown keys), and `select_profile(profiles, key)` (first-match-wins). `src/perch/config/schema.py::validate` delegates `[[profiles]]` parsing to this module.
- [`src/perch/core/layouts.py`](../src/perch/core/layouts.py) — `Layout` / `LayoutEntry` dataclasses, `parse_layouts(raw)`. The apply algorithm (match every entry against the open windows, prefer the most-recently-focused when multiple match, skip entries whose target output is absent) lives in the reducer (M2.d); the engine emits an `ApplyActionDecision` for each layout-matched window and the reducer sequences them.
- Both sit above the rules engine and below the UI. They emit the same decision types the rules engine does, so the final "push to backend" code is one function either way.
