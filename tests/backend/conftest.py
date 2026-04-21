"""Backend-compliance fixtures.

The compliance tests parameterise over every backend class Perch ships. The
set is filtered at collection time by :meth:`WindowBackend.is_available`
— backends whose transport isn't detectable on the current host are
skipped rather than failing ``start()``. This keeps the suite green on
dev boxes that don't have every compositor installed, while still
exercising each backend end-to-end in CI hosts that do.

The full matrix:

* ``mock`` — always available; the compliance anchor.
* ``kwin`` — only on KDE / Plasma Wayland sessions.
* ``x11`` — only when ``$DISPLAY`` is set (live X11 or XWayland).
* ``sway`` / ``hyprland`` / ``mutter`` — M6 stubs; gated on their
  respective environment variables.

The compliance tests that need a *seeded* mock (pre-arranged windows /
outputs / desktops) inspect ``backend`` via ``isinstance(backend,
MockBackend)`` and skip themselves against real backends — those tests
are testing the mock's driver API, not the contract.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import cast

import pytest

from perch.backend import (
    BackendUnavailable,
    Geometry,
    OutputInfo,
    WindowBackend,
)
from perch.backend.mock import MockBackend


def _all_backends() -> dict[str, type[WindowBackend]]:
    """Materialise the full backend matrix, lazily importing each class.

    We import lazily so that the test-collection phase doesn't require
    every backend's runtime deps to be installed — e.g. a dev box
    without ``i3ipc`` should still be able to run ``pytest`` against the
    mock.
    """
    classes: dict[str, type[WindowBackend]] = {"mock": cast(type[WindowBackend], MockBackend)}

    def _try_import(name: str, module_path: str, class_name: str) -> None:
        try:
            from importlib import import_module

            module = import_module(module_path)
            classes[name] = cast(type[WindowBackend], getattr(module, class_name))
        except Exception:  # pragma: no cover — missing optional dep
            # Missing transport deps shouldn't stop the suite from running;
            # the backend simply won't be parameterised.
            return

    _try_import("kwin",     "perch.backend.kwin",     "KWinBackend")
    _try_import("x11",      "perch.backend.x11",      "X11Backend")
    _try_import("sway",     "perch.backend.sway",     "SwayBackend")
    _try_import("hyprland", "perch.backend.hyprland", "HyprlandBackend")
    _try_import("mutter",   "perch.backend.mutter",   "MutterBackend")
    return classes


_ALL_BACKENDS = _all_backends()

#: Backends that will be exercised by the compliance suite on this host.
#: Mock is always in; real backends are included only if their probe
#: reports ``True`` (``$DISPLAY`` / ``$SWAYSOCK`` / … present).
BACKEND_CLASSES: dict[str, type[WindowBackend]] = {
    name: cls for name, cls in _ALL_BACKENDS.items() if cls.is_available()
}


@pytest.fixture(autouse=True)
def _require_qapp(qapp: object) -> None:
    """Ensure a ``QApplication`` exists so ``QObject`` construction works."""


@pytest.fixture(params=list(BACKEND_CLASSES))
def backend_name(request: pytest.FixtureRequest) -> str:
    return cast(str, request.param)


@pytest.fixture
def backend_cls(backend_name: str) -> type[WindowBackend]:
    return BACKEND_CLASSES[backend_name]


@pytest.fixture
async def backend(backend_cls: type[WindowBackend]) -> AsyncIterator[WindowBackend]:
    b = backend_cls()
    try:
        await b.start()
    except BackendUnavailable as exc:
        # The ``is_available`` probe was optimistic; the real transport
        # turned out to be missing after all. Skip rather than fail.
        pytest.skip(f"backend {backend_cls.__name__} unavailable: {exc}")
    _seed(b)
    try:
        yield b
    finally:
        await b.stop()


def _seed(backend: WindowBackend) -> None:
    """Seed two outputs and four desktops. Mock-only.

    Real backends have whatever outputs + windows their compositor
    presents; the compliance tests that would otherwise depend on seeded
    state skip themselves via ``isinstance(backend, MockBackend)``
    checks.
    """
    if isinstance(backend, MockBackend):
        backend._add_output(
            OutputInfo(
                name="DP-1",
                geometry=Geometry(0, 0, 2560, 1440),
                work_area=Geometry(0, 0, 2560, 1400),
                scale=1.0,
                refresh_mhz=144000,
                is_primary=True,
                is_connected=True,
            )
        )
        backend._add_output(
            OutputInfo(
                name="HDMI-1",
                geometry=Geometry(2560, 360, 1920, 1080),
                work_area=Geometry(2560, 360, 1920, 1040),
                scale=1.0,
                refresh_mhz=60000,
                is_primary=False,
                is_connected=True,
            )
        )
        backend._set_desktop(0, count=4)
