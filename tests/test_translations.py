"""Regression tests for the extracted translation catalogue.

Guards the class of bug where a string is marked for extraction under one
context but translated at runtime under another, so the translation never
resolves. This is invisible at runtime (``QCoreApplication.translate`` always
uses the context passed to it) — the mismatch only shows up in the extracted
``.ts`` catalogue, which is what these tests inspect.

Originally locks the fix for the tray snap presets, which were marked with a
bare ``QT_TR_NOOP`` (empty context) yet looked up under ``perch.ui.tray``.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from perch.ui.tray import BUILTIN_SNAP_MENU_ITEMS

TS_PATH = Path(__file__).resolve().parents[1] / "translations" / "perch_en.ts"


def _sources_by_context() -> dict[str, set[str]]:
    """Map each ``<context><name>`` to the set of its ``<source>`` strings."""
    root = ET.parse(TS_PATH).getroot()
    out: dict[str, set[str]] = {}
    for context in root.findall("context"):
        name = (context.findtext("name") or "").strip()
        out.setdefault(name, set()).update(
            (msg.findtext("source") or "") for msg in context.findall("message")
        )
    return out


def test_no_empty_translation_context() -> None:
    """A string extracted under the empty context can never be looked up.

    Every runtime ``translate`` / ``QT_TRANSLATE_NOOP`` call passes a real
    context, so an empty ``<name>`` in the catalogue is always a marker/lookup
    mismatch (the bare-``QT_TR_NOOP`` footgun).
    """
    contexts = _sources_by_context()
    assert "" not in contexts, (
        "translations/perch_en.ts has an empty-context block — a string is "
        "marked with a context-less NOOP; use QT_TRANSLATE_NOOP(<context>, …)"
    )


def test_snap_labels_extracted_under_tray_context() -> None:
    """Snap-preset labels must extract under the context the menu looks them up.

    ``build_tray_menu`` translates them via
    ``QCoreApplication.translate("perch.ui.tray", label)``; the catalogue entry
    must live under that same context or a translator's work never reaches the
    menu.
    """
    tray_sources = _sources_by_context().get("perch.ui.tray", set())
    missing = [
        label for _preset, label in BUILTIN_SNAP_MENU_ITEMS
        if label not in tray_sources
    ]
    assert not missing, (
        f"snap labels not extracted under perch.ui.tray: {missing} — "
        "re-run scripts/i18n-update.sh after changing tray strings"
    )
