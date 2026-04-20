"""Perch M2.5 KWin IPC spike — the measurement harness.

Runs the following probes against a live KWin session:

  * latency: N (default 10 000) round-trips through PollCommand → CommandDone;
    records per-op monotonic latency; prints p50/p95/p99/max.
  * cycle:   unload the script, re-load it, verify the poll chain re-arms.
  * idle:    D-minute idle soak (default 60 min), sample Python + KWin RSS.

Results land in ``SPIKE_RESULTS.md`` as a copy-pasteable table; the harness
prints them to stdout too so you can tee them or re-run individual probes.

Usage (run from the repo root, inside a live Plasma 6 Wayland session)::

    python3 -m experiments.kwin_ipc_spike.harness --probe latency --count 10000
    python3 -m experiments.kwin_ipc_spike.harness --probe cycle
    python3 -m experiments.kwin_ipc_spike.harness --probe idle --minutes 60
    python3 -m experiments.kwin_ipc_spike.harness --probe all

The harness installs the KPackage script into
``$XDG_DATA_HOME/kwin/scripts/org.milnet01.perch.spike/`` on first run and
uninstalls it on clean exit. If you SIGKILL the harness, unload the script
manually via ``kpackagetool6 -t KWin/Script -r org.milnet01.perch.spike``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import resource
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

from sdbus import (  # type: ignore[import-untyped]
    DbusInterfaceCommonAsync,
    dbus_method_async,
    sd_bus_open_user,
    set_default_bus,
)

from experiments.kwin_ipc_spike.host import (
    PerchSpikeKWin1,
    start_host,
)

log = logging.getLogger("perch.spike.harness")

SPIKE_DIR = Path(__file__).resolve().parent
SCRIPT_SRC = SPIKE_DIR / "script"
SCRIPT_MAIN = SCRIPT_SRC / "contents" / "code" / "main.js"
PLUGIN_ID = "org.milnet01.perch.spike"


class KWinScripting(  # type: ignore[misc]
    DbusInterfaceCommonAsync,
    interface_name="org.kde.kwin.Scripting",
):
    """Client proxy for ``org.kde.KWin``'s ``/Scripting`` object.

    KWin exposes lowerCamelCase method names on this interface (``loadScript``,
    ``unloadScript``, …). sdbus-python defaults to converting Python function
    names via ``snake_case_to_camel_case`` which uppercases the first letter —
    hence every method below pins ``method_name=`` explicitly.
    """

    @dbus_method_async(input_signature="ss", result_signature="i", method_name="loadScript")
    async def load_script(self, file_path: str, plugin_id: str) -> int: ...

    @dbus_method_async(input_signature="s", result_signature="b", method_name="unloadScript")
    async def unload_script(self, plugin_id: str) -> bool: ...

    @dbus_method_async(input_signature="s", result_signature="b", method_name="isScriptLoaded")
    async def is_script_loaded(self, plugin_id: str) -> bool: ...

    @dbus_method_async(input_signature="", result_signature="", method_name="start")
    async def start(self) -> None: ...


class KWinScript(  # type: ignore[misc]
    DbusInterfaceCommonAsync,
    interface_name="org.kde.kwin.Script",
):
    """Per-script object at ``/Scripting/Script${id}``."""

    @dbus_method_async(input_signature="", result_signature="", method_name="run")
    async def run(self) -> None: ...

    @dbus_method_async(input_signature="", result_signature="", method_name="stop")
    async def stop(self) -> None: ...


def install_script() -> Path:
    """Copy the KPackage into ``$XDG_DATA_HOME/kwin/scripts/<plugin>/``.

    KWin on Wayland runs on the host and reads scripts out of the standard
    KPackage locations; a dev path under the repo is not resolvable for it,
    so we mirror the tree into the user data dir. Idempotent.
    """
    xdg_data = Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))
    target = xdg_data / "kwin" / "scripts" / PLUGIN_ID
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    shutil.copy2(SCRIPT_SRC / "metadata.json", target / "metadata.json")
    code_dir = target / "contents" / "code"
    code_dir.mkdir(parents=True)
    shutil.copy2(SCRIPT_MAIN, code_dir / "main.js")
    log.info("installed spike script: %s", target)
    return target / "contents" / "code" / "main.js"


def uninstall_script() -> None:
    xdg_data = Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))
    target = xdg_data / "kwin" / "scripts" / PLUGIN_ID
    if target.exists():
        shutil.rmtree(target)
        log.info("removed spike script: %s", target)


async def load_kwin_script(main_js: Path) -> int:
    scripting = KWinScripting.new_proxy("org.kde.KWin", "/Scripting")
    script_id = await scripting.load_script(str(main_js), PLUGIN_ID)
    if script_id < 0:
        raise RuntimeError(f"KWin refused loadScript; returned {script_id}")
    per_script = KWinScript.new_proxy("org.kde.KWin", f"/Scripting/Script{script_id}")
    await per_script.run()
    log.info("loadScript returned id=%d; run() ok", script_id)
    return script_id


async def unload_kwin_script() -> None:
    scripting = KWinScripting.new_proxy("org.kde.KWin", "/Scripting")
    ok = await scripting.unload_script(PLUGIN_ID)
    log.info("unloadScript returned %s", ok)


def rss_mib(pid: int) -> float:
    """Read RSS from /proc/<pid>/status in MiB. Returns NaN if unavailable."""
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                kib = int(line.split()[1])
                return kib / 1024.0
    except (OSError, ValueError):
        pass
    return float("nan")


def self_rss_mib() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def kwin_pid() -> int | None:
    try:
        result = subprocess.run(
            ["pidof", "kwin_wayland", "kwin_x11", "kwin"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        return int(result.stdout.split()[0])
    except ValueError:
        return None


# ──────────────────────── probes ────────────────────────


async def probe_latency(iface: PerchSpikeKWin1, count: int) -> dict[str, float]:
    """Fire N echoes back-to-back; collect round-trip latencies."""
    log.info("latency probe: %d round-trips", count)
    iface.counters.latencies_ns.clear()
    t0 = time.monotonic()
    for i in range(count):
        reply = await iface.echo(f"ping-{i}", timeout=10.0)
        if reply != f"ping-{i}":
            raise RuntimeError(f"echo mismatch at i={i}: got {reply!r}")
    elapsed = time.monotonic() - t0
    lat_us = [ns / 1000.0 for ns in iface.counters.latencies_ns]
    stats = {
        "count": float(count),
        "elapsed_s": elapsed,
        "throughput_hz": count / elapsed if elapsed else float("inf"),
        "p50_us": statistics.median(lat_us),
        "p95_us": _percentile(lat_us, 0.95),
        "p99_us": _percentile(lat_us, 0.99),
        "max_us": max(lat_us),
        "pending_replies_end": float(iface.pending_replies()),
    }
    return stats


def _percentile(xs: list[float], q: float) -> float:
    if not xs:
        return float("nan")
    xs = sorted(xs)
    k = min(len(xs) - 1, int(len(xs) * q))
    return xs[k]


async def probe_cycle(iface: PerchSpikeKWin1, main_js: Path) -> dict[str, float]:
    """Unload the script, re-load it, verify one round-trip completes.

    Exercises the failure mode where KWin drops the callback chain: Python
    must be tolerant of in-flight PollCommand calls that never CommandDone.
    """
    log.info("cycle probe: unload → load → verify")
    results: dict[str, float] = {}
    t0 = time.monotonic()
    await unload_kwin_script()
    # Flush orphan PollCommand awaiters left over from the old script instance;
    # otherwise the next echo is consumed by a dead callback chain.
    iface.invalidate_polls()
    await asyncio.sleep(0.5)
    iface.script_ready.clear()
    await load_kwin_script(main_js)
    try:
        await asyncio.wait_for(iface.script_ready.wait(), timeout=5.0)
    except TimeoutError as exc:
        raise RuntimeError("ScriptReady not observed within 5 s after re-load") from exc
    results["reload_to_ready_s"] = time.monotonic() - t0
    reply = await iface.echo("after-reload", timeout=5.0)
    if reply != "after-reload":
        raise RuntimeError(f"post-reload echo mismatch: {reply!r}")
    results["post_reload_ok"] = 1.0
    return results


async def probe_idle(
    iface: PerchSpikeKWin1, minutes: int, sample_every_s: int = 60
) -> dict[str, float]:
    """Leave the poll chain idle; sample RSS of self and KWin."""
    log.info("idle probe: %d minutes, sample every %ds", minutes, sample_every_s)
    kwin = kwin_pid()
    samples: list[tuple[float, float, float]] = []  # (t, self_rss, kwin_rss)
    t0 = time.monotonic()
    deadline = t0 + minutes * 60
    while True:
        now = time.monotonic()
        samples.append((now - t0, self_rss_mib(), rss_mib(kwin) if kwin else float("nan")))
        if now >= deadline:
            break
        await asyncio.sleep(sample_every_s)
    self_series = [s[1] for s in samples]
    kwin_series = [s[2] for s in samples if s[2] == s[2]]  # drop NaN
    return {
        "minutes": float(minutes),
        "samples": float(len(samples)),
        "ceilings_observed": float(iface.counters.poll_ceiling_returns),
        "self_rss_first_mib": self_series[0],
        "self_rss_last_mib": self_series[-1],
        "self_rss_delta_mib": self_series[-1] - self_series[0],
        "kwin_rss_first_mib": kwin_series[0] if kwin_series else float("nan"),
        "kwin_rss_last_mib": kwin_series[-1] if kwin_series else float("nan"),
        "kwin_rss_delta_mib": (
            kwin_series[-1] - kwin_series[0] if len(kwin_series) >= 2 else float("nan")
        ),
    }


# ──────────────────────── driver ────────────────────────


async def run(args: argparse.Namespace) -> int:
    set_default_bus(sd_bus_open_user())
    iface = await start_host()

    main_js = install_script()
    try:
        await load_kwin_script(main_js)
        try:
            await asyncio.wait_for(iface.script_ready.wait(), timeout=5.0)
        except TimeoutError:
            log.error("ScriptReady not received within 5 s — aborting")
            return 2

        report: dict[str, dict[str, float]] = {}
        probes = {"latency", "cycle", "idle"} if args.probe == "all" else {args.probe}

        if "latency" in probes:
            report["latency"] = await probe_latency(iface, args.count)
        if "cycle" in probes:
            report["cycle"] = await probe_cycle(iface, main_js)
        if "idle" in probes:
            report["idle"] = await probe_idle(iface, args.minutes)

        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    finally:
        try:
            await unload_kwin_script()
        except Exception as exc:
            log.warning("unloadScript during cleanup: %s", exc)
        uninstall_script()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kwin_ipc_spike", description=__doc__)
    parser.add_argument("--probe", choices=["latency", "cycle", "idle", "all"], default="latency")
    parser.add_argument("--count", type=int, default=10000, help="round-trips for latency probe")
    parser.add_argument("--minutes", type=int, default=60, help="duration for idle probe")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    if os.environ.get("XDG_SESSION_TYPE") != "wayland":
        log.warning("XDG_SESSION_TYPE=%r — spike expects a Plasma Wayland session",
                    os.environ.get("XDG_SESSION_TYPE"))

    try:
        return asyncio.run(run(args))
    except KeyboardInterrupt:
        log.warning("interrupted; script may still be loaded in KWin — clean up with "
                    "`kpackagetool6 -t KWin/Script -r %s`", PLUGIN_ID)
        return 130


if __name__ == "__main__":
    sys.exit(main())
