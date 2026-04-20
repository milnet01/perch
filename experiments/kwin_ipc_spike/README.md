# Perch M2.5 — KWin IPC spike

This directory contains the measurement spike that de-risks the long-poll IPC
pattern described in [`docs/05-backend-kwin.md`](../../docs/05-backend-kwin.md)
**before** M5 (the real KWin backend) commits to it. See
[`docs/11-roadmap.md`](../../docs/11-roadmap.md) §M2.5 for the exit criteria.

Not end-user code. Not shipped in the installed `perch` package. Lives under
`experiments/` precisely so it doesn't pollute the distribution.

## Contents

| File | Role |
|---|---|
| `script/metadata.json` | KPackage metadata — KWin loads this to validate the script. |
| `script/contents/code/main.js` | 30-ish-line JS: subscribes to `workspace.windowAdded`, maintains the long-poll callback chain against Python. |
| `host.py` | sdbus-python service owning `io.github.milnet01.Perch.spike` at `/KWin`. Holds `PollCommand` replies for up to 5 s (heartbeat ceiling). |
| `harness.py` | Driver: installs the script, loads it via `org.kde.KWin.Scripting.loadScript`, runs probes, unloads, reports. |

## Prerequisites

- Plasma Wayland ≥ 6.0 (the script uses Plasma-6 `workspace.windowAdded` /
  `window*` names; Plasma 5 names are not supported).
- `python3 -m pip install --user --break-system-packages sdbus qasync PySide6`
  (same pins as `pyproject.toml`).
- You'll load a KWin script into your **current live session**. It's small and
  idempotent, but if you kill the harness with `SIGKILL` the script stays
  loaded — remove with `kpackagetool6 -t KWin/Script -r org.milnet01.perch.spike`.

## Running

From the repo root (`perch/`):

```bash
# 10 000 round-trips; prints p50 / p95 / p99 / max latency.
python3 -m experiments.kwin_ipc_spike.harness --probe latency --count 10000

# unload → re-load → verify one round-trip survives the cycle.
python3 -m experiments.kwin_ipc_spike.harness --probe cycle

# one-hour idle soak; samples RSS every 60 s.
python3 -m experiments.kwin_ipc_spike.harness --probe idle --minutes 60

# run the three probes back-to-back.
python3 -m experiments.kwin_ipc_spike.harness --probe all
```

Results print as a JSON object on stdout; transcribe the numbers into the
matching section of [`SPIKE_RESULTS.md`](SPIKE_RESULTS.md).

## What the spike is checking

Three exit criteria from `docs/11-roadmap.md` §M2.5:

1. **Long-poll round-trip median latency < 5 ms** on Plasma 6.2, 6.3, and
   `kdeneon:unstable` (proxy for current development tip).
2. **No memory growth** after 1 h of idle operation (callback chain must
   unwind correctly even when every `PollCommand` times out and returns `nop`).
3. **Clean recovery across `unloadScript`/`loadScript`** — the script re-arms
   its poll chain, Python sees `ScriptReady`, one round-trip succeeds post-reload.

If any criterion fails, document the observed failure mode in
`docs/05-backend-kwin.md` and revert to the 50 ms polling fallback (see the
roadmap "Fallback" clause). Better to know now than in M5.

## Known caveats

- The harness passes ZERO windows through `workspace.windowAdded` — that
  signal is incidental to the spike; we measure the out-of-band `PollCommand`
  chain, which is the actual IPC hot path for M5.
- A single KWin JS context holds the callback chain. Two concurrent
  harnesses will fight over the bus name (second `request_default_bus_name_async`
  fails fast).
- The `kpackagetool6` cleanup path assumes `plasma-framework-tools` is
  installed; on a bare Plasma 6, the script is removed by `harness.py` itself
  on clean exit.

## What to update after running

1. Fill in the relevant row of `SPIKE_RESULTS.md`.
2. If all exit criteria passed, flip the note in `docs/11-roadmap.md` from
   "spike pending" to "spike passed" and cross-reference the results file from
   `docs/05-backend-kwin.md` §Testing strategy.
3. If any criterion failed, open a doc PR against `docs/05-backend-kwin.md`
   documenting the failure and the fallback you're taking (per the roadmap's
   no-workarounds-without-documentation rule).
