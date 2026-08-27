"""First-run setup wizard.

Three pages, specified in :file:`docs/08-ui.md` §First-run setup wizard:

1. **Welcome** — the one thing that matters: Perch needs no configuration.
2. **Health checks** — tray visibility, start-at-login, compositor.
3. **Done** — with an optional signpost to the config dialog.

It runs once, gated on ``[general] onboarding_completed``, and is
re-launchable from the config dialog's General page.

The badge logic lives in the module-level ``check_*`` functions so it is
unit-testable without a live desktop — the same discipline the tray tests
use. Only rows 1 and 3 are checks; **Start Perch at login** is a
*preference*, so it renders on/off and never a warning: turning autostart
off is a valid choice, not a fault.

This module names backends by ``type(backend).__name__`` rather than
importing them. :mod:`perch.ui` never imports :mod:`perch.backend` at
runtime (see that package's docstring); :mod:`perch.ui.status` sets the
same precedent with a ``TYPE_CHECKING``-only import.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QLabel,
    QVBoxLayout,
    QWizard,
    QWizardPage,
)

from perch.config.writer import load_document, write_document

from .. import autostart, paths
from ..config import Config
from ..config.edit import apply_general
from .sni_probe import is_gnome_wayland, sni_host_available

if TYPE_CHECKING:
    from collections.abc import Callable

    from PySide6.QtWidgets import QWidget

    from ..backend.base import WindowBackend

log = logging.getLogger(__name__)


# ── Health-check rows ────────────────────────────────────────────────────────


#: Row is healthy.
BADGE_OK = "ok"
#: Row needs attention. Only rows 1 and 3 can ever carry this.
BADGE_WARN = "warn"
#: Row is a preference that is switched off — neutral, never a fault.
BADGE_OFF = "off"

_BADGE_GLYPHS = {BADGE_OK: "✓", BADGE_WARN: "⚠", BADGE_OFF: "●"}


@dataclass(frozen=True)
class CheckResult:
    """One health-check row's verdict, independent of any widget."""

    badge: str
    title: str
    detail: str = ""


def badge_glyph(badge: str) -> str:
    """The glyph a badge renders as. Unknown badges fall back to the off dot."""
    return _BADGE_GLYPHS.get(badge, _BADGE_GLYPHS[BADGE_OFF])


#: Where a GNOME Wayland user installs the tray-icon extension. Verified
#: reachable 2026-08-27. ``docs/08-ui.md`` §First-run setup wizard asks the
#: wizard's tray row to carry a link; the standalone hint keeps copy only.
APPINDICATOR_EXTENSION_URL = (
    "https://extensions.gnome.org/extension/615/appindicator-support/"
)


def appindicator_guidance() -> str:
    """The GNOME-Wayland "install the extension" copy.

    Shared with :func:`perch.app._maybe_show_appindicator_hint` so the two
    surfaces cannot drift. The translation context stays ``perch.app`` —
    the string was extracted under it before this helper existed, and the
    context is an argument rather than a property of this file.
    """
    return QCoreApplication.translate(
        "perch.app",
        "GNOME Wayland doesn't show tray icons by default. Please install "
        "the <b>AppIndicator and KStatusNotifierItem Support</b> GNOME "
        "extension to see Perch in your top bar.",
    )


def check_tray(
    *, have_host: bool | None = None, gnome: bool | None = None
) -> CheckResult:
    """Row 1 — is a StatusNotifier host present to draw the tray icon?

    The probes are injectable so the badge logic can be tested without a
    session bus.
    """
    ctx = "perch.ui.onboarding"
    host = sni_host_available() if have_host is None else have_host
    if host:
        return CheckResult(
            BADGE_OK, QCoreApplication.translate(ctx, "Tray icon visible")
        )
    on_gnome = is_gnome_wayland() if gnome is None else gnome
    if on_gnome:
        link = QCoreApplication.translate(
            ctx, "Install it from extensions.gnome.org"
        )
        return CheckResult(
            BADGE_WARN,
            QCoreApplication.translate(ctx, "Tray icon not visible"),
            f'{appindicator_guidance()} '
            f'<a href="{APPINDICATOR_EXTENSION_URL}">{link}</a>',
        )
    return CheckResult(
        BADGE_WARN,
        QCoreApplication.translate(ctx, "Tray icon not confirmed"),
        QCoreApplication.translate(
            ctx,
            "Couldn't confirm a tray host — Perch still runs; reach it with "
            "<code>perch --settings</code>.",
        ),
    )


def check_autostart(*, enabled: bool) -> CheckResult:
    """Row 2 — a *preference*, not a check.

    ``enabled`` is the live checkbox, never :func:`perch.autostart.is_enabled`,
    which reports False on the Flatpak/portal path because it cannot cheaply
    query portal autostart — that would render a false off-state.
    """
    ctx = "perch.ui.onboarding"
    return CheckResult(
        BADGE_OK if enabled else BADGE_OFF,
        QCoreApplication.translate(ctx, "Start Perch at login"),
    )


#: One label per real backend. Keyed by class name so this module does not
#: import :mod:`perch.backend`. ``MockBackend`` is deliberately absent — it
#: means no compatible compositor was found, which is the ⚠ case.
#:
#: Public because it states a contract a test should hold us to: every real
#: backend has exactly one label, so adding a backend without a label here
#: is a caught omission rather than a silent "limited mode".
BACKEND_LABELS = {
    "KWinBackend": "KWin / Plasma",
    "MutterBackend": "Mutter / GNOME",
    "SwayBackend": "Sway",
    "HyprlandBackend": "Hyprland",
    "X11Backend": "X11",
}


def backend_label(backend: WindowBackend | None) -> str | None:
    """Display name for ``backend``, or None when it is not a real one."""
    if backend is None:
        return None
    return BACKEND_LABELS.get(type(backend).__name__)


def check_compositor(backend: WindowBackend | None) -> CheckResult:
    """Row 3 — did Perch find a compositor it can drive?"""
    ctx = "perch.ui.onboarding"
    label = backend_label(backend)
    if label is None:
        return CheckResult(
            BADGE_WARN,
            QCoreApplication.translate(ctx, "No compatible compositor"),
            QCoreApplication.translate(
                ctx,
                "Perch is running in limited mode — it can't move windows "
                "on this session.",
            ),
        )
    return CheckResult(
        BADGE_OK,
        QCoreApplication.translate(ctx, "Compositor detected"),
        label,
    )


# ── Pages ────────────────────────────────────────────────────────────────────


class _WelcomePage(QWizardPage):
    """Page 1 — states that no configuration is needed, and stops there."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setTitle(self.tr("Welcome to Perch"))
        body = QLabel(
            self.tr(
                "<p>You don't need to configure anything.</p>"
                "<p>Just move your windows where you like them — Perch "
                "remembers, and puts them back next time.</p>"
            )
        )
        body.setWordWrap(True)
        body.setTextFormat(Qt.TextFormat.RichText)
        layout = QVBoxLayout(self)
        layout.addWidget(body)
        layout.addStretch(1)


class _HealthPage(QWizardPage):
    """Page 2 — three rows: two checks and one preference."""

    def __init__(
        self,
        config: Config,
        backend: WindowBackend | None,
        parent: QWidget | None = None,
        *,
        have_host: bool | None = None,
        gnome: bool | None = None,
    ) -> None:
        super().__init__(parent)
        self.setTitle(self.tr("Checking your setup"))
        layout = QVBoxLayout(self)

        self.tray_result = check_tray(have_host=have_host, gnome=gnome)
        layout.addWidget(_row_widget(self.tray_result))

        self.start_at_login = QCheckBox(self.tr("Start Perch at login"))
        self.start_at_login.setChecked(config.general.start_at_login)
        self._autostart_badge = QLabel()
        self.start_at_login.toggled.connect(self._refresh_autostart_badge)
        row = QVBoxLayout()
        row.addWidget(self.start_at_login)
        row.addWidget(self._autostart_badge)
        layout.addLayout(row)
        self._refresh_autostart_badge(self.start_at_login.isChecked())

        self.compositor_result = check_compositor(backend)
        layout.addWidget(_row_widget(self.compositor_result))
        layout.addStretch(1)

    def _refresh_autostart_badge(self, enabled: bool) -> None:
        result = check_autostart(enabled=enabled)
        self._autostart_badge.setText(
            f"{badge_glyph(result.badge)} {result.title}"
        )


class _DonePage(QWizardPage):
    """Page 3 — done, plus the optional signpost to the config dialog."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setTitle(self.tr("That's it"))
        body = QLabel(self.tr("Perch is watching."))
        body.setWordWrap(True)
        self.show_config = QCheckBox(self.tr("Show me what else Perch can do"))
        self.show_config.setChecked(False)
        layout = QVBoxLayout(self)
        layout.addWidget(body)
        layout.addWidget(self.show_config)
        layout.addStretch(1)


def _row_widget(result: CheckResult) -> QLabel:
    """Render one :class:`CheckResult` as a single wrapped rich-text label."""
    text = f"<b>{badge_glyph(result.badge)} {result.title}</b>"
    if result.detail:
        text += f"<br>{result.detail}"
    label = QLabel(text)
    label.setWordWrap(True)
    label.setTextFormat(Qt.TextFormat.RichText)
    label.setOpenExternalLinks(True)
    return label


# ── Wizard ───────────────────────────────────────────────────────────────────


class SetupWizard(QWizard):
    """The three-page wizard itself. Owns no persistence."""

    def __init__(
        self,
        config: Config,
        backend: WindowBackend | None,
        parent: QWidget | None = None,
        *,
        have_host: bool | None = None,
        gnome: bool | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Perch — Setup"))
        self.addPage(_WelcomePage(self))
        self.health = _HealthPage(
            config, backend, self, have_host=have_host, gnome=gnome
        )
        self.addPage(self.health)
        self.done_page = _DonePage(self)
        self.addPage(self.done_page)

    @property
    def start_at_login(self) -> bool:
        """The live value of the health page's autostart checkbox."""
        return bool(self.health.start_at_login.isChecked())

    @property
    def wants_config_dialog(self) -> bool:
        """Whether the user asked to be shown the rest of Perch."""
        return bool(self.done_page.show_config.isChecked())


@dataclass(frozen=True)
class WizardOutcome:
    """What a wizard run decided, for the caller to act on."""

    #: Config as it stands after the run — always ``onboarding_completed``.
    config: Config
    #: True when the user reached Finish rather than cancelling or closing.
    accepted: bool
    #: True when Finish was reached with "show me what else" ticked.
    show_config_dialog: bool


def run_setup_wizard(
    config: Config,
    backend: WindowBackend | None,
    parent: QWidget | None = None,
    *,
    config_path: Path | None = None,
    have_host: bool | None = None,
    gnome: bool | None = None,
    load_document_callback: Callable[[Path], Any] | None = None,
    save_callback: Callable[[Path, Any], None] | None = None,
) -> WizardOutcome:
    """Run the wizard modally and persist the result.

    ``onboarding_completed`` is written on **every** exit — Finish, Cancel
    and window-close alike (Qt routes ✕ and Cancel through the same
    ``reject()``) — so the wizard never reappears unprompted.

    The autostart checkbox is persisted to config rather than only synced to
    the OS: :func:`perch.autostart.sync_from_config` reconciles from
    ``config.general.start_at_login`` at every startup, so writing the old
    value back would revert the toggle at the next login.

    * **Finish** — the checkbox is persisted *and* applied via
      :func:`perch.autostart.sync`.
    * **Cancel / close** — the flag is written, the checkbox is dropped, and
      no system setting is touched.
    """
    wizard = SetupWizard(config, backend, parent, have_host=have_host, gnome=gnome)
    accepted = wizard.exec() == QDialog.DialogCode.Accepted

    start_at_login = (
        wizard.start_at_login if accepted else config.general.start_at_login
    )
    general = replace(
        config.general,
        start_at_login=start_at_login,
        onboarding_completed=True,
    )
    path = config_path or paths.config_file()
    load_doc = load_document_callback or load_document
    save = save_callback or write_document
    try:
        document = load_doc(path)
        apply_general(
            document,
            start_at_login=general.start_at_login,
            restore_on_open=general.restore_on_open,
            notify_on_restore=general.notify_on_restore,
            theme=general.theme,
            onboarding_completed=True,
        )
        save(path, document)
    except Exception:
        # A failed write must not stop Perch starting. The wizard will run
        # again next launch, which is the benign failure of the two.
        log.exception("setup wizard: could not persist onboarding state")

    if accepted:
        autostart.sync(start_at_login)

    return WizardOutcome(
        config=replace(config, general=general),
        accepted=accepted,
        show_config_dialog=accepted and wizard.wants_config_dialog,
    )
