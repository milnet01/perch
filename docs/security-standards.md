# Security standard

Perch's security posture, stated honestly: what is enforced today, and what is
deliberately out of scope for v1. Perch is a single-user desktop tray app — it
holds no secrets, opens no network sockets, and needs no root. This document
describes the actual code as it ships; aspirational items are labelled as such.

## Threat model scope

- **Single-user desktop application.** Perch runs inside one user's login
  session with that user's privileges. It manages the geometry of that user's
  own windows and nothing else.
- **No root.** Perch never elevates. There is no setuid path, no `sudo`, no
  privileged helper. (The drive-level convention of `SUDO_ASKPASS` in the parent
  `CLAUDE.md` covers unrelated system admin, not Perch.)
- **No network service in v1.** Perch listens on nothing and phones home to
  nothing (verified — see §"No telemetry / no network calls"). It is not remotely reachable.
- **In scope:** local config/state file handling, the session-bus / X11 /
  compositor trust boundary, hotkey registration, and supply-chain integrity of
  the shipped artifacts.
- **Out of scope:** a hostile local user or malware already running as the same
  UID. Anything with your UID can already read your files and drive your X11
  server / session bus directly; Perch adds no privilege boundary there and does
  not pretend to.

## Config and state handling

- **XDG paths only.** Config at `$XDG_CONFIG_HOME/perch/config.toml`, machine
  state at `$XDG_STATE_HOME/perch/state.json`, both under the user's home. See
  [02-state-format.md](02-state-format.md).
- **Safe parsing, never `eval`.** Config is read with the stdlib `tomllib`
  parser and written with `tomlkit` (`src/perch/config/loader.py`,
  `src/perch/config/writer.py`). State is plain `json`. No `eval`, `exec`, `pickle`, or YAML-unsafe-load is used
  on any on-disk data — a malformed or malicious config can at worst raise a
  parse/validation error, not execute code.
- **Schema validation + graceful failure.** Every loaded document runs through
  `schema.validate`. A parse or schema failure falls back to the last known-good
  `.bak`, and if that also fails Perch raises `ConfigError` and exits non-zero
  rather than limping on with garbage. A `schema_version` newer than this build
  understands is refused, not guessed at.
- **Atomic writes + backup rotation.** All writes use tmp → `fsync` → rotate old
  file to `.bak` → `rename` → `fsync` dir (`config/writer.py`,
  `core/state_store.py`). A crash or power loss during a write cannot corrupt the
  live file; the previous good copy always survives as `.bak`.
- **No secrets stored.** Perch persists window identities, geometries, rules, and
  layouts — no passwords, tokens, or credentials. Files are world-readable:
  `config.toml` is pinned to mode `0644` on rewrite but umask-derived (typically
  `0644`) on the first-run seed, and `state.json` is always umask-derived. This
  is intentional and safe because nothing sensitive is stored. If you ever add a
  secret-bearing field, that assumption — and every write path's permissions —
  must be revisited.
- **Window titles are treated as sensitive.** The log file omits window titles
  by default (they often leak paths, URLs, chat counterparties); `PERCH_LOG_TITLES=1`
  is an explicit opt-in. See [02-state-format.md](02-state-format.md) §Log file.

## D-Bus / X11 / KWin trust boundary

Perch trusts the session it runs in — the session bus, the X11 server, and the
compositor are all already fully privileged over the user's windows. Perch is a
client of them, not a sandbox around them.

- **X11** ([04-backend-x11.md](04-backend-x11.md)): Perch speaks EWMH to the
  running WM via `python-xlib`. X11 offers no inter-client isolation by design;
  Perch inherits that model and claims no more.
- **KWin** ([05-backend-kwin.md](05-backend-kwin.md)): Perch installs a **bundled
  JS script** shipped inside the package, loaded via
  `org.kde.KWin.Scripting.loadScript(path, pluginId)`. The script is
  version-stamped (`BUNDLED_SCRIPT_VERSION`), pinned to match the Python half,
  and its install is idempotent + checksummed against the bundled source — Perch
  only ever loads its own vendored script from its own install tree, never a
  path supplied by an untrusted party.
- **Own D-Bus name.** Perch owns `io.github.milnet01.Perch` on the session bus;
  the KWin script calls back into it. This is session-scoped — reachable only by
  clients already inside the user's session.

## Global hotkeys

Registered through the compositor/portal, never by snooping input. Order of
preference ([08-ui.md](08-ui.md) §Hotkeys): the
`org.freedesktop.portal.GlobalShortcuts` portal first (user sees a permission
prompt, best for sandboxed Flatpak), then KGlobalAccel on Plasma, then
`XGrabKey` on X11. On GNOME Wayland without portal support Perch **does not
self-grab** — it greys the rows and says so, rather than falling back to a
key-logging shim. Autostart likewise goes through
`org.freedesktop.portal.Background` with a user consent prompt
(`src/perch/autostart.py`).

## Dependency currency as a security posture

Perch runs the **latest stable version** of every dependency as a deliberate
security choice — the latest release is the one receiving security patches, and
a dependency left behind accumulates missed fixes. Caps below latest require a
documented reason (confirmed breakage or a tested major-version ceiling). The
full standard, register, and the currency-sweep command are in
[dependency-policy.md](dependency-policy.md); run the sweep each release cycle.
Runtime surface is intentionally small: PySide6, qasync, sdbus, python-xlib,
tomlkit — all local libraries, none of which open network connections on Perch's
behalf.

## Supply chain and artifact integrity

- **AppImage bundles pinned deps.** The AppImage build freezes the exact built
  wheel into a `requirements.txt` recipe and installs from it in a container
  (`packaging/appimage/build.sh`), so the bundled dependency set is reproducible
  for a given build rather than floating.
- **SHA256SUMS on releases.** Source tarballs from GitHub are SHA256-summed and
  the sums are published in the release notes — verify a download against them
  before running it ([10-packaging.md](10-packaging.md) §Signed binaries /
  reproducible builds).
- **No GPG signing in v1 (honest gap).** Tarballs are *not* GPG-signed; GitHub's
  release infrastructure is the current tamper-evidence story. Fully
  reproducible builds are not a v1 target either, though the Python-only +
  static-data shape makes them attainable — both are tracked in the roadmap, not
  shipped.

## No telemetry / no network calls

Verified against the source tree: Perch makes **no network calls**. There is no
`requests`, `urllib`, `httpx`, or `aiohttp` usage anywhere in `src/`; the sockets
in play are all local — the X11 display socket, the session D-Bus socket (KWin
backend, the GlobalShortcuts / Background portals), and the Unix-domain IPC
sockets for the Sway/Hyprland stub backends. There is no analytics, crash
reporting, or update check that contacts a remote host. Perch is fully
offline-capable.

## Reporting a vulnerability

The disclosure channel is [`SECURITY.md`](../SECURITY.md) at the repository root:
report privately through **GitHub's private vulnerability reporting**
(`Security → Report a vulnerability`), never a public issue for anything
exploitable. `SECURITY.md` states the supported versions (latest 1.x), the
expected acknowledgement window, and what is in/out of scope for a single-user,
no-root, no-network desktop app.

## See also

- [02-state-format.md](02-state-format.md) — config/state layout, atomic writes, `.bak` rotation
- [dependency-policy.md](dependency-policy.md) — dependency currency standard
- [10-packaging.md](10-packaging.md) — artifact integrity, SHA256SUMS, signing status
- [../CLAUDE.md](../CLAUDE.md) — project rules (no secrets in config; docs-first)
