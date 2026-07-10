# Security Policy

Perch is a single-user Linux desktop application — it runs in your own session
with your own privileges, needs no root, and makes no network connections (see
[`docs/security-standards.md`](docs/security-standards.md) for the full posture).
Even so, we take security reports seriously.

## Supported versions

Security fixes land on the latest release line. Perch follows SemVer; only the
most recent **1.x** release is supported.

| Version | Supported |
|---|---|
| Latest 1.x release | ✅ |
| Anything older | ❌ |

## Reporting a vulnerability

**Please do not open a public issue for a security problem.** Instead, use
GitHub's private vulnerability reporting:

1. Go to <https://github.com/milnet01/perch/security/advisories>.
2. Click **Report a vulnerability**.
3. Describe the issue, the affected version, and steps to reproduce.

This keeps the report private until a fix is available. If private reporting is
unavailable to you, open a normal issue that says only *"security report — please
enable private reporting"* (no details) and we will follow up.

## What to expect

- **Acknowledgement** within about a week.
- An assessment of whether it is a genuine vulnerability and its severity.
- A fix on the supported release line, credited to you unless you prefer to
  remain anonymous.

Perch is a volunteer-run project with no bug-bounty program, but your report is
genuinely appreciated.

## Scope

In scope: anything that lets another local user or a malicious window/config
influence Perch beyond its intended single-user behaviour — e.g. code execution
from a crafted `config.toml`, or a window/compositor message escaping Perch's
trust boundary. Out of scope: issues that require an already-compromised session
(Perch runs at the user's own privilege by design and cannot defend against a
user who is already root or controls the session bus).
