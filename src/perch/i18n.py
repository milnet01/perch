"""Translation loading.

Translations live at ``translations/perch_<locale>.ts`` in the source tree,
compiled to ``perch_<locale>.qm`` at install time by ``pyside6-lrelease``.
See ``docs/08-ui.md`` §Localization.

The module-level :class:`QTranslator` instances are **load-bearing**: Qt
only holds weak references through ``QCoreApplication.installTranslator``,
and if the Python side lets them go out of scope the GC reclaims them and
every translated string silently reverts to source. Keeping them at module
scope is the documented fix for the #1 PySide6 i18n footgun.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QLibraryInfo, QLocale, QTranslator

log = logging.getLogger(__name__)

_app_translator = QTranslator()
_qt_translator = QTranslator()


def _candidate_translation_dirs() -> list[Path]:
    """Return translation directory candidates in preference order.

    Environment override wins so developers can point at an arbitrary
    checkout. Flatpak's ``/app`` prefix comes next, then the system install
    prefix (``$sys.prefix/share/perch/translations``), then the dev-checkout
    fallback (three levels up from this file — ``src/perch/i18n.py`` →
    repo root → ``translations/``).
    """
    dirs: list[Path] = []
    override = os.environ.get("PERCH_TRANSLATIONS_DIR")
    if override:
        dirs.append(Path(override))
    dirs.append(Path("/app/share/perch/translations"))
    dirs.append(Path(sys.prefix) / "share" / "perch" / "translations")
    dirs.append(Path(__file__).resolve().parents[2] / "translations")
    return dirs


def install_translators(app: QCoreApplication) -> None:
    """Install Qt's own translations + Perch's translations on ``app``.

    Both are loaded for :func:`PySide6.QtCore.QLocale.system`. If no
    ``.qm`` matches the locale fallback chain :meth:`QTranslator.load`
    returns False and the source (English) strings stay in use — that is
    the graceful no-op path for "we haven't translated your locale yet".
    """
    locale = QLocale.system()

    qt_path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if _qt_translator.load(locale, "qtbase", "_", qt_path):
        app.installTranslator(_qt_translator)
        log.debug("installed Qt base translations from %s", qt_path)

    for candidate in _candidate_translation_dirs():
        if not candidate.is_dir():
            continue
        if _app_translator.load(locale, "perch", "_", str(candidate)):
            app.installTranslator(_app_translator)
            log.debug("installed Perch translations from %s", candidate)
            return
    log.debug("no Perch translations found for locale %s", locale.name())
