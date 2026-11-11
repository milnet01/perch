# Submission scripts

One-shot runbooks for pushing Perch to each downstream channel. Each
script assumes:

1. The v1.0.0 tag is live on `origin` (it is — `git describe` prints
   `v1.0.0`).
2. The platform-specific credential is already on this machine.
3. The required CLI tool is installed.

Each script prints its preconditions on `--help` and refuses to run
until they are met. No script pushes without explicit re-confirmation
when the action is hard to reverse (AUR first-push).

| Channel | Script | Platform auth | CLI tool |
|---|---|---|---|
| **openSUSE OBS** | `obs.sh` | `~/.config/osc/oscrc` with an openSUSE account | `osc` |
| **AUR (stable)** | `aur.sh perch` | SSH key registered with AUR account | `git` only |
| **AUR (-git)** | `aur.sh perch-git` | same | `git` only |
| **KDE Store** | `kde-store.md` | web submission — no CLI | — |

## Running order

OBS first (it builds the Fedora RPM as well as the openSUSE one), then
AUR (Arch), then KDE Store (on hold: its listing pointed at a Flathub
build). Perch is not on Flathub (user decision, 2026-11-11); the Flatpak
ships as a GitHub release file, built by `packaging/flathub/flatpak-build.sh`
(docs/10-packaging.md § Release mechanics).

```
./packaging/submit/obs.sh               # immediate; builds run on OBS
./packaging/submit/aur.sh perch         # immediate
./packaging/submit/aur.sh perch-git     # immediate
# packaging/submit/kde-store.md — walkthrough, no CLI
```

Each script is idempotent where the platform permits (AUR, OBS —
re-runs overwrite).
