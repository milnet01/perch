"""``state.json`` persistence — last-seen geometries, active profile/layout.

Spec: ``docs/02-state-format.md`` §``state.json`` and §Atomic writes.
``StateStore`` owns the on-disk representation plus the in-memory model
that the reducer mutates. Writes are atomic (tmp → fsync → rename → fsync
dir — same recipe as ``config.toml``) and debounced: a run of cheap
geometry updates produces one disk flush, not dozens.

The debounce also fulfils the docs/02 §Write cadence promise: never more
often than every 5 s, always on clean shutdown.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from perch.backend.types import DesktopIndex, Geometry, OutputName

CURRENT_STATE_SCHEMA_VERSION = 1

log = logging.getLogger(__name__)


class StateLoadError(ValueError):
    """Raised when both ``state.json`` and ``state.json.bak`` fail to parse."""


@dataclass
class WindowRecord:
    """One remembered window, keyed by its identity string."""

    identity: str
    geometry: Geometry
    monitor: OutputName
    desktop: DesktopIndex
    last_seen: str  # ISO-8601 UTC — kept as a string so JSON round-trips stay byte-exact

    def to_json(self) -> dict[str, Any]:
        return {
            "identity": self.identity,
            "geometry": asdict(self.geometry),
            "monitor": self.monitor,
            "desktop": self.desktop,
            "last_seen": self.last_seen,
        }

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> WindowRecord:
        g = raw["geometry"]
        return cls(
            identity=raw["identity"],
            geometry=Geometry(x=g["x"], y=g["y"], w=g["w"], h=g["h"]),
            monitor=raw["monitor"],
            desktop=raw["desktop"],
            last_seen=raw["last_seen"],
        )


@dataclass
class PersistedState:
    """The on-disk document, in memory."""

    schema_version: int = CURRENT_STATE_SCHEMA_VERSION
    active_profile: str | None = None
    active_layout: str | None = None
    windows: dict[str, WindowRecord] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "active_profile": self.active_profile,
            "active_layout": self.active_layout,
            "windows": {k: v.to_json() for k, v in self.windows.items()},
        }

    @classmethod
    def from_json(cls, raw: Any) -> PersistedState:
        if not isinstance(raw, dict):
            raise StateLoadError("state.json top-level must be an object")
        version = raw.get("schema_version", 1)
        if not isinstance(version, int):
            raise StateLoadError(
                f"state.json schema_version must be an integer (got {version!r})"
            )
        if version > CURRENT_STATE_SCHEMA_VERSION:
            raise StateLoadError(
                f"state.json schema_version {version} is newer than this "
                f"Perch understands ({CURRENT_STATE_SCHEMA_VERSION})"
            )
        windows_raw = raw.get("windows", {})
        if not isinstance(windows_raw, dict):
            raise StateLoadError("state.json 'windows' must be an object")
        windows = {k: WindowRecord.from_json(v) for k, v in windows_raw.items()}
        return cls(
            schema_version=version,
            active_profile=raw.get("active_profile"),
            active_layout=raw.get("active_layout"),
            windows=windows,
        )


class StateStore:
    """Load, mutate, and atomically persist ``state.json``.

    Usage::

        store = StateStore(state_path, debounce_seconds=5.0)
        store.load()
        store.record_window(identity, geometry, monitor, desktop)
        await store.flush()    # explicit flush (shutdown)

    The reducer normally calls :meth:`mark_dirty` after a mutation; the
    store schedules a single debounced flush task that writes at most
    every ``debounce_seconds`` seconds.
    """

    DEFAULT_DEBOUNCE_SECONDS = 5.0

    def __init__(
        self,
        path: Path,
        *,
        debounce_seconds: float = DEFAULT_DEBOUNCE_SECONDS,
    ) -> None:
        self.path = path
        self.backup_path = path.with_name(path.name + ".bak")
        self.debounce_seconds = debounce_seconds
        self.state: PersistedState = PersistedState()
        self._dirty: bool = False
        self._flush_task: asyncio.Task[None] | None = None

    # ── Load ───────────────────────────────────────────────────────────────
    def load(self) -> None:
        """Read ``state.json``, falling back to ``.bak`` on parse failure.

        A missing file is normal on first run — the store stays empty and
        the next flush creates ``state.json``.
        """
        for candidate, label in (
            (self.path, "state.json"),
            (self.backup_path, "state.json.bak"),
        ):
            if not candidate.exists():
                continue
            try:
                raw = json.loads(candidate.read_text(encoding="utf-8"))
                self.state = PersistedState.from_json(raw)
                log.info("loaded %s (%d windows)", label, len(self.state.windows))
                return
            except (OSError, json.JSONDecodeError, StateLoadError) as exc:
                log.warning("%s failed to load: %s", label, exc)
        log.info("state.json missing; starting with empty state")
        self.state = PersistedState()

    # ── Mutations ──────────────────────────────────────────────────────────
    def record_window(
        self,
        identity: str,
        geometry: Geometry,
        monitor: OutputName,
        desktop: DesktopIndex,
    ) -> None:
        self.state.windows[identity] = WindowRecord(
            identity=identity,
            geometry=geometry,
            monitor=monitor,
            desktop=desktop,
            last_seen=_utc_now_iso(),
        )
        self._dirty = True

    def forget_window(self, identity: str) -> None:
        if identity in self.state.windows:
            del self.state.windows[identity]
            self._dirty = True

    def get_last_seen(self, identity: str) -> WindowRecord | None:
        return self.state.windows.get(identity)

    def set_active(
        self, *, profile: str | None, layout: str | None
    ) -> None:
        if (
            self.state.active_profile == profile
            and self.state.active_layout == layout
        ):
            return
        self.state.active_profile = profile
        self.state.active_layout = layout
        self._dirty = True

    # ── Flush ──────────────────────────────────────────────────────────────
    def is_dirty(self) -> bool:
        """Whether the in-memory state has pending changes not yet on disk."""
        return self._dirty

    def mark_dirty(self) -> None:
        """Schedule a debounced flush. Safe to call many times; flushes once."""
        self._dirty = True
        if self._flush_task is not None and not self._flush_task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop — tests and synchronous callers invoke
            # :meth:`flush` directly. Nothing to schedule.
            return
        self._flush_task = loop.create_task(self._debounced_flush())

    async def _debounced_flush(self) -> None:
        await asyncio.sleep(self.debounce_seconds)
        try:
            await self.flush()
        except Exception:
            log.exception("state.json debounced flush failed")

    async def flush(self) -> None:
        """Atomically write ``state.json`` if dirty.

        Implements the docs/02 §Atomic writes recipe: tmp → fsync →
        rename-old-to-.bak → rename-tmp-to-primary → fsync dir.
        """
        if not self._dirty:
            return
        payload = json.dumps(
            self.state.to_json(), indent=2, sort_keys=True
        )
        await asyncio.to_thread(self._write_atomically, payload)
        self._dirty = False

    def _write_atomically(self, payload: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(payload, encoding="utf-8")
        with tmp.open("rb") as fh:
            os.fsync(fh.fileno())
        if self.path.exists():
            os.replace(self.path, self.backup_path)
        os.replace(tmp, self.path)
        dir_fd = os.open(self.path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)


def _utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string, second precision."""
    return datetime.now(UTC).replace(microsecond=0).isoformat()
