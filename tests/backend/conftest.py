"""Backend-compliance fixtures.

The compliance tests parameterise over every backend class Perch ships. For
M2 that is only :class:`MockBackend`; X11 (M4), KWin (M5), and the stubs (M6)
will join by extending the :data:`BACKEND_CLASSES` table.

Every compliance test gets a fresh, already-connected backend seeded with
two outputs (``DP-1``, ``HDMI-1``) and four desktops so that capability
assertions have something to work against.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import cast

import pytest

from perch.backend import (
    Geometry,
    OutputInfo,
    WindowBackend,
)
from perch.backend.mock import MockBackend

BACKEND_CLASSES: dict[str, type[WindowBackend]] = {
    "mock": cast(type[WindowBackend], MockBackend),
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
    await b.start()
    _seed(b)
    try:
        yield b
    finally:
        await b.stop()


def _seed(backend: WindowBackend) -> None:
    """Seed two outputs and four desktops. Mock-only for now.

    When real backends join, each will supply its own seeding (or refuse to
    be seeded if the backend is read-only — the tests skip those cases).
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
