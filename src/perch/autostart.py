"""Autostart-at-login plumbing.

Two transports, one ``sync(enabled)`` façade:

* **XDG path** (non-Flatpak). Writes or removes
  ``$XDG_CONFIG_HOME/autostart/io.github.milnet01.Perch.desktop``. This is
  the freedesktop autostart spec — every session manager picks it up.
* **Portal path** (Flatpak). Calls
  ``org.freedesktop.portal.Background.RequestBackground`` with
  ``autostart=True``. Portal shows the user a permission prompt on first
  use; subsequent ``sync`` calls flip the flag without re-prompting.

Which transport we pick is determined by :func:`is_flatpak` — the
Flatpak sandbox mounts a well-known marker at ``/.flatpak-info``. That
probe is the canonical detection pattern used by GNOME, KDE, and every
portal-aware application.

``sync(enabled)`` is idempotent. Calling it with ``True`` on a system
where autostart is already enabled is a no-op; likewise ``False`` with
no autostart entry present.

The Qt config-dialog ``saved`` signal calls :func:`sync_from_config` so
toggling the ``Start Perch at login`` checkbox takes effect
immediately. :mod:`perch.app` calls it once at startup to reconcile any
drift (e.g. the user manually edited their autostart folder).
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import portal
from .config import Config
from .paths import is_flatpak as _is_flatpak
from .paths import xdg_base

log = logging.getLogger(__name__)


#: Stable basename for the autostart desktop file. Must match the install
#: ``Name`` so session managers can correlate Perch's autostart entry with
#: its running instance.
AUTOSTART_BASENAME = "io.github.milnet01.Perch.desktop"


def is_flatpak() -> bool:
    """Return True when Perch is running inside a Flatpak sandbox.

    Re-exported from :func:`perch.paths.is_flatpak`, which owns the probe.
    """
    return _is_flatpak()


def autostart_dir() -> Path:
    """``$XDG_CONFIG_HOME/autostart``, following the same XDG fallback rules
    as :func:`perch.paths.config_dir`.
    """
    return xdg_base("XDG_CONFIG_HOME", ".config") / "autostart"


def autostart_file() -> Path:
    """Absolute path to Perch's autostart entry (may or may not exist)."""
    return autostart_dir() / AUTOSTART_BASENAME


# ── XDG transport ────────────────────────────────────────────────────────────


_XDG_DESKTOP_TEMPLATE = """\
[Desktop Entry]
Type=Application
Name=Perch
GenericName=Window Geometry Manager
Comment=Remember where your windows belong
Icon=io.github.milnet01.Perch
Exec=perch
Terminal=false
Categories=Utility;
X-GNOME-Autostart-enabled=true
"""


def xdg_is_enabled() -> bool:
    """Return True when a non-hidden autostart entry is installed."""
    path = autostart_file()
    if not path.is_file():
        return False
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    # Freedesktop §Hidden: "Hidden=true" overrides everything else and
    # tells the session manager to pretend the file doesn't exist.
    return all(
        line.strip().lower() != "hidden=true" for line in content.splitlines()
    )


def xdg_enable() -> None:
    """Write the autostart entry (idempotent)."""
    path = autostart_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic write via temp-and-rename — a half-written autostart file
    # would confuse the session manager on next login.
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(_XDG_DESKTOP_TEMPLATE, encoding="utf-8")
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)
    log.info("autostart enabled (XDG): %s", path)


def xdg_disable() -> None:
    """Remove the autostart entry (idempotent — missing file is fine)."""
    path = autostart_file()
    try:
        path.unlink()
    except FileNotFoundError:
        return
    log.info("autostart disabled (XDG): %s removed", path)


# ── Portal transport ─────────────────────────────────────────────────────────


#: Type of the ``sdbus.DbusInterfaceCommonAsync`` subclass we pass around.
#: Kept as ``Any`` because the import is lazy — on a test box without an
#: sdbus build we still want :func:`sync` to import without exploding.
PortalFactory = Callable[[], Any]

#: Portal root object path — every portal interface lives on the same object.
PORTAL_OBJECT = "/org/freedesktop/portal/desktop"

#: Success code of an ``org.freedesktop.portal.Request`` response.
PORTAL_RESPONSE_SUCCESS = 0

#: How long to wait for the Request's ``Response`` signal. The portal shows
#: a permission dialog on the first call per install and the response only
#: arrives once the user has answered, so this is deliberately generous —
#: the call runs as a background task and blocks nothing.
PORTAL_RESPONSE_TIMEOUT_S = 300.0


async def portal_set_autostart(
    enabled: bool,
    *,
    factory: PortalFactory | None = None,
    subscriber: portal.Subscriber | None = None,
    sender: portal.SenderName | None = None,
    timeout_s: float = PORTAL_RESPONSE_TIMEOUT_S,
) -> bool:
    """Ask the Background portal to enable/disable autostart for this app.

    Returns True when the portal reports autostart as granted, and False
    for every other outcome — a refusal, a timeout, or no portal at all.

    ``RequestBackground`` does not return the result. It returns the object
    path of an ``org.freedesktop.portal.Request``, and the outcome arrives
    later as that request's ``Response`` signal, carrying
    ``(uint32 response, a{sv} results)``, and it can arrive before the call
    returns. :func:`perch.portal.call_with_response` subscribes first; the
    KWin hotkey provider uses the same helper.

    ``factory``, ``subscriber`` and ``sender`` are injection seams for
    tests. Production callers leave them as ``None``.

    Note: on the first call per Flatpak install, the portal shows a
    permission prompt. Subsequent calls flip the flag silently. If the
    user denies the prompt, the response carries ``autostart=False`` and
    the portal won't autostart us; we log at WARNING and treat that as
    "user said no" rather than as an error.
    """
    proxy = (factory or _build_portal_proxy)()
    options: dict[str, Any] = {
        "autostart": ("b", enabled),
        "reason": ("s", "Perch keeps window geometry in sync across sessions."),
    }
    if enabled:
        # Exec line the portal hands to the session manager. ``perch`` is
        # on $PATH inside the sandbox courtesy of the wheel's entry point.
        options["commandline"] = ("as", ["perch"])
    def invoke(token: str) -> Any:
        return proxy.request_background(
            "", {**options, "handle_token": ("s", token)}
        )

    try:
        response = await portal.call_with_response(
            invoke, timeout_s=timeout_s, subscriber=subscriber, sender=sender
        )
    except Exception as exc:
        log.warning("portal RequestBackground failed: %s", exc)
        return False
    if response is None:
        log.warning(
            "portal RequestBackground: no Response within %.0fs", timeout_s
        )
        return False
    status, results = response
    if status != PORTAL_RESPONSE_SUCCESS:
        log.warning("portal RequestBackground refused (response=%s)", status)
        return False
    granted = bool(_unwrap_variant(results.get("autostart", False)))
    log.info(
        "portal RequestBackground: autostart requested=%s granted=%s",
        enabled,
        granted,
    )
    return granted


def _unwrap_variant(value: Any) -> Any:
    """Unwrap an sdbus variant tuple ``(signature, value)`` to its value."""
    if isinstance(value, tuple) and len(value) == 2 and isinstance(value[0], str):
        return value[1]
    return value


def _build_portal_proxy() -> Any:
    """Construct the real sdbus proxy. Split out so tests don't import sdbus."""
    from sdbus import (
        DbusInterfaceCommonAsync,
        dbus_method_async,
    )

    class BackgroundPortalProxy(
        DbusInterfaceCommonAsync,
        interface_name="org.freedesktop.portal.Background",
    ):
        """Minimal proxy for the Background portal's ``RequestBackground``.

        We only wire the one method; the portal exposes more (NotifyBackground,
        SetStatus) but Perch doesn't need them for autostart toggling.
        """

        @dbus_method_async(
            input_signature="sa{sv}",
            result_signature="o",
            method_name="RequestBackground",
        )
        async def request_background(  # type: ignore[empty-body]
            self, parent_window: str, options: dict[str, Any]
        ) -> str: ...

    return BackgroundPortalProxy.new_proxy(portal.PORTAL_SERVICE, PORTAL_OBJECT)


# ── Façade ──────────────────────────────────────────────────────────────────


def sync(
    enabled: bool,
    *,
    flatpak: bool | None = None,
    portal_factory: PortalFactory | None = None,
    portal_subscriber: portal.Subscriber | None = None,
    portal_sender: portal.SenderName | None = None,
) -> None:
    """Reconcile the system's autostart state with ``enabled``.

    Synchronous for the XDG path (the normal case). For the portal path,
    schedules the async portal call on the running loop if one exists;
    otherwise runs it to completion via :func:`asyncio.run`.

    ``flatpak`` and the ``portal_*`` arguments are injection seams for tests.
    """
    in_flatpak = is_flatpak() if flatpak is None else flatpak
    if in_flatpak:
        _run_portal_call(
            portal_set_autostart(
                enabled,
                factory=portal_factory,
                subscriber=portal_subscriber,
                sender=portal_sender,
            )
        )
        return
    if enabled:
        xdg_enable()
    else:
        xdg_disable()


def _run_portal_call(coro: Any) -> None:
    """Schedule a portal coroutine, picking sync-or-async based on the loop.

    Config save runs from a Qt slot, which under qasync means a loop is
    already spinning — we schedule the call as a background task so the
    dialog's OK button doesn't stall on the portal's permission prompt.
    Called at startup (before the loop runs) we fall back to a
    short-lived :func:`asyncio.run`.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(coro)
        return
    task: asyncio.Task[bool] = loop.create_task(coro)
    # The set pattern mirrors :mod:`perch.app` — holds a strong ref so
    # the GC doesn't reclaim the task mid-flight.
    _portal_tasks.add(task)
    task.add_done_callback(_portal_tasks.discard)


_portal_tasks: set[asyncio.Task[bool]] = set()


def sync_from_config(config: Config) -> None:
    """Read the ``[general] start_at_login`` value and reconcile.

    Called from :mod:`perch.app` at startup and from the config dialog's
    ``saved`` signal. Kept as a separate function so tests can drive it
    without constructing the full app state.
    """
    sync(config.general.start_at_login)


__all__ = [
    "AUTOSTART_BASENAME",
    "autostart_dir",
    "autostart_file",
    "is_flatpak",
    "portal_set_autostart",
    "sync",
    "sync_from_config",
    "xdg_disable",
    "xdg_enable",
    "xdg_is_enabled",
]
