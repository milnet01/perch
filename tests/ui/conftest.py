"""UI-test fixtures.

`pytest-qt` provides a session-scoped ``qapp``. We force
``QT_QPA_PLATFORM=offscreen`` so widget tests run under CI without Xvfb.

qasync 0.28 exposes a ``DefaultQEventLoopPolicy`` class only on Python
< 3.12; on 3.12+ qasync uses ``asyncio.run(..., loop_factory=...)``
instead. Tests that need a qasync-backed loop construct it explicitly
(see `tests/core/test_reducer.py` for the pattern); we don't override
pytest-asyncio's loop policy globally here.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
