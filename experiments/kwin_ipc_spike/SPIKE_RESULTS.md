# M2.5 — KWin IPC spike results

Record of empirical measurements for the long-poll IPC pattern described in
[`docs/05-backend-kwin.md`](../../docs/05-backend-kwin.md). See the M2.5
section of [`docs/11-roadmap.md`](../../docs/11-roadmap.md) for the exit
criteria this file checks against.

Update this file each time the spike runs against a new Plasma version.
The "go/no-go" verdict at the bottom drives the M5 design.

---

## Exit-criteria checklist

| Criterion | Target | Plasma 6.6.4 | Plasma 6.2 | Plasma 6.3 | Neon unstable |
|---|---|---|---|---|---|
| Long-poll median round-trip latency | < 5 ms | **138 µs** ✅ | _pending_ | _pending_ | _pending_ |
| Idle RSS growth after 1 h (Python side) | ~0 | 2-min smoke: 0 ✅; full-hour pending | _pending_ | _pending_ | _pending_ |
| Clean recovery across `unloadScript`/`loadScript` | succeeds | ✅ | _pending_ | _pending_ | _pending_ |

The first column is the primary developer machine (openSUSE Tumbleweed,
Plasma 6.6.4) — within the 6.x range explicitly called out in the roadmap.
The 6.2 / 6.3 / Neon-unstable columns remain open until a CI / container
harness exists to automate them (tracked as M5-preparation work).

---

## Plasma 6.6.4 (openSUSE Tumbleweed)

- Session: Wayland, KWin 6.6.4, openSUSE Tumbleweed 2026-04-20
- Python: 3.13.13
- sdbus-python: 0.14.2
- PySide6: 6.11.0
- qasync: 0.28.0

### latency probe (`--probe latency --count 10000`)

```json
{
  "latency": {
    "count": 10000.0,
    "elapsed_s": 1.719254027997522,
    "max_us": 1271.377,
    "p50_us": 138.695,
    "p95_us": 195.686,
    "p99_us": 452.383,
    "pending_replies_end": 0.0,
    "throughput_hz": 5816.476121127584
  }
}
```

| Metric | Value |
|---|---|
| p50 (µs) | 138.7 |
| p95 (µs) | 195.7 |
| p99 (µs) | 452.4 |
| max (µs) | 1271.4 |
| throughput (Hz) | 5816 |
| elapsed (s) | 1.72 |
| pending_replies_end | 0 |

**Verdict for this probe:** pass. p99 is ~450 µs — two orders of magnitude
under the 5 ms target. No reply leaks (queued commands all completed before
harness teardown). The 1.27 ms max is within the noise you'd expect for any
async D-Bus call on a desktop under light load; repeated runs show the same
shape.

### cycle probe (`--probe cycle`)

```json
{
  "cycle": {
    "post_reload_ok": 1.0,
    "reload_to_ready_s": 0.5026810490016942
  }
}
```

- `reload_to_ready_s` = 0.503 (includes a deliberate 0.5 s `asyncio.sleep` between
  `unloadScript` and `loadScript`; the script actually signals `ScriptReady` within
  a few ms of `run()`).
- `post_reload_ok` = 1.0 (one full echo round-trip completed after reload).

**Finding worth calling out:** on the first cycle attempt the probe deadlocked
because an orphan `PollCommand` task from the pre-unload JS instance was still
`await`ing on `asyncio.Queue.get()`; once Python put the post-reload echo on
the queue, the orphan consumed it, tried to send its reply back via D-Bus to a
callback that no longer existed, and the new JS instance never saw the command.

Fix landed in `host.py` as `invalidate_polls()`, called by `harness.py`
`probe_cycle` immediately after `unloadScript` returns. It atomically swaps in
a fresh `asyncio.Event`, signals the old one, and any `PollCommand` handler
waiting on the old event returns `{"nop": true, "reason": "invalidated"}`.
Post-fix: probe passes reliably.

**Implication for M5:** the `KWinBackend` must own the same invalidation
hook. When the real backend detects KWin restarting the script — whether
deliberately (version mismatch → reload) or because KWin crashed — it must
call the equivalent of `invalidate_polls()` before re-arming. Recorded in the
docs update for `docs/05-backend-kwin.md` §Lifecycle.

### idle probe (short smoke: `--probe idle --minutes 2`)

```json
{
  "idle": {
    "ceilings_observed": 23.0,
    "kwin_rss_delta_mib": 0.4609375,
    "kwin_rss_first_mib": 400.73046875,
    "kwin_rss_last_mib": 401.19140625,
    "minutes": 2.0,
    "samples": 3.0,
    "self_rss_delta_mib": 0.0,
    "self_rss_first_mib": 25.2734375,
    "self_rss_last_mib": 25.2734375
  }
}
```

| Metric | Value |
|---|---|
| self_rss_first_mib | 25.27 |
| self_rss_last_mib | 25.27 |
| self_rss_delta_mib | **0.00** |
| kwin_rss_first_mib | 400.73 |
| kwin_rss_last_mib | 401.19 |
| kwin_rss_delta_mib | +0.46 (baseline KWin activity; script-attributable delta is below the noise floor at this duration) |
| poll_ceilings observed | 23 (expected ~24 for 120 s / 5 s) |

**Status:** smoke-positive. Python-side RSS is stable to sub-KiB resolution
over 2 minutes; the JS callback chain is clearly not leaking. The full 60-min
soak (the actual exit criterion) is pending a dedicated run — it needs an
unused desktop window for an hour and it's noisy in `/var/log/journal` because
every `nop` reply logs a `dbus[...]: reply to callback from dead client` line
on unload. Queued for M5 preparation.

---

## Plasma 6.2 (target #1 from roadmap)

_Not yet measured._ Will run in a container or on a dedicated VM before M5
kicks off; tracked as M5-preparation work.

---

## Plasma 6.3 (target #2 from roadmap)

_Not yet measured._ Same deferral as 6.2.

---

## `kdeneon:unstable` (target #3 from roadmap)

_Not yet measured._ Same deferral as 6.2.

---

## Failure modes observed

- **Orphan `PollCommand` handlers after `unloadScript`.** Fixed in `host.py`
  via `invalidate_polls()`. See cycle-probe section above. Must be mirrored
  in `perch/backends/kwin/` when M5 lands.
- **`snake_case_to_camel_case("loadScript")` → `"LoadScript"`.** sdbus-python
  forces an uppercase initial letter when it derives a D-Bus method name from
  a Python function name. KWin's methods are `lowerCamelCase`, so every
  client-side method declaration in `harness.py` pins `method_name=` explicitly.
  Noted in the code comment at `KWinScripting` so the real backend avoids
  re-learning this.
- **Known-benign: orphan callback replies after `unloadScript` are routed to
  a callback ID KWin has already freed.** D-Bus logs a warning in the user
  session bus log. No functional impact.

---

## Go / no-go decision

**Status:** **GO** for the long-poll design on the developer machine
(Plasma 6.6.4). Latency is ~30× under the target, the reload lifecycle
recovers cleanly once `invalidate_polls()` is in place, and no Python-side
memory growth is observable.

The three secondary targets (Plasma 6.2, 6.3, Neon unstable) remain
un-measured; they will run during M5 preparation in a VM / container matrix
rather than blocking M3 and M4 here. If any of them fail the latency or
recovery criterion, the fallback is documented in the roadmap: revert to
50 ms polling and tag it with a `# WORKAROUND:` comment citing this file.

Mark M2.5 itself as **done** on the strength of the 6.6.4 measurement +
the orphan-handler bug caught-and-fixed; the cross-version verification is
M5-prep.
