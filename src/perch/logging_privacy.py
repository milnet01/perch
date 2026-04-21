"""Privacy helpers for log-redaction (M7.e).

Window titles routinely leak sensitive data — "Passwords — KeePass",
"Email from <address>", "~/finances/taxes.ods". Perch writes its log to
``$XDG_STATE_HOME/perch/perch.log`` in plain text that the user (or
their distro's crash-report collector) may upload to a bug tracker. The
log is therefore a privacy surface, and we redact window-title-bearing
fields before they ever hit the log.

Rules:

* INFO-level messages **never** embed a window title or its
  near-equivalents (``name``, ``title``, ``caption``). Counts, app_ids,
  and geometry coordinates are fine.
* DEBUG-level messages may reference :class:`WindowInfo` by ``id`` or
  by the computed ``identity`` (``app:<app_id>`` form), never by title.
* Raw backend payloads (dicts / strings pulled straight from KWin's
  ``WindowAdded`` callback or Hyprland's ``socket2`` stream) go through
  :func:`redact_payload` before ``%r`` formatting.

``perch --debug`` raises the log level but does **not** relax these
rules; the redactions are applied unconditionally.
"""

from __future__ import annotations

from typing import Any

# Keys in KWin / Hyprland / Mutter payloads that carry user-visible window
# text. Conservative superset across all backends to keep callers simple.
_REDACTED_KEYS: frozenset[str] = frozenset(
    {
        "title",
        "name",
        "caption",
        "class",           # Hyprland's app class — low risk, but included
        "initialClass",    # Hyprland
        "initialTitle",    # Hyprland
        "window_class",    # i3ipc / Sway
    }
)

# What a redacted field shows in the log so readers can still see the
# *shape* of the problem even though the value is scrubbed.
_REDACTED_MARKER = "<redacted>"


def redact_payload(payload: Any) -> Any:
    """Return a copy of ``payload`` with title-bearing fields redacted.

    * ``dict`` inputs get a shallow copy with redacted keys replaced by
      the ``<redacted>`` marker; nested dicts / lists recurse.
    * ``list`` / ``tuple`` inputs recurse element-wise.
    * Scalars pass through unchanged.

    The function is total (never raises on exotic input); a caller that
    passes ``None`` or an opaque object gets it back verbatim. Use for
    ``log.debug("%r", redact_payload(...))`` sites where the payload is
    an untrusted backend event.
    """
    if isinstance(payload, dict):
        return {
            k: (
                _REDACTED_MARKER
                if k in _REDACTED_KEYS and payload.get(k) not in (None, "")
                else redact_payload(v)
            )
            for k, v in payload.items()
        }
    if isinstance(payload, list):
        return [redact_payload(v) for v in payload]
    if isinstance(payload, tuple):
        return tuple(redact_payload(v) for v in payload)
    return payload


def summarize_keys(payload: Any) -> str:
    """Return a safe one-line summary of a backend payload.

    Used when the full structured payload is too noisy even after
    redaction — e.g. the malformed-entry path that only needs to tell
    the user *what kind* of thing failed, not *which* window. Returns
    the sorted keys of a dict, ``"<list of N>"`` for a list, or the
    type name for scalars.
    """
    if isinstance(payload, dict):
        return "keys=" + ",".join(sorted(str(k) for k in payload))
    if isinstance(payload, list):
        return f"<list of {len(payload)}>"
    if isinstance(payload, tuple):
        return f"<tuple of {len(payload)}>"
    return f"<{type(payload).__name__}>"
