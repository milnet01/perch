"""User-interface layer.

Everything in this package is built on ``PySide6.QtWidgets`` and talks to the
core only via :mod:`perch.ui.intents` — a typed intent ADT the core reducer
consumes. The UI never imports from :mod:`perch.backend` directly. See
``docs/01-architecture.md`` §Layers and ``docs/08-ui.md``.
"""

from __future__ import annotations
