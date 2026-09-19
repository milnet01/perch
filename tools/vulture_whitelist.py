"""Names vulture reports as unused that are used — its calibration (PERC-0061).

Pass this file alongside the tree:
    vulture src tools scripts tools/vulture_whitelist.py --min-confidence 60
and anything it still reports is new. Every entry below was checked on
2026-09-19 and falls in one of these groups:

* WindowBackend interface members (capabilities, desktop_count, …) that the
  core calls through the base class, so vulture cannot see the call.
* D-Bus methods and signals exported to, or proxied from, the compositor:
  called by name over the bus, never from Python.
* Qt virtual overrides (rowCount, headerData, moveRows, …): Qt calls them.
* MockBackend's `_` driver API and diagnostic counters, used by the tests.
* Strong references held on purpose so Qt or asyncio cannot collect the
  object (`_menu`, `_seed_task`, `_apply_task`, `_per_script`).
* Protocol constants kept as a complete set (EWMH / ICCCM values).
* Parameters a D-Bus signature requires and the body does not read.
* Lazy module `__getattr__` hooks.

Deliberately NOT here: config/edit.py's update_layout_entry,
reorder_layout_entries and rename_profile, which docs describe and the code
does not call — PERC-0051 decides which side is wrong — and
x11/geometry.py's frame-extent helpers, which may be the frame compensation
X11 placement is missing.
"""
# ruff: noqa: F821, B018
_._add_output  # unused method (src/perch/backend/mock.py:233)
_._apply_task  # unused attribute (src/perch/ui/dialog.py:597)
cache_dir  # unused function (src/perch/paths.py:51)
can_enumerate_windows  # unused variable (src/perch/backend/types.py:81)
can_observe_geometry  # unused variable (src/perch/backend/types.py:82)
can_observe_outputs  # unused variable (src/perch/backend/types.py:83)
can_preplace_windows  # unused variable (src/perch/backend/types.py:85)
_.capabilities  # unused property (src/perch/backend/base.py:97)
_._change_output  # unused method (src/perch/backend/mock.py:239)
_._change_window  # unused method (src/perch/backend/mock.py:194)
_._clear_fail_state  # unused method (src/perch/backend/mock.py:271)
_.columnCount  # unused method (src/perch/ui/dialog.py:1393)
_.CommandDone  # unused method (src/perch/backend/kwin/service.py:308)
_.commands_completed  # unused attribute (src/perch/backend/kwin/service.py:312)
commands_completed  # unused variable (src/perch/backend/kwin/service.py:72)
_.commands_dispatched  # unused attribute (src/perch/backend/kwin/service.py:161)
commands_dispatched  # unused variable (src/perch/backend/kwin/service.py:71)
_.commands_expired  # unused attribute (src/perch/backend/kwin/service.py:299)
commands_expired  # unused variable (src/perch/backend/kwin/service.py:73)
_.desktop_count  # unused method (src/perch/backend/base.py:148)
_._fail_state  # unused method (src/perch/backend/mock.py:259)
file_path  # unused variable (src/perch/backend/kwin/scripting.py:38)
_.fire  # unused method (src/perch/backend/kwin/hotkeys.py:178)
_._fire_hotkey  # unused method (src/perch/backend/mock.py:256)
_.foreign_calls  # unused attribute (src/perch/backend/kwin/service.py:207)
foreign_calls  # unused variable (src/perch/backend/kwin/service.py:74)
__getattr__  # unused function (src/perch/backend/hyprland/__init__.py:19)
_.headerData  # unused method (src/perch/ui/dialog.py:1400)
ICCCM_NORMAL_STATE  # unused variable (src/perch/backend/x11/ewmh.py:105)
ICCCM_WITHDRAWN_STATE  # unused variable (src/perch/backend/x11/ewmh.py:104)
_.is_any  # unused method (src/perch/core/rules.py:53)
_.list_shortcuts  # unused method (src/perch/backend/kwin/hotkeys.py:474)
loading  # unused variable (src/perch/backend/kwin/hotkeys.py:206)
_._menu  # unused attribute (src/perch/ui/tray.py:361)
_.moveRows  # unused method (src/perch/ui/rules_model.py:197)
_._move_window  # unused method (src/perch/backend/mock.py:201)
notes  # unused variable (src/perch/backend/types.py:86)
_.outputs_changed  # unused attribute (src/perch/backend/kwin/service.py:253)
outputs_changed  # unused variable (src/perch/backend/kwin/service.py:67)
_.OutputsChanged  # unused method (src/perch/backend/kwin/service.py:249)
_.pending_replies  # unused method (src/perch/backend/kwin/service.py:171)
_._per_script  # unused attribute (src/perch/backend/kwin/backend.py:162)
_.poll_ceiling_returns  # unused attribute (src/perch/backend/kwin/service.py:305)
poll_ceiling_returns  # unused variable (src/perch/backend/kwin/service.py:69)
_.PollCommand  # unused method (src/perch/backend/kwin/service.py:269)
_.poll_invalidated_returns  # unused attribute (src/perch/backend/kwin/service.py:302)
poll_invalidated_returns  # unused variable (src/perch/backend/kwin/service.py:70)
_.poll_requests  # unused attribute (src/perch/backend/kwin/service.py:273)
poll_requests  # unused variable (src/perch/backend/kwin/service.py:68)
PRESENCE_ALL  # unused variable (src/perch/backend/x11/ewmh.py:59)
_._remove_output  # unused method (src/perch/backend/mock.py:245)
request_json  # unused variable (src/perch/backend/mutter/backend.py:323)
_.rowCount  # unused method (src/perch/ui/dialog.py:1386)
_._script_id  # unused attribute (src/perch/backend/kwin/backend.py:163)
_.ScriptReady  # unused method (src/perch/backend/kwin/service.py:256)
_._seed_task  # unused attribute (src/perch/ui/dialog.py:448)
_._set_active_window  # unused method (src/perch/backend/mock.py:224)
_.set_capabilities  # unused method (src/perch/backend/mock.py:97)
_._set_desktop  # unused method (src/perch/backend/mock.py:251)
shortcuts  # unused variable (src/perch/backend/kwin/hotkeys.py:469)
SOURCE_APPLICATION  # unused variable (src/perch/backend/x11/ewmh.py:44)
SOURCE_UNSPECIFIED  # unused variable (src/perch/backend/x11/ewmh.py:43)
_._spawn_window  # unused method (src/perch/backend/mock.py:187)
_.started  # unused attribute (src/perch/backend/kwin/hotkeys.py:159)
started  # unused variable (src/perch/backend/kwin/hotkeys.py:154)
_.supportedDragActions  # unused method (src/perch/ui/rules_model.py:194)
_.supportedDropActions  # unused method (src/perch/ui/rules_model.py:191)
_.window_added  # unused attribute (src/perch/backend/kwin/service.py:217)
window_added  # unused variable (src/perch/backend/kwin/service.py:63)
_.WindowAdded  # unused method (src/perch/backend/kwin/service.py:213)
_.window_geometry_changed  # unused attribute (src/perch/backend/kwin/service.py:235)
window_geometry_changed  # unused variable (src/perch/backend/kwin/service.py:65)
_.WindowGeometryChanged  # unused method (src/perch/backend/kwin/service.py:231)
_.window_properties_changed  # unused attribute (src/perch/backend/kwin/service.py:244)
window_properties_changed  # unused variable (src/perch/backend/kwin/service.py:66)
_.WindowPropertiesChanged  # unused method (src/perch/backend/kwin/service.py:240)
_.window_removed  # unused attribute (src/perch/backend/kwin/service.py:226)
window_removed  # unused variable (src/perch/backend/kwin/service.py:64)
_.WindowRemoved  # unused method (src/perch/backend/kwin/service.py:222)
