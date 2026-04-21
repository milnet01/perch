# Submission scripts

One-shot runbooks for pushing Perch to each downstream channel. Each
script assumes:

1. The v1.0.0 tag is live on `origin` (it is — `git describe` prints
   `v1.0.0`).
2. The platform-specific credential is already on this machine.
3. The required CLI tool is installed.

Each script prints its preconditions on `--help` and refuses to run
until they are met. No script pushes without explicit re-confirmation
when the action is hard to reverse (Flathub PR, AUR first-push).

| Channel | Script | Platform auth | CLI tool |
|---|---|---|---|
| **Flathub** | `flathub.sh` | GitHub token on `gh` (have it) | `flatpak-builder`, `flatpak-pip-generator` |
| **openSUSE OBS** | `obs.sh` | `~/.oscrc` with openSUSE account | `osc` |
| **Fedora COPR** | `copr.sh` | `~/.config/copr` API token | `copr-cli` |
| **AUR (stable)** | `aur.sh perch` | SSH key registered with AUR account | `git` only |
| **AUR (-git)** | `aur.sh perch-git` | same | `git` only |
| **KDE Store** | `kde-store.md` | web submission — no CLI | — |

## Running order

Flathub is the primary cross-distro channel — prioritise it. Then
OBS + COPR (RPM distros), then AUR (Arch), then KDE Store (after the
Flathub build is public so the listing can point at it).

```
./packaging/submit/flathub.sh           # ~2h for Flathub review to start
./packaging/submit/obs.sh               # immediate; builds run on OBS
./packaging/submit/copr.sh              # immediate; builds run on COPR
./packaging/submit/aur.sh perch         # immediate
./packaging/submit/aur.sh perch-git     # immediate
# packaging/submit/kde-store.md — walkthrough, no CLI
```

Each script is idempotent where the platform permits (AUR, OBS,
COPR — re-runs overwrite). Flathub is a fork-and-PR flow; re-running
pushes a new commit to the same fork branch, which Flathub reviewers
see as an update to the pending PR.
