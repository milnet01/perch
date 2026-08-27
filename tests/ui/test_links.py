"""The tray's outbound links, and their agreement with FUNDING.yml.

``.github/FUNDING.yml`` is the source of truth for where donations go, but
it is not shipped in the wheel, the RPM or the Flatpak, so the menu cannot
read it at runtime (see :mod:`perch.ui.links`). These tests are what keeps
the stated copy honest: add a destination to ``FUNDING.yml`` without adding
it to ``links.py`` and the suite fails here rather than in a user's menu.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from perch.ui.links import FUNDING_LINKS, ISSUES_URL

REPO_ROOT = Path(__file__).resolve().parents[2]
FUNDING_YML = REPO_ROOT / ".github" / "FUNDING.yml"


def _funding_urls_from_yaml() -> list[str]:
    """Expand FUNDING.yml's platform shorthands into full URLs."""
    data = yaml.safe_load(FUNDING_YML.read_text())
    urls: list[str] = []
    for platform, value in data.items():
        entries = value if isinstance(value, list) else [value]
        for entry in entries:
            if platform == "github":
                urls.append(f"https://github.com/sponsors/{entry}")
            elif platform == "patreon":
                urls.append(f"https://www.patreon.com/{entry}")
            elif platform == "custom":
                urls.append(str(entry))
            else:  # pragma: no cover - a new platform needs a mapping here
                pytest.fail(
                    f"FUNDING.yml platform {platform!r} has no URL mapping; "
                    "add one here and an entry in perch.ui.links"
                )
    return urls


def test_funding_yml_exists() -> None:
    """A missing file would make every other assertion here vacuous."""
    assert FUNDING_YML.is_file()


def test_donate_menu_covers_every_funding_destination() -> None:
    assert [link.url for link in FUNDING_LINKS] == _funding_urls_from_yaml()


def test_every_link_is_https_and_labelled() -> None:
    """A blank label renders an unclickable-looking menu entry."""
    for link in (*FUNDING_LINKS, type(FUNDING_LINKS[0])("Issues", ISSUES_URL)):
        assert link.url.startswith("https://")
        assert link.label.strip()
