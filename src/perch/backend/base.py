"""The ``WindowBackend`` abstract base class and its error taxonomy.

Every compositor backend subclasses :class:`WindowBackend`, emits events as Qt
signals, and implements the async command methods. Authoritative reference:
``docs/03-backend-interface.md``.
"""

from __future__ import annotations

from abc import abstractmethod

from PySide6.QtCore import QObject, Signal

from .types import (
    Capabilities,
    DesktopIndex,
    Geometry,
    OutputInfo,
    OutputName,
    WindowId,
    WindowInfo,
    WindowState,
)


class BackendError(Exception):
    """Base class for every backend-surface error."""


class BackendUnavailable(BackendError):
    """The backend's transport is missing entirely (no D-Bus, no socket, …)."""


class BackendDisconnected(BackendError):
    """The connection was lost after :meth:`WindowBackend.connect` succeeded."""


class BackendUnsupported(BackendError):
    """The requested operation is not supported by this backend."""


class UnknownWindow(BackendError):
    """No window with that :data:`~perch.backend.types.WindowId` is known."""


class UnknownOutput(BackendError):
    """No output with that :data:`~perch.backend.types.OutputName` is known."""


class WindowBackend(QObject):
    """Abstract base for every compositor backend.

    Signals carry the frozen dataclasses from :mod:`perch.backend.types`.
    Event ordering guarantees (``window_opened`` before the first
    ``geometry_changed``; ``window_closed`` terminal; outputs before windows
    referencing them) are the backend's responsibility — see
    ``docs/03-backend-interface.md`` §Event ordering guarantees.
    """

    # ── Window lifecycle ────────────────────────────────────────────────────
    window_opened = Signal(object)                 # WindowInfo
    window_closed = Signal(str)                    # WindowId
    window_changed = Signal(object)                # WindowInfo (title/type/state)
    geometry_changed = Signal(str, object, str, int)
    #   (WindowId, Geometry, OutputName, DesktopIndex)

    # ── Output lifecycle ────────────────────────────────────────────────────
    output_added = Signal(object)                  # OutputInfo
    output_removed = Signal(str)                   # OutputName
    output_changed = Signal(object)                # OutputInfo

    # ── Backend health ──────────────────────────────────────────────────────
    backend_connected = Signal()
    backend_disconnected = Signal(str)             # reason
    backend_error = Signal(str)                    # non-fatal warning

    # ── Hotkeys ─────────────────────────────────────────────────────────────
    hotkey_fired = Signal(str)                     # callback_id

    # ── Lifecycle ───────────────────────────────────────────────────────────
    # Named ``start`` / ``stop`` (not ``connect`` / ``disconnect``) because
    # :class:`QObject` already exposes ``connect`` / ``disconnect`` as
    # staticmethods for the signal/slot API. Overriding those with async
    # methods tripped mypy's ``--strict`` override check and would confuse
    # readers scanning for Qt idioms.
    @abstractmethod
    async def start(self) -> None:
        """Open the transport, subscribe to events, emit ``backend_connected``.

        Raises :class:`BackendUnavailable` if the transport is missing.
        """

    @abstractmethod
    async def stop(self) -> None:
        """Close the transport and emit ``backend_disconnected``."""

    @property
    @abstractmethod
    def capabilities(self) -> Capabilities:
        """What this backend can do. Stable for the life of one connection."""

    @classmethod
    def is_available(cls) -> bool:
        """Cheap probe — can this backend attempt to ``start()`` on this host?

        Default: ``True`` (the backend is always usable, e.g. ``MockBackend``).
        Real backends override to read environment variables ($SWAYSOCK,
        $HYPRLAND_INSTANCE_SIGNATURE, $XDG_CURRENT_DESKTOP, …) or check for a
        CLI binary on ``PATH``. The probe **must not do I/O** — it's called
        from :func:`perch.backend.select` and the compliance-suite parametriser,
        both of which run during module/test collection.

        Returning ``True`` does not guarantee ``start()`` will succeed; it
        only means there's a reasonable chance. ``start()`` is still expected
        to raise :class:`BackendUnavailable` on a missing transport.
        """
        return True

    # ── Queries ─────────────────────────────────────────────────────────────
    @abstractmethod
    async def list_windows(self) -> list[WindowInfo]: ...

    @abstractmethod
    async def get_window(self, wid: WindowId) -> WindowInfo:
        """Return the current snapshot. Raises :class:`UnknownWindow`."""

    async def get_active_window(self) -> WindowInfo | None:
        """Return the currently-focused user-manageable window, or ``None``.

        ``None`` means "no user-manageable window is focused" — e.g.
        focus on the desktop background, a menu, a tooltip, or no
        window at all. Backends that can't report focus at all should
        override to raise :class:`BackendUnsupported` (Sway, Hyprland
        without a running IPC, etc.); the default implementation
        raises :class:`BackendUnsupported` so compliance tests must
        opt in explicitly.
        """
        raise BackendUnsupported(
            "get_active_window: this backend does not report focus"
        )

    @abstractmethod
    async def list_outputs(self) -> list[OutputInfo]: ...

    @abstractmethod
    async def current_desktop(self) -> DesktopIndex: ...

    @abstractmethod
    async def desktop_count(self) -> int: ...

    # ── Commands ────────────────────────────────────────────────────────────
    @abstractmethod
    async def set_geometry(
        self,
        wid: WindowId,
        geom: Geometry,
        monitor: OutputName | None = None,
        desktop: DesktopIndex | None = None,
    ) -> None:
        """Apply geometry (and optionally monitor/desktop) atomically.

        Raises :class:`UnknownWindow`, :class:`UnknownOutput`, or
        :class:`BackendUnsupported` if a requested field cannot be set on
        this backend.
        """

    @abstractmethod
    async def set_state(self, wid: WindowId, state: WindowState) -> None:
        """Set the compositor's native window state.

        Raises :class:`BackendUnsupported` if the specific state (e.g.
        ``MAXIMIZED`` on Sway / Hyprland) has no compositor equivalent. The
        core's apply pipeline catches this and substitutes work-area geometry
        — see ``docs/07-rules-engine.md`` §Apply order.
        """

    @abstractmethod
    async def close_window(self, wid: WindowId) -> None:
        """Politely ask the window to close (``WM_DELETE_WINDOW`` / xdg close)."""

    # ── Hotkeys (optional) ──────────────────────────────────────────────────
    @abstractmethod
    async def register_hotkey(self, accel: str, callback_id: str) -> None: ...

    @abstractmethod
    async def unregister_hotkey(self, callback_id: str) -> None: ...
