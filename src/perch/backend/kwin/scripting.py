"""Client proxies for ``org.kde.KWin`` — the compositor-side D-Bus surface.

KWin exports lowerCamelCase method names (``loadScript``, ``unloadScript``,
``isScriptLoaded``, …); ``sdbus-python`` derives a D-Bus method name from a
Python function name by ``snake_case_to_camel_case`` which uppercases the
first letter. Every method below pins ``method_name=`` explicitly so the
call lands on the real KWin method and not ``LoadScript`` etc.
"""

from __future__ import annotations

import logging
from pathlib import Path

from sdbus import (
    DbusInterfaceCommonAsync,
    dbus_method_async,
    dbus_property_async,
)

log = logging.getLogger("perch.backend.kwin.scripting")


KWIN_SERVICE = "org.kde.KWin"
KWIN_SCRIPTING_OBJ = "/Scripting"
KWIN_OBJECT = "/KWin"


class KWinScripting(
    DbusInterfaceCommonAsync,
    interface_name="org.kde.kwin.Scripting",
):
    """Proxy for ``/Scripting`` on ``org.kde.KWin``."""

    @dbus_method_async(
        input_signature="ss", result_signature="i", method_name="loadScript"
    )
    async def load_script(  # type: ignore[empty-body]
        self, file_path: str, plugin_id: str
    ) -> int: ...

    @dbus_method_async(
        input_signature="s", result_signature="b", method_name="unloadScript"
    )
    async def unload_script(self, plugin_id: str) -> bool:  # type: ignore[empty-body]
        ...

    @dbus_method_async(
        input_signature="s", result_signature="b", method_name="isScriptLoaded"
    )
    async def is_script_loaded(self, plugin_id: str) -> bool:  # type: ignore[empty-body]
        ...

    @dbus_method_async(input_signature="", result_signature="", method_name="start")
    async def start(self) -> None: ...


class KWinScript(
    DbusInterfaceCommonAsync,
    interface_name="org.kde.kwin.Script",
):
    """Per-script proxy for ``/Scripting/Script${id}``.

    ``load_script`` returns the integer id that names the per-script object
    path; the caller is expected to bind a :class:`KWinScript` proxy at
    ``/Scripting/Script{id}`` and call ``run()`` to actually execute the
    script's body.
    """

    @dbus_method_async(input_signature="", result_signature="", method_name="run")
    async def run(self) -> None: ...

    @dbus_method_async(input_signature="", result_signature="", method_name="stop")
    async def stop(self) -> None: ...


class KWinCore(
    DbusInterfaceCommonAsync,
    interface_name="org.kde.KWin",
):
    """Proxy for the ``/KWin`` root object.

    Used for the session-wide bits the scripting API doesn't cover:
    virtual-desktop count, current virtual desktop, and the matching
    change signals. Property accessors rely on ``sdbus``'s standard
    ``Properties`` interface, so we only declare the D-Bus methods we
    actually call.
    """

    @dbus_method_async(
        input_signature="", result_signature="i", method_name="currentDesktop"
    )
    async def current_desktop(self) -> int:  # type: ignore[empty-body]
        ...

    @dbus_property_async(property_signature="i", property_name="desktopGridSize")
    def desktop_grid_size(self) -> int:  # type: ignore[empty-body]
        ...


# ── Small orchestration helpers ────────────────────────────────────────────


async def install_and_run_script(
    scripting: KWinScripting, main_js_path: Path, plugin_id: str
) -> tuple[int, KWinScript]:
    """Load ``main_js_path`` under ``plugin_id`` and call ``run()`` on it.

    Returns the ``(script_id, per-script proxy)`` tuple so the caller can
    later stop / unload by id.
    """
    script_id = await scripting.load_script(str(main_js_path), plugin_id)
    if script_id < 0:
        raise RuntimeError(
            f"KWin refused loadScript for {plugin_id!r}; returned {script_id}"
        )
    proxy = KWinScript.new_proxy(KWIN_SERVICE, f"/Scripting/Script{script_id}")
    await proxy.run()
    log.info("loaded KWin script %s as id=%d", plugin_id, script_id)
    return script_id, proxy


async def unload_script_if_loaded(
    scripting: KWinScripting, plugin_id: str
) -> bool:
    """Best-effort unload. Returns True on success, False otherwise.

    Used both on backend shutdown and on a defensive pre-install check
    (``stop`` before ``start`` if we crashed last session).
    """
    try:
        loaded = await scripting.is_script_loaded(plugin_id)
    except Exception as exc:
        # sdbus-python raises a family of D-Bus exception types that don't
        # share a common useful base; rather than list each one we treat any
        # bus-side failure as "probably not loaded" and move on.
        log.debug("is_script_loaded(%s) raised %s", plugin_id, exc)
        return False
    if not loaded:
        return True
    try:
        return await scripting.unload_script(plugin_id)
    except Exception as exc:
        log.warning("unload_script(%s) raised %s", plugin_id, exc)
        return False


__all__ = [
    "KWIN_OBJECT",
    "KWIN_SCRIPTING_OBJ",
    "KWIN_SERVICE",
    "KWinCore",
    "KWinScript",
    "KWinScripting",
    "install_and_run_script",
    "unload_script_if_loaded",
]
