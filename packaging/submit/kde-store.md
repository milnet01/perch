# KDE Store submission (manual — web flow)

No CLI. Listing goes through store.kde.org's submission web form.

## Prerequisites

1. **An install source.** On hold: this walkthrough was written to
   point at a Flathub build, and Perch is not on Flathub (user decision,
   2026-11-11). Step 4 needs a source for the GitHub release files first
   (PERC-0002).
2. KDE Store account at https://store.kde.org. Sign in with an
   OpenDesktop / KDE Identity account.

## Walkthrough

1. Go to https://store.kde.org/ → **Add Product** (top right).
2. Select category: **Plasma Applications** → **Utilities**.
3. Fill in the listing from `packaging/kde-store/LISTING.md`:
   - **Name:** Perch
   - **Description:** copy from the Short / Full description fields
     in `LISTING.md`.
   - **Tags:** copy from `LISTING.md` §Tags.
   - **Homepage:** `https://github.com/milnet01/perch`
   - **Issue tracker:** `https://github.com/milnet01/perch/issues`
   - **License:** GPL-3.0-or-later.
4. **Install source:** not decided; see prerequisite 1.
5. **Screenshots:** upload the two images from
   `docs/screenshots/tray-menu.png` and `docs/screenshots/rules-editor.png`.
   They're committed alongside the v1.0.0 tag, so also acceptable:
   raw-URL links to
   `https://raw.githubusercontent.com/milnet01/perch/v1.0.0/docs/screenshots/*.png`.
6. **Icon:** upload `data/icons/hicolor/scalable/apps/io.github.milnet01.Perch.svg`.
7. Submit for review. KDE Store review is usually fast (hours, not
   days).

## After acceptance

The listing appears in KDE's **Get Hot New Stuff** browser (Discover /
System Settings → Get New Stuff). How it follows new releases depends on
the install source, which is not decided.

## Updating the listing

When the `docs/screenshots/*.png` regenerate (via
`scripts/render-screenshots.py`), re-upload them through the same
store.kde.org account: your product page → **Edit** → Screenshots.
