"""The event reducer — glues backend events, the rules engine, live state,
and ``state.json`` persistence together.

Architecturally this is the *only* module with an opinion on execution
order: everything below it (engine, resolver, state store) is pure; the
reducer turns events into backend calls and mutates the persistent state.

Flow on a ``window_opened`` event::

    info → identity → evaluate(engine) → resolve(action) → backend.set_...
                                                         → state_store.record_window
                                                         → mark_dirty (debounced flush)

Feedback-loop prevention follows ``docs/07-rules-engine.md``
§Feedback-loop prevention: after every ``set_geometry`` call the reducer
records the geometry it *expects* to see echoed back, and the matching
``geometry_changed`` event is dropped so Perch never fights itself.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from perch.backend.base import (
    BackendUnsupported,
    UnknownOutput,
    UnknownWindow,
    WindowBackend,
)
from perch.backend.types import (
    DesktopIndex,
    Geometry,
    OutputInfo,
    OutputName,
    WindowId,
    WindowInfo,
    WindowState,
)
from perch.config.schema import Config

from .actions import ApplyAction
from .engine import (
    ApplyActionDecision,
    Decision,
    Ignore,
    RestoreLastSeen,
    TriggerEvent,
    evaluate,
)
from .exclusions import is_builtin_excluded, is_user_excluded
from .identity import UNKNOWN_IDENTITY, compute_identity
from .layouts import Layout
from .profiles import (
    Profile,
    compute_topology_key,
    profile_output_names,
    select_profile,
)
from .resolver import ResolveError, resolve_action
from .state_store import StateStore

log = logging.getLogger(__name__)

TOPOLOGY_DEBOUNCE_SECONDS = 0.3


class Reducer:
    """Event-driven glue between backend + engine + state.

    Public handler methods (``handle_*``) are directly callable; tests
    drive the reducer synchronously. In the live app, :meth:`bind_signals`
    wires the same handlers to the backend's Qt signals via
    ``qasync.asyncSlot``.
    """

    def __init__(
        self,
        backend: WindowBackend,
        config: Config,
        state_store: StateStore,
        *,
        topology_debounce_seconds: float = TOPOLOGY_DEBOUNCE_SECONDS,
    ) -> None:
        self.backend = backend
        self.config = config
        self.state_store = state_store
        self.topology_debounce_seconds = topology_debounce_seconds

        self.active_profile: Profile | None = None
        self.active_layout: Layout | None = None
        # Active layout with the current profile's ``[[profiles.override]]``
        # entries applied. Recomputed whenever either input changes; the
        # engine consults this, not ``active_layout``.
        self._effective_layout: Layout | None = None
        self.current_desktop: DesktopIndex = 0
        self._outputs: dict[OutputName, OutputInfo] = {}
        self._topology_key: str = ""

        # When True, ``_execute`` drops EVERY placement decision — rule
        # matches, layout-entry placement, and last-seen restore — so no
        # window is moved automatically. This is the "Pause Perch" panic
        # toggle, exposed via the tray's middle-click + menu item. Manual
        # snap bypasses the reducer and is unaffected. See docs/08-ui.md
        # §Menu structure.
        self.paused: bool = False

        # The reducer caches the most recent :class:`WindowInfo` per window so
        # ``geometry_changed`` (which carries only wid/geom/monitor/desktop)
        # can still compute an identity for the state.json write.
        self._windows: dict[WindowId, WindowInfo] = {}

        # Feedback-loop guard: the next ``geometry_changed`` matching this
        # value is dropped.
        self._expected_geometry: dict[WindowId, Geometry] = {}
        self._topology_task: asyncio.Task[None] | None = None

    # ── Startup ────────────────────────────────────────────────────────────
    async def start(self) -> None:
        """Snapshot the world, activate a profile, evaluate open windows."""
        outputs = await self.backend.list_outputs()
        self._outputs = {o.name: o for o in outputs}
        self._topology_key = compute_topology_key(outputs)
        self.active_profile = select_profile(
            self.config.profiles, self._topology_key
        )
        self._adopt_profile_default_layout()
        self._recompute_effective_layout()
        self.state_store.set_active(
            profile=self.active_profile.name if self.active_profile else None,
            layout=self.active_layout.name if self.active_layout else None,
        )
        self.current_desktop = await self.backend.current_desktop()

        for window in await self.backend.list_windows():
            await self.handle_window_opened(window, trigger=TriggerEvent.USER_TRIGGER)

    async def stop(self) -> None:
        """Cancel the debounce task (if any) and flush pending state."""
        if self._topology_task is not None and not self._topology_task.done():
            self._topology_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._topology_task
        await self.state_store.flush()

    # ── Window-event handlers ──────────────────────────────────────────────
    async def handle_window_opened(
        self, info: WindowInfo, *, trigger: TriggerEvent = TriggerEvent.OPENED
    ) -> None:
        self._windows[info.id] = info
        identity = compute_identity(info)
        has_last_seen = self.state_store.get_last_seen(identity) is not None
        decision = evaluate(
            info,
            trigger,
            rules=self.config.rules,
            user_exclusions=self.config.exclusions,
            active_layout=self._effective_layout,
            active_profile_name=(
                self.active_profile.name if self.active_profile else None
            ),
            active_layout_name=(
                self.active_layout.name if self.active_layout else None
            ),
            current_desktop=self.current_desktop,
            has_last_seen=has_last_seen,
            restore_on_open=self.config.general.restore_on_open,
        )
        log.debug(
            "evaluate(%s, %s) → %r", identity, trigger.value, decision
        )
        await self._execute(info, identity, decision)

    async def handle_window_changed(self, info: WindowInfo) -> None:
        """Only re-evaluate on title / type / state changes.

        Geometry changes are never a trigger — the core's feedback-loop
        guard relies on that (see ``docs/07-rules-engine.md`` §Reactive
        evaluation).
        """
        await self.handle_window_opened(info, trigger=TriggerEvent.CHANGED)

    def handle_window_closed(self, wid: WindowId) -> None:
        self._expected_geometry.pop(wid, None)
        self._windows.pop(wid, None)

    def handle_geometry_changed(
        self,
        wid: WindowId,
        geometry: Geometry,
        monitor: OutputName,
        desktop: DesktopIndex,
    ) -> None:
        """Update state.json on a user-initiated geometry change.

        Drops the event when it matches what Perch itself just wrote —
        that's Perch's own round-trip echoing back, not a user action.
        """
        expected = self._expected_geometry.get(wid)
        if expected is not None and expected == geometry:
            # Consume the echo; subsequent events on this window are legit.
            del self._expected_geometry[wid]
            return
        info = self._windows.get(wid)
        if info is None:
            # The window closed between the event and here, or opened-without-
            # an-info (shouldn't happen; backends emit window_opened before
            # geometry_changed per docs/03). Drop — there's no identity to key on.
            return
        self._remember(info, geometry, monitor, desktop)

    # ── Output / topology handlers ─────────────────────────────────────────
    async def handle_output_added(self, info: OutputInfo) -> None:
        self._outputs[info.name] = info
        self._schedule_topology_recompute()

    async def handle_output_removed(self, name: OutputName) -> None:
        self._outputs.pop(name, None)
        self._schedule_topology_recompute()

    async def handle_output_changed(self, info: OutputInfo) -> None:
        self._outputs[info.name] = info
        self._schedule_topology_recompute()

    def _schedule_topology_recompute(self) -> None:
        """Debounce 300 ms: coalesce rapid reconfigure events into one eval."""
        if self._topology_task is not None and not self._topology_task.done():
            self._topology_task.cancel()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._topology_task = loop.create_task(self._debounced_recompute())

    async def _debounced_recompute(self) -> None:
        try:
            await asyncio.sleep(self.topology_debounce_seconds)
        except asyncio.CancelledError:
            return
        await self.recompute_topology()

    async def recompute_topology(self) -> None:
        """Recompute topology key + active profile; re-evaluate open windows.

        Exposed publicly so tests can bypass the debounce delay.
        """
        outputs = list(self._outputs.values())
        new_key = compute_topology_key(outputs)
        if new_key == self._topology_key:
            return
        self._topology_key = new_key
        new_profile = select_profile(self.config.profiles, new_key)
        self.active_profile = new_profile
        self._adopt_profile_default_layout()
        self._recompute_effective_layout()
        self.state_store.set_active(
            profile=new_profile.name if new_profile else None,
            layout=self.active_layout.name if self.active_layout else None,
        )
        self.state_store.mark_dirty()
        await self.reapply()

    # ── Layout activation ──────────────────────────────────────────────────
    async def activate_layout(self, name: str | None) -> None:
        """Switch to a named layout (or deactivate with ``None``).

        Activation is not a window event and therefore re-evaluates every
        open window under the new layout. Per ``docs/09-layouts-profiles.md``
        §Activating / deactivating, deactivating does *not* move windows
        back — that's a "Revert layout" action held in RAM (out of M2.d).
        """
        if name is None:
            self.active_layout = None
        else:
            layout = self.config.layouts.get(name)
            if layout is None:
                raise ValueError(f"unknown layout {name!r}")
            self.active_layout = layout
        self._recompute_effective_layout()
        self.state_store.set_active(
            profile=self.active_profile.name if self.active_profile else None,
            layout=name,
        )
        self.state_store.mark_dirty()
        await self.reapply()

    async def reapply(self) -> None:
        """Re-evaluate every open window under the current profile + layout.

        A user trigger (``USER_TRIGGER``), not a window event — wired to the
        "Reapply rules now" tray action and reused by :meth:`activate_layout`
        and :meth:`recompute_topology` once they have updated active state.
        Unlike ``recompute_topology`` it does not gate on the topology key:
        the user asked for a re-apply, so every open window is re-evaluated.
        """
        for window in await self.backend.list_windows():
            await self.handle_window_opened(
                window, trigger=TriggerEvent.USER_TRIGGER
            )

    # ── Pause Perch ────────────────────────────────────────────────────────
    def toggle_pause(self) -> bool:
        """Flip the pause flag and return the new value.

        When paused, :meth:`_execute` drops every placement decision, so
        no window is moved automatically. The tray menu wires middle-click
        + the "Pause Perch" menu item to this method.
        """
        self.paused = not self.paused
        log.info("pause %s", "enabled" if self.paused else "disabled")
        return self.paused

    # ── Profile default layout ────────────────────────────────────────────
    def _adopt_profile_default_layout(self) -> None:
        """Activate the layout the newly-active profile declares.

        ``docs/09-layouts-profiles.md`` §Activation step 2: activating a
        profile applies its ``default_layout`` too. A profile that declares
        none leaves the current layout alone — step 3 keeps layouts working
        under the implicit unnamed profile, so a topology change must not
        silently drop one the user activated by hand.
        """
        if self.active_profile is None:
            return
        name = self.active_profile.default_layout
        if name is None:
            return
        layout = self.config.layouts.get(name)
        if layout is None:
            # The config loader rejects a profile naming an unknown layout,
            # so this only fires if the two fall out of step.
            log.warning(
                "profile %r declares unknown default_layout %r; ignoring",
                self.active_profile.name, name,
            )
            return
        self.active_layout = layout

    # ── Effective layout (base layout + profile overrides) ────────────────
    def _recompute_effective_layout(self) -> None:
        if self.active_layout is None:
            self._effective_layout = None
            return
        if self.active_profile is None:
            self._effective_layout = self.active_layout
            return
        overrides = tuple(
            entry
            for override in self.active_profile.overrides
            if override.layout == self.active_layout.name
            for entry in override.windows
        )
        self._effective_layout = self.active_layout.with_overrides(overrides)

    # ── Decision execution ─────────────────────────────────────────────────
    async def _execute(
        self, window: WindowInfo, identity: str, decision: Decision
    ) -> None:
        if self.paused:
            # "Pause Perch" panic toggle — suppress every placement
            # decision (rules, layouts, last-seen restore) so no window is
            # moved automatically. Manual snap bypasses the reducer, so it
            # stays live. See docs/08-ui.md §Menu structure.
            log.debug("placement suppressed (paused): %s", identity)
            return
        if isinstance(decision, Ignore):
            return
        if isinstance(decision, RestoreLastSeen):
            await self._restore_last_seen(window, identity)
            return
        if isinstance(decision, ApplyActionDecision):
            await self._apply_action(
                window, identity, decision.action, decision.source
            )

    async def _restore_last_seen(
        self, window: WindowInfo, identity: str
    ) -> None:
        record = self.state_store.get_last_seen(identity)
        if record is None:
            return
        await self._set_geometry_safe(
            window, record.geometry, record.monitor, record.desktop
        )

    async def _apply_action(
        self,
        window: WindowInfo,
        identity: str,
        action: ApplyAction,
        source: str,
    ) -> None:
        try:
            placement = resolve_action(
                action,
                window,
                list(self._outputs.values()),
                self.config.snaps,
                profile_outputs=(
                    profile_output_names(self.active_profile.topology)
                    if self.active_profile is not None
                    else None
                ),
            )
        except ResolveError as exc:
            log.warning("resolve failed for %s: %s", identity, exc)
            return

        target_monitor = placement.monitor or window.monitor
        target_desktop = (
            placement.desktop if placement.desktop is not None else window.desktop
        )

        if placement.unmaximize_first:
            await self._set_state_safe(window, WindowState.NORMAL)

        if placement.geometry is not None:
            await self._set_geometry_safe(
                window, placement.geometry, target_monitor, target_desktop
            )
        elif placement.monitor is not None or placement.desktop is not None:
            # Monitor / desktop moves without a geometry: pass through the
            # window's current geometry so the backend has something to place.
            await self._set_geometry_safe(
                window, window.geometry, target_monitor, target_desktop
            )

        if placement.maximized is True:
            await self._set_state_safe(
                window,
                WindowState.MAXIMIZED,
                fallback_monitor=target_monitor,
                fallback_desktop=target_desktop,
                source=source,
            )

    # ── Backend wrappers with fallback ─────────────────────────────────────
    async def _set_geometry_safe(
        self,
        window: WindowInfo,
        geometry: Geometry,
        monitor: OutputName,
        desktop: DesktopIndex,
    ) -> None:
        self._expected_geometry[window.id] = geometry
        try:
            await self.backend.set_geometry(
                window.id, geometry, monitor=monitor, desktop=desktop
            )
        except UnknownWindow:
            # Raced with a close event — discard the expectation and move on.
            self._expected_geometry.pop(window.id, None)
            return
        except UnknownOutput as exc:
            log.warning(
                "set_geometry: %s (window=%s); skipping placement", exc, window.id
            )
            self._expected_geometry.pop(window.id, None)
            return
        except BackendUnsupported as exc:
            log.warning(
                "set_geometry: backend rejected request (%s); skipping", exc
            )
            self._expected_geometry.pop(window.id, None)
            return

        self._remember(window, geometry, monitor, desktop)

    async def _set_state_safe(
        self,
        window: WindowInfo,
        state: WindowState,
        *,
        fallback_monitor: OutputName | None = None,
        fallback_desktop: DesktopIndex | None = None,
        source: str | None = None,
    ) -> None:
        try:
            await self.backend.set_state(window.id, state)
        except BackendUnsupported as exc:
            if state is WindowState.MAXIMIZED:
                # docs/02-state-format.md §Apply actions: fall back to the
                # work area of the *resolved target* monitor — the window's
                # own monitor is where it sat before this action moved it —
                # and name the rule in the log line.
                monitor = fallback_monitor or window.monitor
                desktop = (
                    fallback_desktop
                    if fallback_desktop is not None
                    else window.desktop
                )
                log.debug(
                    "set_state MAXIMIZED unsupported (%s); %s falls back to "
                    "the work area of %s",
                    exc, source or "placement", monitor,
                )
                output = self._outputs.get(monitor)
                if output is not None:
                    await self._set_geometry_safe(
                        window, output.work_area, monitor, desktop
                    )
                return
            log.warning("set_state failed: %s", exc)
        except UnknownWindow:
            return

    # ── state.json writes ──────────────────────────────────────────────────
    def _remember(
        self,
        window: WindowInfo,
        geometry: Geometry,
        monitor: OutputName,
        desktop: DesktopIndex,
    ) -> None:
        """Record this window's geometry, unless it must not be remembered.

        Two kinds never reach ``state.json``. One the exclusion layer covers
        (``docs/07-rules-engine.md`` §Evaluation order): Perch does not manage
        it, so restoring it later would be exactly the thing the exclusion
        asked Perch not to do. And one whose identity is
        :data:`~perch.core.identity.UNKNOWN_IDENTITY`, which every window
        missing both ``app_id`` and ``wm_class`` shares — remembering under it
        would have unrelated windows overwrite each other.
        """
        identity = compute_identity(window)
        if identity == UNKNOWN_IDENTITY:
            log.debug(
                "not remembering window %s: reports no app_id or wm_class",
                window.id,
            )
            return
        if is_builtin_excluded(window) or is_user_excluded(
            window, self.config.exclusions
        ):
            log.debug("not remembering excluded window %s", identity)
            return
        self.state_store.record_window(identity, geometry, monitor, desktop)
        self.state_store.mark_dirty()

    # ── Signal binding (live app only; tests drive handlers directly) ──────
    def bind_signals(self) -> None:
        """Wire backend signals to ``handle_*`` methods.

        Uses ``qasync.asyncSlot`` for async handlers so exceptions raised
        from them propagate to the asyncio loop's exception handler rather
        than being silently dropped by ``asyncio.ensure_future``.
        """
        import qasync  # local import: avoids a hard qasync dep in pure-core tests

        self.backend.window_opened.connect(
            qasync.asyncSlot(object)(self._on_window_opened)
        )
        self.backend.window_changed.connect(
            qasync.asyncSlot(object)(self._on_window_changed)
        )
        self.backend.window_closed.connect(self.handle_window_closed)
        self.backend.geometry_changed.connect(self.handle_geometry_changed)
        self.backend.output_added.connect(
            qasync.asyncSlot(object)(self._on_output_added)
        )
        self.backend.output_removed.connect(
            qasync.asyncSlot(str)(self._on_output_removed)
        )
        self.backend.output_changed.connect(
            qasync.asyncSlot(object)(self._on_output_changed)
        )

    # ── asyncSlot trampolines (keep bind_signals tidy) ─────────────────────
    async def _on_window_opened(self, info: WindowInfo) -> None:
        await self.handle_window_opened(info)

    async def _on_window_changed(self, info: WindowInfo) -> None:
        await self.handle_window_changed(info)

    async def _on_output_added(self, info: OutputInfo) -> None:
        await self.handle_output_added(info)

    async def _on_output_removed(self, name: OutputName) -> None:
        await self.handle_output_removed(name)

    async def _on_output_changed(self, info: OutputInfo) -> None:
        await self.handle_output_changed(info)


