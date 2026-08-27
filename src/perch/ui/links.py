"""Outbound links offered by the tray menu.

The funding destinations mirror :file:`.github/FUNDING.yml`, which is the
source of truth for the list. They are stated here rather than read at
runtime because ``.github/`` is not shipped in the wheel, the RPM or the
Flatpak, so there is nothing to read once Perch is installed.

:file:`tests/ui/test_links.py` asserts the two agree, so a destination
added to ``FUNDING.yml`` and not to this module fails the suite rather
than shipping a menu that is quietly out of date — and a donate link that
404s is worse than no donate link at all.
"""

from __future__ import annotations

from typing import NamedTuple

#: Where "Report an issue" goes.
ISSUES_URL = "https://github.com/milnet01/perch/issues"


class FundingLink(NamedTuple):
    """One entry in the Donate submenu."""

    label: str
    url: str


#: One entry per destination in ``.github/FUNDING.yml``, in that file's order.
FUNDING_LINKS: tuple[FundingLink, ...] = (
    FundingLink("GitHub Sponsors", "https://github.com/sponsors/milnet01"),
    FundingLink("Patreon", "https://www.patreon.com/AntsProjectsHub"),
    FundingLink("PayBru", "https://paybru.co.za/tip/ants-projects-hub"),
)

__all__ = ["FUNDING_LINKS", "ISSUES_URL", "FundingLink"]
