"""StatusNotifierHost availability probe.

The probe is the one documented in ``docs/08-ui.md`` §Tray on GNOME Wayland.
It is *synchronous on purpose* — it runs during CLI startup before qasync
spins the event loop, and the answer decides whether Perch instantiates a
tray icon at all. sdbus-python's ``sdbus_block`` namespace gives us sync
D-Bus without dragging the qasync loop into startup.

Canonical probe (verified April 2026, Plasma 6 + GNOME 48 AppIndicator):

1. The session bus has an owner for ``org.kde.StatusNotifierWatcher``. The
   freedesktop.org rename to ``org.freedesktop.StatusNotifierWatcher``
   proposed in the spec never shipped — every real host still registers
   under ``org.kde``.
2. The ``IsStatusNotifierHostRegistered`` property on
   ``/StatusNotifierWatcher`` returns ``True``. A watcher without a host
   is a deprecated/stale state and must be treated as "no tray".

Any D-Bus-level failure (bus unreachable, unknown property, timeout) is
treated as "no host" — Perch would rather fail-closed and skip the tray
than raise during startup.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable

log = logging.getLogger(__name__)

WATCHER_BUS_NAME = "org.kde.StatusNotifierWatcher"
WATCHER_OBJECT_PATH = "/StatusNotifierWatcher"
WATCHER_INTERFACE = "org.kde.StatusNotifierWatcher"


def _sdbus_probe() -> bool:
    """The real probe — talks to the session bus via sdbus-python.

    The session bus is opened explicitly rather than left to sdbus's
    default. Inside a Flatpak the default open fails outright
    (``sd_bus_open`` returns ENOENT), the probe is classified as a
    transport failure, and Perch reports "no host" on a session that has
    one — ``DBUS_SESSION_BUS_ADDRESS`` points at ``/run/flatpak/bus``,
    which only the explicit user-bus open honours.
    """
    from sdbus import DbusInterfaceCommon, dbus_property, sd_bus_open_user
    from sdbus_block.dbus_daemon import FreedesktopDbus

    class _SNIWatcher(
        DbusInterfaceCommon,
        interface_name=WATCHER_INTERFACE,
    ):
        # ``@dbus_property`` replaces the method body with a real D-Bus
        # getter at class-construction time; the Python body is never
        # executed. Returning a literal here instead of ``...`` keeps
        # mypy --strict happy without suppression.
        @dbus_property("b")
        def is_status_notifier_host_registered(self) -> bool:
            return False

    bus = sd_bus_open_user()
    if not FreedesktopDbus(bus=bus).name_has_owner(WATCHER_BUS_NAME):
        log.debug("sni_probe: %s not owned", WATCHER_BUS_NAME)
        return False
    watcher = _SNIWatcher(WATCHER_BUS_NAME, WATCHER_OBJECT_PATH, bus=bus)
    registered = bool(watcher.is_status_notifier_host_registered)
    log.debug(
        "sni_probe: watcher owned, IsStatusNotifierHostRegistered=%s",
        registered,
    )
    return registered


def sni_host_available(probe: Callable[[], bool] = _sdbus_probe) -> bool:
    """Return True iff a StatusNotifierHost is registered on the session bus.

    Never raises; a failure to talk to the bus is reported as "no host"
    plus a DEBUG log line. The ``probe`` argument is a seam for tests —
    callers in production never pass it.
    """
    try:
        return probe()
    except ImportError as exc:  # pragma: no cover - sdbus is a hard install dep
        log.debug("sni_probe: sdbus import failed: %s", exc)
        return False
    except Exception as exc:  # any D-Bus transport failure → no host
        # Broad except is deliberate: the sdbus exception hierarchy can
        # surface DbusUnknownPropertyError, DbusNoReplyError, or plain
        # transport failures. We classify every one as "probe negative"
        # rather than crash startup.
        log.debug("sni_probe: probe failed (%s: %s)", type(exc).__name__, exc)
        return False


def is_gnome_wayland() -> bool:
    """Detect whether the current session is GNOME on Wayland.

    Used to gate the "install the AppIndicator extension" first-run dialog
    to the one environment where it is actionable. Every other desktop
    either ships a tray host by default (KDE, Xfce, LXQt, Cinnamon, MATE)
    or has no standard extension story (tiling WMs). A negative probe
    elsewhere just logs a warning.
    """
    current = os.environ.get("XDG_CURRENT_DESKTOP", "")
    session = os.environ.get("XDG_SESSION_TYPE", "")
    return "GNOME" in current.split(":") and session == "wayland"
