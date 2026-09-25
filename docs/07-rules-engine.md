# 07 — Rules engine

How Perch decides *what to do* when a window event arrives.

## Inputs and outputs

**Inputs** to a rule evaluation:

- A `WindowInfo` (from the backend).
- The event that triggered evaluation: `opened`, `changed`, or an explicit user trigger ("Apply rules now").
- The currently active **profile** (selected by monitor topology; see [09-layouts-profiles.md](09-layouts-profiles.md)).
- The currently active **layout**, if any.

**Output** of a rule evaluation: at most **one** decision, which is a union of:

- `IGNORE` — do nothing. (Used by exclusions.)
- `RESTORE_LAST_SEEN` — apply the remembered geometry for this identity, if any.
- `APPLY_ACTION(action)` — apply the matched rule's or layout's `apply` block (see [02-state-format.md](02-state-format.md) §Apply actions). The action carries any combination of `geometry`, `snap`, `monitor`, `desktop`, and `maximized` — the reducer applies them together (§Apply order).

The engine never emits more than one decision per window per event. Chaining ("apply layout X *then* move to monitor 2") is expressed inside a single layout or rule, not by stacking decisions.

## Evaluation order

Top to bottom, first match wins. The order is:

1. **Built-in exclusion: system surfaces.** Emits `IGNORE`. Not configurable. Concrete list at `src/perch/core/exclusions.py::BUILTIN_EXCLUDED_TYPES` — currently `WindowType.DESKTOP` and `WindowType.DOCK`. X11 override-redirect windows and Wayland layer-shell surfaces are filtered upstream by the backend and never reach the engine.
2. **User exclusions** (`[exclusions]` in config). Emits `IGNORE`.
3. **User rules** (`[[rules]]`, in config order). First match whose `context` also matches — `APPLY_ACTION`. Context mismatches are skipped silently, not treated as misses.
4. **Active layout**, if one is set and has an entry matching this window. `APPLY_ACTION` using the layout entry's `apply`.
5. **Last-seen geometry** from `state.json`, if `general.restore_on_open = true` and we have an entry. Emits `RESTORE_LAST_SEEN`. Only fires on `OPENED` / `USER_TRIGGER`; on `CHANGED` the engine falls through to `IGNORE`.
6. **Do nothing.** (`IGNORE` with `source = "no-match"`.)

This ordering is deliberate:

- Exclusions always win so a user can always say "never touch this."
- Rules beat layouts because rules are more explicit user intent ("*always* X").
- Layouts beat last-seen because activating a layout is a current, explicit user action.
- Last-seen is the fallback for the many windows that have no rule or layout entry.

## Matching

A rule's `match` is an AND over its specified fields. The field semantics are defined in [02-state-format.md](02-state-format.md). Key points:

- Unspecified fields are wildcards. `match = { app_id = "firefox" }` matches every Firefox window.
- `title` supports regex; all others are glob (`*`, `?`, `[abc]`). Regexes are validated with Python `re` syntax and searched (`re.search` semantics) — anchor them if you want a full match.
- A title search is bounded in time. Titles come from any application the user runs, and a pattern with catastrophic backtracking — `(a+)+$` is eight characters — would otherwise freeze the one thread that drives both the tray and the event loop. `src/perch/core/matching.py::match_window` runs the search through the `regex` package with a 50 ms timeout; a search that runs out counts as **no match**, and the pattern is logged once at WARNING so the user can fix it. The timeout is per title per pattern.
- Missing attributes on the window (`pid` is `None`, `role` is `""`) fail to match only if the corresponding `match` field was specified.

### Matching on multiple monitors

A rule can include a `context` block that gates matching on the current session:

```toml
[[rules]]
name = "Editor max on external, windowed on laptop"
match = { app_id = "code" }
context = { profile = "Docked (dual external)" }
apply = { geometry = "maximize", monitor = "DP-1" }

[[rules]]
match = { app_id = "code" }
context = { profile = "Laptop only" }
apply = { geometry = { x = "10%", y = "5%", w = "80%", h = "90%", monitor = "primary" } }
```

Same match, different action per profile. `context` also accepts `layout` and `desktop` (current desktop index) for finer control.

## Conflict resolution

When two rules would match:

- **Explicit order** always wins. The user writes them top-to-bottom in `config.toml` and that order is the priority.
- There is no implicit specificity heuristic (unlike CSS selectors). A rule matching `app_id = "firefox"` placed before a rule matching `app_id = "firefox", title = ".*Private.*"` will win, even though the second is "more specific." This is a deliberate choice — implicit specificity would make "why did *this* rule win?" hard to explain.
- The config dialog surfaces order with drag-to-reorder; see [08-ui.md](08-ui.md).

## Geometry resolution

When an action's `geometry` or `snap` is applied, Perch resolves it to pixel coordinates:

1. Named preset → its stored geometry. The built-ins (`"left-half"`, `"top-right-quarter"`, `"maximize"`, `"center"`, …) are fixed `x%/y%/w%/h%` of the target monitor's work area, except `"center-in-place"`, which centres the window there at its current size. A user-defined preset under `[snaps]` is its own absolute or percent geometry, resolved by the rules below.
2. Percent values → multiplied by the target monitor's work area, rounded to ints, then clamped to it. Percentages are not range-checked when the config is parsed, so `"-50%"` is caught here.
3. Absolute pixel values → offsets from the top-left of the target monitor's work area, then clamped to it. So `x = 120` on `HDMI-1` lands 120 px in from HDMI-1's usable left edge, wherever HDMI-1 sits on the desktop. Neither form can push a window off-screen.
4. `monitor = "primary"` → the connected output flagged primary; `"current"` → the output the window is on; an integer index → that position (0-based) in the active profile's output list.
5. `monitor` as an output name (`"DP-1"`) → resolved directly; if that output is currently disconnected, the decision is dropped with a warning (not reassigned to primary — that would silently do the wrong thing). Evaluation does not fall through to a later rule, the layout or last-seen.

## Apply order

An action can mix `maximized`, `geometry`/`snap`, `monitor`, and `desktop`. The reducer issues them in a fixed order so the user-visible result is deterministic:

1. If `maximized = false` (explicit), unmaximize first. This lets a subsequent `set_geometry` actually move the window on backends that ignore geometry writes on maximized windows (Mutter; see [06-backend-stubs.md](06-backend-stubs.md)).
2. When the rule sets a `desktop`, the core passes it in the `set_geometry(…, desktop=…)` call; when it sets none, the core passes `None` and the window stays on its desktop. Inside that one call, which `docs/03-backend-interface.md` makes atomic, each backend moves the desktop before the geometry — a window manager is free to re-place a window when its desktop changes, so the placement has to be the last word.
3. If `geometry` / `snap` is set, apply it (with `monitor` resolving the target output).
   If `monitor` is set without `geometry` / `snap` and resolves to a different output, the resolver moves the window itself. The window keeps its offset from the top-left of its current output's work area and lands at the same offset in the target output's work area. A window larger than the target work area shrinks to it, and the result is clamped inside it. The window's current output is the one the backend reports it on. The backend only ever receives global coordinates ([03-backend-interface.md](03-backend-interface.md) §Coordinate system). When the target is the output the window is already on, its current geometry passes through unchanged, so only step 2's desktop move takes effect.
4. If `maximized = true`, call `set_state(wid, WindowState.MAXIMIZED)`.

If a backend cannot set the native maximized state and the action sets `maximized = true`, Perch substitutes `geometry = "maximize"` against the **resolved target** monitor and logs at DEBUG, naming the rule. Both routes to that arrive the same way — a backend declaring `can_set_state = False`, and one that declares it can but raises `BackendUnsupported` for `MAXIMIZED` specifically (Sway, Hyprland), both raise `BackendUnsupported` from `set_state`, and that is what the reducer catches. This is the only automatic substitution the engine performs; the semantic difference is noted at [02-state-format.md](02-state-format.md) §Apply actions.

## Reactive evaluation

The engine is reactive:

- Evaluated on `window_opened`, always.
- Evaluated on `window_changed` only for fields that can affect matching: `title`, `type`, `state`. Not on geometry changes (that would create a feedback loop every time Perch moves a window). A decision from a `window_changed` evaluation is applied only when its source (the rule or layout that matched) differs from the one last applied to that window. So a tab switch that keeps the same rule matching leaves a window the user moved where it is, and a title change that makes a different rule match moves it.
- Evaluated on `output_added` / `output_removed` / `output_changed` *indirectly*: these may change the active profile, which re-triggers evaluation of all visible windows under the new profile.

Geometry changes coming *from the user* (drag-resize) are treated as signal and recorded into `state.json` for later `RESTORE_LAST_SEEN`. They do not trigger rule re-evaluation.

## Feedback-loop prevention

If a rule applies a geometry that doesn't match what the user wanted, Perch must not fight the user. Protections:

- Evaluation is *only* triggered by the events listed above. Perch never re-applies a geometry it just set.
- After `set_geometry`, Perch records the applied values as "expected current geometry." The next `geometry_changed` matching those values is silently dropped.
- A subsequent `geometry_changed` that does *not* match (i.e. the user dragged the window) updates `state.json` but does not re-trigger the rule. Even if the rule is a "pin this window to (100,100)" rule, Perch does not forcibly pull it back. Pinning-style behaviour would require a v2 "enforcement mode" explicitly opt-in per rule.

## Dry-run mode

The config dialog has a "Dry run" toggle while editing rules. With dry-run on:

- Rules are evaluated on every event as normal.
- The resulting decision is *logged* (and shown in a small "Rules trace" panel in the dialog) but not applied.
- Lets users see "this window would have been moved to DP-1 by rule X" without actually moving anything.

Dry-run is UI-state only; it does not persist to disk.

## Performance model

Window events are rare (dozens per minute at most during heavy use). Matching is a linear scan through the rules list. No indexing, no RETE, no compiled matchers — for v1 this is fine.

**Measured** (M7.d harness at `tests/core/test_engine_performance.py`, worst case: each window's matching rule is placed last in the rules list):

| Scale | Wall time |
|---|---|
| 100 rules × 100 windows | ~5 ms |
| 500 rules × 500 windows | ~55 ms |
| 1000 rules × 1000 windows | ~200 ms |

Budgets in the harness are deliberately 10-20× the measured times so CI runner jitter doesn't flake the test; the point is to catch accidental quadratic regressions, not to pin a tight latency number. If a user with a 500+-rule config ever materialises and the measured numbers climb toward the budgets, revisit — compiled regex caches and app_id → rule-index prefiltering are the obvious first cuts.

## Debugging and observability

- Every rule evaluation logs at `DEBUG` with `(window_identity, chosen_rule, decision)`.
- The dialog's "Rules trace" panel shows the last N evaluations live.
- `perch --test-rules <path-to-config.toml>` (post-v1; tracked as PERC-0016 in [`ROADMAP.md`](../ROADMAP.md)) replays a saved event stream against a config for regression testing.

## Validation

The config loader rejects a rule with:

- A `match` block that is entirely empty (would match every window — users almost never want that; use an explicit `catch_all = true` field if you really do).
- A `match` block combining `catch_all = true` with any other field. `catch_all` short-circuits, so the other fields would never be consulted and the config would say one thing and do another.
- Any `match` or `apply` string field written as `""`.
- `monitor = "all"`, at the apply level or inside a `geometry` table. Nothing fans one action out across every output; the valid forms are an output name, `"primary"`, `"current"`, or an integer index.
- A `[[profiles]]` entry whose `default_layout` names a layout that is not declared under `[layouts]`.
- An `apply` block that has no effect — i.e. none of `geometry`, `snap`, `monitor`, `maximized`, `desktop` is set. `maximized = false` alone is a legitimate unmaximize action and is accepted.
- An `apply` block setting both `maximized = true` and an explicit `geometry` or `snap` (contradiction — see [02-state-format.md](02-state-format.md) §Apply actions). `maximized = false` alongside a geometry/snap is allowed and means "unmaximize first, then place."
- An `apply` block specifying `monitor` both at the apply level and inside the `geometry` table with *different* values. Redundant-but-agreeing specifications are accepted.
- `geometry` and `snap` together (mutually exclusive — two ways of writing the same "where" intent).
- A `monitor` referring to an output index higher than the current profile declares (checked by the resolver when the rule fires; the parser accepts any non-negative index).
- A `snap` name not in the built-in set or the user's `[snaps]` table. This check runs at apply time inside the resolver ([`src/perch/core/resolver.py`](../src/perch/core/resolver.py)), not at parse time, so a rule that refers to a snap via a variable will only fail when it fires — the failure surfaces as a logged warning and the decision is dropped, as for a disconnected output (§Geometry resolution).

Validation errors are shown in the config dialog's problem inspector; Perch does not silently drop bad rules.

## Implementation pointers

- [`src/perch/core/matching.py`](../src/perch/core/matching.py) — `MatchPattern` + `parse_match` + `match_window`.
- [`src/perch/core/actions.py`](../src/perch/core/actions.py) — `ApplyAction`, the `GeometryExpr` ADT (`AbsoluteGeometry` / `PercentGeometry` / `PresetGeometry` / `CenterKeepSize`), `BUILTIN_PRESETS`, `parse_action`. Geometry resolution to pixels lives in [`src/perch/core/resolver.py`](../src/perch/core/resolver.py) (M2.d).
- [`src/perch/core/rules.py`](../src/perch/core/rules.py) — `Rule`, `Context`, `parse_rules`.
- [`src/perch/core/layouts.py`](../src/perch/core/layouts.py) — `Layout`, `LayoutEntry`, `parse_layouts`.
- [`src/perch/core/exclusions.py`](../src/perch/core/exclusions.py) — `BUILTIN_EXCLUDED_TYPES`, `is_builtin_excluded`, `parse_user_exclusions`.
- [`src/perch/core/engine.py`](../src/perch/core/engine.py) — `evaluate(...)`, `Decision` (`Ignore` / `RestoreLastSeen` / `ApplyActionDecision`), `TriggerEvent` enum.
- [`src/perch/core/resolver.py`](../src/perch/core/resolver.py) — `resolve_action(action, window, outputs, snaps, profile_outputs)` turning an `ApplyAction` into a `ResolvedPlacement` (pixel `Geometry`, concrete `OutputName`, `DesktopIndex`, plus `unmaximize_first` flag). Geometry presets expand against the target monitor's work area; absolute pixels offset from its top-left and clamp inside it.
- [`src/perch/core/identity.py`](../src/perch/core/identity.py) — `compute_identity(window)` returning the base `app:<app_id>` key (with `app:<wm_class>` fallback). Extra identity segments (title / role / pid pins) are v1.x.
- [`src/perch/core/reducer.py`](../src/perch/core/reducer.py) — the event reducer that subscribes to backend signals, runs the engine + resolver, executes decisions via the backend, and records geometry changes to `state.json`. Implements the docs/02 §Write cadence debounce and the §Feedback-loop prevention echo-drop described above.
