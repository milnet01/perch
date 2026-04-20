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
- `APPLY_GEOMETRY(geom)` — apply a specific geometry now.
- `APPLY_LAYOUT(name)` — apply the named layout's entry that matches this window (if any).

The engine never emits more than one decision per window per event. Chaining ("apply layout X *then* move to monitor 2") is expressed inside a single layout or rule, not by stacking decisions.

## Evaluation order

Top to bottom, first match wins. The order is:

1. **Built-in exclusion: override-redirect windows, known system popups.** Emits `IGNORE`. Not configurable.
2. **User exclusions** (`[exclusions]` in config). Emits `IGNORE`.
3. **User rules** (`[[rules]]`, in config order). First match wins — `APPLY_GEOMETRY` or `APPLY_LAYOUT`.
4. **Active layout**, if one is set and has an entry matching this window. `APPLY_LAYOUT(current)`.
5. **Last-seen geometry** from `state.json`, if `general.restore_on_open = true` and we have an entry. Emits `RESTORE_LAST_SEEN`.
6. **Do nothing.**

This ordering is deliberate:

- Exclusions always win so a user can always say "never touch this."
- Rules beat layouts because rules are more explicit user intent ("*always* X").
- Layouts beat last-seen because activating a layout is a current, explicit user action.
- Last-seen is the fallback for the many windows that have no rule or layout entry.

## Matching

A rule's `match` is an AND over its specified fields. The field semantics are defined in [02-state-format.md](02-state-format.md). Key points:

- Unspecified fields are wildcards. `match = { app_id = "firefox" }` matches every Firefox window.
- `title` supports regex; all others are glob (`*`, `?`, `[abc]`). Regexes are Python `re.search` — anchor them if you want a full match.
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

1. Named preset (`"left-half"`, `"top-right-quarter"`, `"maximize"`, `"center"`, or a user-defined preset) → fixed `x%/y%/w%/h%` relative to the target monitor's work area.
2. Percent values → multiplied by the target monitor's work area and rounded to ints.
3. Absolute pixel values → used as-is, clamped to the target monitor's work area (a rule cannot push a window off-screen).
4. `monitor = "primary"` | `"current"` | an integer index → resolved against the active profile's output list.
5. `monitor` as an output name (`"DP-1"`) → resolved directly; if that output is currently disconnected, the rule is skipped (not reassigned to primary — that would silently do the wrong thing).

## Reactive evaluation

The engine is reactive:

- Evaluated on `window_opened`, always.
- Evaluated on `window_changed` only for fields that can affect matching: `title`, `type`, `state`. Not on geometry changes (that would create a feedback loop every time Perch moves a window).
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

Window events are rare (dozens per minute at most during heavy use). Matching is a linear scan through the rules list. No indexing, no RETE, no compiled matchers — for v1 this is fine. If a user with a 500-rule config ever materialises, we revisit then.

## Debugging and observability

- Every rule evaluation logs at `DEBUG` with `(window_identity, chosen_rule, decision)`.
- The dialog's "Rules trace" panel shows the last N evaluations live.
- `perch --test-rules <path-to-config.toml>` (post-M4) will be a CLI mode that replays a saved event stream against a config for regression testing.

## Validation

The config loader rejects a rule with:

- A `match` block that is entirely empty (would match every window — users almost never want that; use an explicit `catch_all = true` field if you really do).
- An `apply` block missing both `geometry` and `snap` (no effect).
- A `monitor` referring to an output index higher than the current profile declares.
- A `snap` name not in the built-in set or the user's `[snaps]` table.

Validation errors are shown in the config dialog's problem inspector; Perch does not silently drop bad rules.
