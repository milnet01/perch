# Test-suite review — 2026-09-25

A dated record of the `review-tests` run for PERC-0063. It is a record,
not a description of the current code: each finding is as the lane
reported it against commit 4413d33. The roadmap items that close these
findings cite this file.

- Baseline: 962 passed, 0 failed, 16 skipped; 978 collected.
- Nine cold lanes, one per test area, every lane returned.
- The lane reports below are verbatim apart from dropped preamble.


---

## Chunk tests/backend (compliance, mock, select, stub decoders) — 8 files read (lane 1, review-tests 2026-09-25)

### Focus answer
Only mock is checked against its capability claims. All 16 baseline skips are 8 tests x 2 non-mock backends (skip lines test_compliance.py:101, 113, 125, 142, 158, 185, 198, 221). Each real backend runs 4 of 12 compliance tests (lifecycle, list_windows, list_outputs, unknown_window). sway/hyprland/mutter join the matrix only when their env is present; for them the chunk checks decoders plus constant capability flags, never the contract (coverage gap, retired dim 3, not filed).
Orchestrator check: `pytest tests/backend/test_compliance.py --collect-only` on this host collects [kwin] x12, [mock] x12, [x11] x12 (XDG_CURRENT_DESKTOP=KDE, XDG_SESSION_TYPE=wayland). The second real backend in the baseline was kwin.

### Findings

**[HIGH] [dim 9] tests/backend/conftest.py:74** (the matrix; via test_compliance.py:45 and the backend fixture at conftest.py:95)
> name: cls for name, cls in _ALL_BACKENDS.items() if cls.is_available()
Consequence: KWinBackend.is_available() is True whenever XDG_CURRENT_DESKTOP contains KDE and the session is Wayland (kwin/backend.py:187-195) — this project's dev desktop. The compliance tests then call KWinBackend().start() against the user's real session bus: acquire the service name, unload_script_if_loaded, install_and_run_script inside the user's live KWin, pick a hotkey provider (kwin/backend.py:217-248; source comment at :203-206 "a JS script loaded and running inside the user's KWin"). Nothing points the bus or XDG paths somewhere private; the kwin marker suite's private dbus + kwin_wayland --virtual is bypassed. Host-dependent: with an installed Perch running, start() probably raises BackendUnavailable and the fixture skips (conftest.py:102); otherwise it loads a script into the desktop compositor.
Fix: exclude kwin from the env-probed matrix unless the private-bus kwin harness supplies it.

**[MEDIUM] [dim 1] tests/backend/test_compliance.py:99** (same shape :111, :123, :183)
> if not backend.capabilities.can_set_position:
>     pytest.skip("backend does not claim can_set_position")
Consequence: line 100 already skips every non-mock backend, and MockBackend's defaults are all True (test_mock.py:190-205), so the capability gate can never evaluate False. The *_matches_capability tests only check the mock's set_geometry/set_state (duplicating test_mock.py). A real backend with a wrong capability flag is never caught on any host, though names and docstring ("Runs against every backend in BACKEND_CLASSES") say otherwise.
Fix: a per-backend window-spawn hook so these run on real backends, or move them to test_mock.py and stop counting them as compliance.

**[MEDIUM] [dim 1] tests/backend/test_compliance.py:69**
> windows = await backend.list_windows()  …  for w in windows:
Consequence: only mock is seeded (66-67). For x11 the run is a bare display with no WM and no client; if list_windows() returns [] the loop never runs and only isinstance(windows, list) remains. A decoder returning wrong types passes.
Fix: open one client before listing for real backends, or assert len(windows) >= 1 where seeded.

**[LOW] [dim 1] tests/backend/mutter/test_mutter_decoders.py:137**
> with pytest.raises(BackendError):
Consequence: UnknownWindow, UnknownOutput, BackendUnsupported all subclass BackendError (base.py:38-46); a regression mapping unmapped kinds to a subclass passes a test claiming the plain-BackendError fallback.
Fix: assert type(excinfo.value) is BackendError.

### Pre-pass verdicts (all setenv_call dim 6)
- hyprland/test_backend.py:19,22,25,30,37: mitigated — monkeypatch.setenv; _signature() reads os.environ fresh (hyprland/backend.py:100).
- hyprland/test_hyprland_decoders.py:137: mitigated — monkeypatch; shutil.which patch at :141/:144 via monkeypatch.setattr.
- mutter/test_mutter_decoders.py:142,145,146,151,152: mitigated — monkeypatch.setenv.
- sway/test_sway_decoders.py:160,165: mitigated — monkeypatch; :158 delenv(raising=False).
- test_select.py:37,38,45,46: mitigated — monkeypatch; autouse _scrub_env at :21 clears every variable select() reads (grepped os.environ across src/perch/backend).

### Dimensions scanned
- 1: 3 findings · 4: clean · 5: none · 6: none · 7: N/A · 8: none (the unreachable skip is filed under 1) · 9: 1 finding · 11: none · 12: none (slowest 0.72s) · 14: none (conftest.py:56 except Exception: return could drop a backend from the matrix, but test_select.py:13-18 imports every backend module directly) · 15: N/A

### Noted, not mine
- src/perch/backend/mutter/backend.py:445: {"ok": False} with no error kind returns silently, treated as success. review-code.
- conftest.py:8 docstring ("still exercising each backend end-to-end in CI hosts that do") is contradicted by the unconditional mock-only skips.

### Possibly wider
- Other tests building KWinBackend() from select() or an env probe outside the private-bus harness would reach the live KWin the same way. Not looked.

### Open questions
- (Answered by orchestrator above: kwin was the second backend.)
- F3: what does X11Backend.list_windows() return in the compliance run? Run test_list_windows_returns_frozen_dataclasses[x11] printing len(windows).
- F1: with an installed Perch running, does _bus_setup(SERVICE_NAME) fail before unload_script_if_loaded can unload that instance's script?
- F1: where does install_and_run_script write the script file by default, given the compliance fixture does not use xdg_env? (kwin/install.py:76)

---

## Chunk backend/kwin — 9 files read (lane 2, review-tests 2026-09-25)

### Findings

**[HIGH] [dim 1] tests/backend/kwin/test_bundled_script.py:157** (body to :167)
> def test_bundled_script_shipped_in_wheel(tmp_path: Path) -> None:
Consequence: docstring says it guards against a pyproject.toml rewrite dropping the JS tree from the wheel, but CI and local_CI.sh install -e '.[dev]' (local_CI.sh:166), so BUNDLED_SCRIPT_DIR is the source tree; the test passes after exactly that regression. No wheel built/inspected, tmp_path unused; repeats test_bundled_script_dir_exists_inside_package.
Fix: build the wheel into tmp_path and assert the .js/metadata.json entries are in its zip listing, or delete and point at the packaging job that inspects the artifact.

**[HIGH] [dim 1] tests/backend/kwin/test_install.py:94** (assert at :102)
> mtime_before = first.stat().st_mtime_ns
Consequence: install.py:148 copies with shutil.copy2, which preserves source mtime; a second ensure_installed() that needlessly re-copies leaves the same st_mtime_ns. Passes whether or not idempotent; second == first only compares paths.
Fix: monkeypatch the copy helper / shutil.copy2 in the install module and assert not called on the second invocation.

**[MEDIUM] [dim 1] tests/backend/kwin/test_live_kwin.py:91**
> assert len(wins) < 10
Consequence: named ..._is_empty_on_fresh_virtual_kwin; docstring says internal placeholders are excluded by main.js normalWindow filter (main.js:301). A regression letting up to 9 internal windows through passes.
Fix: assert wins == [] (or every returned window is a known placeholder).

**[MEDIUM] [dim 1] tests/backend/kwin/test_backend.py:204** (assert at :227)
> async def test_stop_invalidates_polls_before_unloading(
Consequence: the name claims an ordering; the assertion only proves invalidation happened somewhere in stop(). Unload-then-invalidate passes. Same gap at :165 (defensive unload "before our load" asserted only as assert_awaited_once(), no ordering against _mock_run_script).
Fix: _mock_unload_script side_effect records whether invalidation had already happened when unload was called; assert on the record.

**[MEDIUM] [dim 5] tests/backend/kwin/test_backend.py:144** (also :204 and :691 test_on_outputs_changed_reconciles_added_changed_removed)
> async def test_start_emits_backend_connected_and_loads_script(
Consequence: these pass no hotkey_provider and, unlike the started_backend fixture (:251), don't set PERCH_HOTKEY_PROVIDER=mock, so _start() calls the real choose_provider(): off-Flatpak, KGlobalAccelProvider.start() -> real KGlobalAccelProxy.new_proxy("org.kde.kglobalaccel") + signal pump on sdbus's default bus = the user's live session bus. With PERCH_HOTKEY_PROVIDER=portal exported, a real portal CreateSession; failure raises BackendUnavailable. The file's autouse fixture (:40) exists to keep unit tests off the real bus. (Unchecked assumption: sdbus opens the default bus lazily.)
Fix: monkeypatch PERCH_HOTKEY_PROVIDER=mock or pass hotkey_provider=MockHotkeyProvider(), as started_backend does.

**[MEDIUM] [dim 5] tests/backend/kwin/test_backend.py:168**
> async def test_start_raises_backend_unavailable_if_script_never_ready(
Consequence: the only start-path test not using _ready_service, so the real PerchKWin1.export() runs export_to_dbus(OBJECT_PATH) on the default bus. With no session bus, export raises before the ScriptReady wait; start() re-wraps as BackendUnavailable("KWin backend failed to start: ..."), so match="ScriptReady" fails. Passes only with an ambient bus, and there exports onto the user's live session connection.
Fix: stub export as _ready_service does, without setting script_ready.

**[MEDIUM] [dim 8] tests/backend/kwin/test_bus_name.py:21**
> if not _have_tools():
>     pytest.skip("dbus-daemon not installed")
Consequence: _have_tools() (conftest.py:28) requires both dbus-daemon and kwin_wayland; these tests need only dbus-daemon. With dbus-daemon and no KWin the two PERC-0049 regression tests are skipped and the reason misreports the cause.
Fix: gate on shutil.which("dbus-daemon") alone.

**[LOW] [dim 5] tests/backend/kwin/conftest.py:54** (filed against the dependent tests; lane notes a conftest is context, not a subject — orchestrator may drop)
> ch = r.read(1)
> if not ch:
>     time.sleep(0.02)
Consequence: read(1) blocks until data or EOF; "" only at EOF (daemon exited). After the daemon dies it spins the full 10 s then raises RuntimeError (test error, not skip). A daemon that stays up without printing its address hangs private_bus / virtual_kwin_session forever (deadline checked only between characters). Affects 2 test_bus_name.py + 5 test_live_kwin.py tests.
Fix: select/poll the fd with the remaining deadline; stop at EOF.

**[LOW] [dim 1] tests/backend/kwin/test_bundled_script.py:97** (same at :77)
> assert f'"{op}"' in main_js, f"script dispatcher is missing op: {op}"
Consequence: checks the quoted string appears anywhere in main.js, not that a case exists; a removed case whose string survives in a comment passes. Today each op occurs once as a case label (main.js:192-199).
Fix: match case "<op>": with a regex.

### Pre-pass verdicts
Sleeps: conftest.py:56 confirmed (LOW above); conftest.py:88 false positive (bounded 15 s readiness poll); test_backend.py:224 false positive (one sleep(0), FIFO, deterministic); test_backend.py:901, :908 false positive (drain by tick count, mocks never suspend); test_hotkeys.py:586 false positive (first_delay_s=0.0, 20 yields for 2 needed); test_live_kwin.py:185, :193 false positive (bounded polls in gated kwin test); test_service.py:96,129,150,172,196,206,247 false positive (single yields); test_service.py:221 false positive, yield is load-bearing; test_service.py:146 false positive (negative window; fails only on a >=5 s stall).
Env: every setenv_call is monkeypatch (test_backend.py:55,56,63,71,72,251; test_bus_name.py:24; test_hotkeys.py:185,467,550; test_install.py:24,39,48,63,65,233,242; test_live_kwin.py:45-47). The one direct os.environ write (conftest.py:76) is restored in finally.

### Dimensions scanned
- 5: 3 findings · 1: 5 findings (mocked-bus tests do assert on backend results; set_geometry/set_state/close_window assert the command sent, where the wire format is the contract) · 14: clean (conftest.py:86 except Exception: pass is inside a readiness poll; no test asserts on a `triggered` connection) · 4: clean · 6: none in chunk · 7: clean · 8: 1 finding · 9: no production endpoints (live bus under 5) · 11: clean · 12: clean (1.33 s is a gated live test) · 15: N/A

### Noted, not mine
- None.

### Possibly wider
- _wait_for_kwin (conftest.py:78), _default_bus_setup and test_bus_name's fixture call sdbus set_default_bus(...) process-wide and never restore; after their daemons die the default bus points at a dead connection for later tests using an sdbus proxy without setting a bus.
- Other backend test modules building a real backend without pinning PERCH_HOTKEY_PROVIDER reach the ambient bus the same way.

### Open questions
- Does the CI runner have kwin_wayland on PATH? If not, the two test_bus_name.py tests never run in CI.
- Confirm the :168 finding by running it with DBUS_SESSION_BUS_ADDRESS unset and no user bus (env -i).
- Both ambient-bus findings rest on sdbus opening a default bus lazily (documented; source not read).

---

## Chunk x11-backend — 8 files read (lane 3, review-tests 2026-09-25)

### Findings

**[HIGH] [dim 5] tests/backend/x11/test_live_openbox.py:124** (same at :166, :171)
> await _pump_until(lambda: False, duration_s=0.5)
Consequence: the condition can never be true, so this is a fixed 0.5s sleep; the asserts after it (info.geometry.x, info.state is FULLSCREEN / NORMAL) run once whatever openbox's state. On a loaded runner openbox may not have processed _NET_MOVERESIZE_WINDOW / _NET_WM_STATE in 0.5s. Same race PERC-0071 fixed for the open wait; these three were never converted.
Fix: pass a real predicate with a generous ceiling (geometry within tolerance / state is FULLSCREEN, via sync read or a flag from geometry_changed / state_changed). Use time.monotonic() in the helper.

**[MEDIUM] [dim 1] tests/backend/x11/test_geometry.py:78** (to :85)
> _out("DP-1", 0, 0, 1920, 1080, primary=True),
Consequence: the primary output is also first; on a tie monitor_for_geometry keeps first-seen unless the later is primary (geometry.py:93-98), so the test passes with the primary clause deleted. test_monitor_for_geometry_tie_breaks_on_primary does not test the tie-break.
Fix: put the primary second (HDMI-1 primary, after DP-1), assert "HDMI-1".

**[MEDIUM] [dim 1] tests/backend/x11/test_identity.py:282**
> assert got.monitor == "DP-1"  # primary fallback
Consequence: in _OUTPUTS DP-1 is both primary and first connected; _primary_name (identity.py:248-256) falls back to first connected, so it passes with the is_primary check removed.
Fix: an output list where the primary is not first.

**[MEDIUM] [dim 1] tests/backend/x11/test_outputs.py:87**
> assert got[0].work_area == Geometry(0, 0, 0, 0)
Consequence: the disconnected output has geometry (0,0,0,0); removing the not o.is_connected skip in apply_workarea (outputs.py:148) makes _intersect return a = (0,0,0,0) again. Identical either way.
Fix: give the disconnected output a stale non-zero work_area differing from its intersection, assert unchanged.

**[MEDIUM] [dim 1] tests/backend/x11/test_outputs.py:45**
> assert 130_000 <= got <= 135_000
Consequence: the contract is exact, round(dot_clock*1000/(h_total*v_total)) (outputs.py:40) = 132375. Whole-Hz truncation (132000) or floor passes. The only other non-zero case (:39) is exactly 60.000 Hz. mHz precision unverified.
Fix: assert got == 132375.

**[MEDIUM] [dim 6] tests/backend/x11/test_live_openbox.py:86**
> assert await b.desktop_count() == 4
Consequence: the fixture starts openbox with env = {**os.environ, "DISPLAY": display} (conftest.py:104), i.e. the developer's real HOME / XDG_CONFIG_HOME; openbox loads the user's own rc.xml. A developer with a different desktop count fails; openbox may write into real ~/.cache.
Fix: point HOME / XDG_CONFIG_HOME / XDG_CACHE_HOME at tmp_path, or --config-file with a checked-in rc.xml.

**[LOW] [dim 6] tests/backend/x11/test_live_openbox.py:89** (same shape :143, :182, :217, :260, :276, :312)
> await b.stop()
Consequence: stop() is not in a finally; on an assert failure, or pytest.skip("xclock required") at :292 after b.start(), the backend is never stopped; its X connection / QSocketNotifier stay on the session qapp and can emit backend_disconnected or warn inside a later test. Failure path only.
Fix: try/finally, or a fixture that yields a started backend and stops it on teardown.

**[LOW] [dim 5] tests/backend/x11/test_live_openbox.py:109** (same env :157, :198, :290)
> env = {"DISPLAY": openbox_display, "PATH": "/usr/bin:/bin"}
Consequence: the skip gate uses shutil.which("xclock") on the real PATH (:61) but Popen resolves against the hard-coded PATH; xclock outside /usr/bin:/bin errors FileNotFoundError instead of skipping.
Fix: launch shutil.which("xclock") by absolute path, or inherit os.environ["PATH"].

**[LOW] [dim 1] tests/backend/x11/test_backend_skeleton.py:324**
> win.send_event.assert_called_once()
Consequence: claims "sends the ICCCM message" but any single send_event passes; payload (build_close_message) and event_mask=0, propagate=False (backend.py:527-528) unchecked.
Fix: stub build_close_message to a sentinel, assert_called_once_with(sentinel, event_mask=0, propagate=False).

### Pre-pass verdicts
- sleep test_live_openbox.py:55: false positive at that line — asyncio.sleep(0.05) is the poll interval of a condition wait. The defect is the callers at :124/:166/:171 passing lambda: False (the HIGH).

### Dimensions scanned
- 1: 5 findings (fake-display tests mostly assert on what X receives; exceptions above) · 4: clean · 5: 2 findings (open/close waits are real polls; post-command waits are races) · 6: 2 findings · 7: nothing (time.time only as wait deadline) · 8: clean · 9: N/A · 11: clean · 12: 1 measured offender, test_set_state_toggles_fullscreen_and_back 1.14s from the two fixed 0.5s pumps; folded into the dim 5 fix · 14: clean · 15: N/A

### Noted, not mine
- None.

### Possibly wider
- Other live suites (e.g. kwin-marked) may use the same _pump_until(lambda: False, ...) fixed-wait idiom. Not read.

### Open questions
- Does openbox here read $XDG_CONFIG_HOME/openbox/rc.xml under the fixture env? Confirm by pointing XDG_CONFIG_HOME at an rc.xml with <number>2</number> and watching :86 fail.
- The post-command race needs a loaded-CPU run (e.g. stress-ng alongside pytest -m x11 --count=50).

---

## Chunk core-1 — 10 files read (lane 4, review-tests 2026-09-25)

### Findings

**[MEDIUM] [dim 1] tests/core/test_engine_performance.py:157** (test starts line 123)
> assert elapsed < 0.5, (
Claim (docstring): the exclusion path is O(1) regardless of rule-list size; the 0.5s budget is "tighter than the full-walk budget". Baseline has the 1000x1000 full walk at 0.24s (~500k rule checks, ~0.5µs each, lane's inference). A linear regression (500 docks x 500 non-matching rules = ~250k checks, ~0.12s) stays under 0.5s.
Consequence: the regression the test exists to catch leaves it green; it fails only at ~4x the full-walk cost.
Fix: time the 500-matching-window walk in the same test and assert the dock loop is a small fraction of it (ratio), or assert structurally that match_window is never called for a dock.

**[LOW] [dim 1] tests/core/test_exclusions.py:71**
> [{"app_id": "plasmashell"}, {"app_id": "firefox"}]
Consequence: the matching pattern is first; an is_user_excluded that checked only patterns[0] passes test_is_user_excluded_matches_any.
Fix: put the non-matching pattern first.

**[LOW] [dim 1] tests/core/test_exclusions.py:55**
> assert len(patterns) == 2
> assert patterns[0].app_id == "plasmashell"
Consequence: the second pattern {"wm_class": "Plasma*", "type": "splash"} is only counted; a parser dropping wm_class or type passes.
Fix: also assert patterns[1].wm_class and patterns[1].types.

**[LOW] [dim 1] tests/core/test_actions.py:77**
> assert a.geometry.w_pct == pytest.approx(0.6)
Consequence: neither percent test (lines 69-87) checks x_pct/y_pct, and every input gives them "0%"; a parser ignoring or swapping x/y passes. parsers_defensive and layouts percent tests don't check them either.
Fix: non-zero distinct x/y percentages, assert all four fields (or compare the whole PercentGeometry).

**[LOW] [dim 1] tests/core/test_layouts.py:57**
> assert entries[1].apply.geometry == PresetGeometry(name="maximize")
Consequence: entry 1's entry-level "monitor": "HDMI-1" (line 46) is never asserted; a parser dropping it passes.
Fix: add assert entries[1].apply.monitor == "HDMI-1".

### Pre-pass verdicts
- setenv_call tests/conftest.py:33,34,35: false positive — monkeypatch.setenv in function-scoped xdg_env fixture, undone at teardown. The module-level QT_QPA_PLATFORM setdefault (line 21) is deliberate and documented.

### Dimensions scanned
- 1: 5 findings · 4: clean (orchestrator count) · 5: clean (budgets ~40x headroom; test_matching.py:212 < 1.0 vs 0.05s timeout ~20x; no sleeps/network; flake risk judged low, inferred not measured) · 6: clean in chunk · 7: clean · 8: clean · 9: clean · 11: clean · 12: clean (slowest 0.24s) · 14: clean · 15: N/A

### Noted, not mine
- test_engine_performance.py module docstring (lines 16-19) says every window "walks the full rules list once"; _make_rules spreads matches so the average walk is half the list (its own docstring line 55 says "most of"). Doc inaccuracy in the test.

### Possibly wider
- test_matching.py:204 calls matching._warn_timed_out.cache_clear() before but not after; the module-level lru_cache keeps "(a|aa)+$" for the session. Another test expecting a timeout warning for the same pattern without clearing first would get none. Not checked.

### Open questions
- The MEDIUM estimate is extrapolated from one timing. Confirm: temporarily move is_builtin_excluded after the rules loop in evaluate, run test_evaluate_short_circuits_on_builtin_exclusion, see whether it stays green.

(Lane noted: Ants MCP verbs were unavailable in its session; used Read/Grep.)

---

## Chunk core/reducer-resolver-rules-snaps-state — 5 files read (lane 5, review-tests 2026-09-25)

### Findings

**[HIGH] [dim 1] tests/core/test_reducer.py:341** (test_set_geometry_echo_is_dropped, to 369)
> assert store.state.windows["app:firefox"].last_seen == ts_before
Consequence: last_seen comes from _utc_now_iso(), second precision (state_store.py:378-380). If the echo is not dropped, _remember re-records the same geometry with the same last_seen whenever both writes land in the same second — nearly always. A regression that stops consuming echoes passes on almost every run; fails only across a second boundary (also dim 7).
Fix: monkeypatch perch.core.state_store._utc_now_iso with a strictly advancing fake, or observe the echo another way (is_dirty() after a flush).

**[HIGH] [dim 1] tests/core/test_reducer.py:388** (test_window_closed_clears_expected_geometry, to 411)
> reducer.handle_geometry_changed("w1", Geometry(1, 2, 3, 4), "DP-1", 0)
Consequence: the test ends on this call with no assertion; its comment claims the late event "is ignored because the WindowInfo cache is gone". If handle_window_closed stopped popping _windows, the late event would overwrite the stored geometry and the test still passes.
Fix: assert store.state.windows["app:firefox"].geometry still equals Geometry(0, 0, 2560, 1400).

**[MEDIUM] [dim 1] tests/core/test_state_store.py:93** (test_load_future_version_rejected, to 106)
> "schema_version": CURRENT_STATE_SCHEMA_VERSION + 1,
> "windows": {},
> assert store.state.windows == {}
Consequence: the future-version file already has empty windows, so the assertion holds whether it is refused or loaded.
Fix: put a window record in it and assert it is absent, or assert the read-only latch's effect.

**[MEDIUM] [dim 1] tests/core/test_reducer.py:517** (test_maximized_true_calls_set_state, to 527)
> names = backend.commands.names()
> assert "set_geometry" in names
Consequence: names/order only; the set_geometry arguments are never checked, so a move to the wrong monitor passes. The success-path move to HDMI-1 is unverified (only the failure path at :848 checks the target).
Fix: assert the set_geometry monitor is "HDMI-1" and geometry is HDMI-1's work area.

**[MEDIUM] [dim 1] tests/core/test_resolver.py:137** (test_absolute_geometry_clamped_to_work_area, to 153)
> assert geom.x + geom.w <= 2560
> assert geom.y + geom.h <= 1400
Consequence: only right/bottom bounded; x = -5000 or w/h shrunk to 0 passes.
Fix: assert the exact geometry, or all four bounds plus w/h preserved.

**[MEDIUM] [dim 1] tests/core/test_resolver.py:357** (test_percent_geometry_is_clamped_into_the_work_area, to 378)
> assert placement.geometry.x >= work_area.x
> assert placement.geometry.y >= work_area.y
Consequence: only left/top checked; past right/bottom or collapsed w/h passes.
Fix: assert the exact clamped geometry, or all four edges.

**[MEDIUM] [dim 1] tests/core/test_state_store.py:172** (test_flush_rotates_old_to_bak, to 187)
> assert bak.exists()
Consequence: claims the OLD file rotates to .bak; a rotation copying the new document passes.
Fix: parse .bak, assert app:a geometry x is 0 (the first flush's value).

**[LOW] [dim 1] tests/core/test_state_store.py:151** (test_flush_writes_atomically)
> raw = json.loads(state_path.read_text())
Consequence: name claims atomicity; only content is checked; a plain write_text passes.
Fix: patch os.replace / the temp-file step and assert it is used, or rename to what it verifies.

**[LOW] [dim 1] tests/core/test_reducer.py:1016** (test_set_config_applies_a_new_rule_to_the_next_window)
> assert _placed(backend) == ["w1"]
Consequence: the id discriminates rule-applied-or-not (only reachable placement source), but not that the new rule's geometry (left-half DP-1 = Geometry(0, 0, 1280, 1400)) was used.
Fix: assert the full set_geometry tuple.
The other PERC-0075 tests hold up: :1019 exclusion (paired with :1005 as positive control); :1035 (set_config is synchronous, schedules nothing, reducer.py:424-443); :1047 (identity check); :1061.

**[LOW] [dim 1] tests/core/test_reducer.py:765** (test_profile_override_with_no_matching_base_is_appended)
> assert geom_calls[0][0] == "sig"
Consequence: the appended override says maximize on HDMI-1; wrong geometry/monitor passes.
Fix: assert monitor and geometry, as :712-713 does for the replace case.

**[LOW] [dim 1] tests/core/test_reducer.py:922** (test_a_lone_window_event_does_not_notify)
> outside one logs, and must not queue a notification for the next pass."""
Consequence: no next pass is run; the reset at reducer.py:326 (self._skipped_entries = []) could be removed unnoticed.
Fix: run a second activate_layout("coding") after the lone event, assert the pass reports exactly its own skipped entry, once.

**[LOW] [dim 1] tests/core/test_resolver.py:299** (test_desktop_current)
> assert placement.desktop == 0
Consequence: _w() sits on desktop 0, so a resolver returning constant 0 for "current" passes (real path resolver.py:256-257 returns window.desktop).
Fix: build the window on desktop 3, assert 3.

### Pre-pass verdicts
- datetime_now test_state_store.py:25: false positive — _RECENT only feeds last_seen fixture values inside the 90-day window; retention tests (:322, :338) pass an explicit now=.

### Dimensions scanned
- 1: 12 findings (2 HIGH, 5 MEDIUM, 5 LOW) · 6: none (module-level dicts read-only through validate top level; per-test MockBackend/StateStore under tmp_path; resolver outputs fixture function-scoped) · 7: 1 (the :341 wall-clock dependence, filed under 1) · 4: clean · 5: none (debounce 0.0) · 8: none · 9: N/A · 11: none (:388 filed as dim 1) · 12: N/A · 14: none · 15: N/A

### Noted, not mine
- None.

### Possibly wider
- Any test outside this chunk proving "not recorded" by comparing last_seen before/after has the same second-precision defeat.

### Open questions
- Most reducer tests end with a pending StateStore._debounced_flush task (mark_dirty -> loop.create_task, 5 s sleep); handle_output_removed ones also leave a topology task; reducer.stop() never called. Whether loop teardown cancels them cleanly or warns "Task was destroyed but it is pending" needs a run with -W error::RuntimeWarning / PYTHONASYNCIODEBUG=1 on test_reducer.py.

---

## Chunk app_startup … hardening — 8 files read (lane 6, review-tests 2026-09-25)

### Findings

**[HIGH] [dim 5] tests/test_autostart.py:256** (to :265)
> autostart.portal_set_autostart(
>     True,
>     factory=lambda: _ExplodingPortal(),
>     sender=_FakePortal().sender,
> )
Consequence: no subscriber passed; portal.call_with_response uses default_subscriber before invoke, which runs get_default_bus().match_signal_async(...) on sdbus's process-global default bus — a match rule on the host's real session bus. Result depends on the machine.
Fix: pass subscriber=_FakePortal().subscribe, as every other portal test does via fake.seams().

**[MEDIUM] [dim 1] tests/test_autostart.py:256** (same call; assertion `is False` at :264)
> assert (
>     asyncio.run(
Consequence: portal_set_autostart wraps call_with_response in except Exception: return False, covering the subscribe step. Where default_subscriber raises (no session bus, sdbus missing), it returns False before _ExplodingPortal.request_background is reached; the test passes without exercising "a failing portal call must not crash" and cannot tell the cases apart.
Fix: inject a fake subscriber so the only exception on the path is the portal call's own.

**[MEDIUM] [dim 1] tests/test_autostart.py:144**
> if Path("/.flatpak-info").is_file():
>     pytest.skip("running inside a Flatpak sandbox")
> assert not autostart.is_flatpak()
Consequence: paths.is_flatpak is exactly return Path("/.flatpak-info").is_file(); guard and implementation are the same expression and the True branch is never driven. A regression to return False passes everywhere.
Fix: monkeypatch the marker probe (tmp_path file), assert both True and False.

**[MEDIUM] [dim 1] tests/test_cli.py:60**
> exit_code = entry.cli(["--check-config"])
> assert exit_code == 0
Consequence: "falls back to backup" asserted only through the exit code; a loader regression that re-seeds defaults over an unparsable primary also exits 0. Only test_config_loader.py:28 (theme == "light") catches it.
Fix: assert the backup's value was used (config.toml not overwritten with defaults, or the parsed theme).

**[LOW] [dim 1] tests/test_autostart.py:61**
> # No exception, still exactly one file with the expected content.
> assert autostart.xdg_is_enabled()
Consequence: only that a non-hidden entry exists; a leftover .desktop.tmp or altered content passes.
Fix: assert the directory listing is exactly the one basename and content equals the first write.

**[LOW] [dim 1] tests/test_config_atomic_write.py:16**
> # Tmp and bak must not linger after a clean write.
> assert not target.with_suffix(target.suffix + ".tmp").exists()
Consequence: only .tmp checked; a spurious .bak on first write passes.
Fix: also assert no .bak.

**[LOW] [dim 1] tests/test_cli.py:49**
> exit_code = entry.cli(["--check-config"])
> assert exit_code == 1
Consequence: docstring (:8-9) says it "exits non-zero and logs a pinpoint error"; only exit code asserted.
Fix: capsys; assert the stderr line names the config path.

### Pre-pass verdicts
- setenv_call test_autostart.py:26,38,45,58,68,78,88,104,112,121,131: false positive (monkeypatch; per-test tmp_path; autostart_dir() re-reads env each call, autostart.py:63).

### Dimensions scanned
- 1: 6 findings (written-vs-parsed question: _seed_defaults returns validate(_parse(path)); round-trip tests compare bytes on disk; no config test reads real ~/.config) · 4: clean · 5: 1 finding (0.01s portal timeout at :322 is not a race) · 6: nothing tied to a named collision · 7: nothing · 8: nothing (skip at :145 has reason and live condition) · 9: N/A · 11: nothing · 12: nothing (slowest 0.13s) · 14: nothing beyond :256 · 15: N/A

### Noted, not mine
- None.

### Possibly wider
- test_app_startup.py:85 runs the real perch_app.main() against the session-scoped QApplication and leaves setQuitOnLastWindowClosed(False), installed translators, apply_theme state, an aboutToQuit connection to an Event from a closed loop, and a shown TrayIcon. Later tests relying on QApplication defaults or untranslated strings depend on order.
- The sdbus default bus opened at test_autostart.py:256 is process-global.
- cli() calls configure_logging() every invocation (test_cli.py runs it four times); handlers may pile up. Not opened.

### Open questions
- test_portal_swallows_exceptions: which branch returns False on the baseline machine? Needs a caplog run.
- test_backend_is_stopped_when_startup_fails_after_it_started: does tray.show() under offscreen register a StatusNotifierItem on the host session bus? Needs dbus-monitor.

---

## Chunk tests/test_hostenv.py … test_translations.py — 8 files read (lane 7, review-tests 2026-09-25)

### Findings

**[MEDIUM] [dim 6] tests/test_logging_setup.py:16** (all five tests in the file; also tests/test_instance.py:60 and :103 via cli())
> logger = configure_logging(log_path=log_path)
Consequence: configure_logging changes the process-wide perch logger (handlers, root.propagate = False, DEBUG in test_perch_debug_env_sets_level) and nothing restores it; old handlers are removed without close(), leaking file handles. Via cli(), the two CLI tests in test_instance.py also call install_qt_bridge() (__main__.py:86) — a process-wide Qt message handler — and bind a StreamHandler(sys.stderr) while capsys has swapped sys.stderr. Later tests see a non-propagating perch logger, so caplog captures nothing from perch.* (order-dependent); after capsys teardown a later record writes to a closed stream ("--- Logging error ---", not run to confirm); the last test's log file keeps receiving records.
Fix: a fixture saving the perch logger's handlers/level/propagate, closing and restoring on teardown; stub install_qt_bridge in the CLI tests, as perch.app.main already is.

**[MEDIUM] [dim 5] tests/test_instance.py:72**
> assert channel.listen()
Consequence: the real socket is at tmp_path/perch.sock, ~73 chars under pytest's default basetemp against a ~107 limit. A temp dir ~34 chars longer than /tmp (long TMPDIR, --basetemp, long username) makes listen() return False every time; the bare assert hides channel.error_string(), so it reads as a product bug. (Known trap, at that strength.)
Fix: XDG_RUNTIME_DIR at a short tempfile.mkdtemp(dir="/tmp") cleaned in teardown; put channel.error_string() in the assert message.

**[MEDIUM] [dim 1] tests/test_instance.py:102**
> monkeypatch.setattr(instance, "request_settings", lambda: True)
Consequence: test_cli_settings_hands_off_to_the_running_copy never checks the handoff happened; the stub records no call. cli(["--settings"]) returning 0 without calling request_settings passes.
Fix: the stub appends to a list; assert called exactly once.

**[MEDIUM] [dim 5] tests/test_instance.py:101**
> monkeypatch.setattr(instance, "acquire_instance_lock", lambda: None)
Consequence: unlike the sibling at :59, this does not stub perch.app.main (whose comment says "Without the guard cli() runs the whole app; fail fast instead of hanging"). A regression taking cli past the lock check runs the real app loop and the suite hangs (no pytest-timeout).
Fix: stub perch.app.main with the same _must_not_run raiser.

**[LOW] [dim 1] tests/test_logging_setup.py:29**
> # Exactly one file handler + one stream handler, not doubled.
> assert sum(isinstance(h, RotatingFileHandler) for h in logger.handlers) == 1
Consequence: only file handlers are counted; two console handlers (every line printed twice) passes.
Fix: assert len(logger.handlers) == 2 (RotatingFileHandler is itself a StreamHandler, so an isinstance count won't work).

### Pre-pass verdicts
- test_hostenv.py:21,26,27,36,37,45,46,53,54,65: false positive (monkeypatch; host_environment() writes os.environ directly at hostenv.py:59-68 but monkeypatch saved and restores LD_LIBRARY_PATH).
- test_install_gnome_extension.py:35,49,60: false positive.
- test_instance.py:20,33,40,70,85: false positive (separate tmp_path per test).
- test_logging_setup.py:52: false positive for env leakage; the DEBUG level it causes persists (part of the dim 6 finding).
- test_paths.py:13: false positive.

### Dimensions scanned
- 1: 2 findings · 4: clean · 5: 2 findings (no sleeps; waitUntil used deliberately at :76) · 6: 1 finding (lock/socket files per-test tmp_path; CLI tests stub acquire_instance_lock so the real $XDG_RUNTIME_DIR/perch.lock is never touched) · 7: clean · 8: N/A · 9: clean · 11: clean · 12: N/A · 14: clean (test_hostenv.py:58 except RuntimeError: pass catches the deliberate raise, not the assertion) · 15: N/A

### Noted, not mine
- configure_logging (logging_setup.py:37-38) removes old handlers without closing them — leaks file handles in production if called more than once. review-code.

### Possibly wider
- Other tests calling cli() or configure_logging() probably leak the same logger state.
- xdg_env does not redirect XDG_RUNTIME_DIR; a test calling the real acquire_instance_lock() or InstanceChannel.listen() with only xdg_env would use the real user's perch.lock / perch.sock and collide with a running Perch.

### Open questions
- Confirm the dim 6 consequence: a caplog test on perch.foo after test_logging_setup.py, fixed order, captures nothing?
- Socket-path finding: run test_instance.py with a ~70+ char --basetemp and confirm listen() returns False.

---

## Chunk tests/ui (part A) — 8 files read (lane 8, review-tests 2026-09-25)

### Findings

**[HIGH] [dim 1] tests/ui/test_import_export_pane.py:82** (to :100)
> from perch.config.loader import _load_and_validate
> with pytest.raises(SchemaError):
>     _load_and_validate(bad_source)
> assert page._pending_import_path is None
Consequence: never touches the page; checks a loader function _on_import does not call (it uses validate_text, dialog.py:2322). The final assert checks the page's untouched starting value. If _on_import staged invalid files, this passes.
Fix: stub QFileDialog.getOpenFileName -> bad.toml and a recording QMessageBox.critical (as test_import_of_a_non_utf8_file_is_refused_not_raised does); call page._on_import(); assert the "Invalid TOML" message and nothing staged.

**[HIGH] [dim 1] tests/ui/test_import_export_pane.py:103** (to :134)
> page.confirm_import_button.setEnabled(True)
> page.cancel_import_button.setEnabled(True)
> assert page.confirm_import_button.isEnabled() is True
Consequence: computes the diff itself with difflib, writes page state by hand, asserts a button it just enabled is enabled. _on_import's diff rendering and staging (dialog.py:2338-2373) never run.
Fix: stub getOpenFileName -> new.toml, call page._on_import(), assert diff_view.toPlainText(), _pending_import_text and button state.

**[MEDIUM] [dim 1 / dim 14] tests/ui/test_dialog.py:312** (to :322)
> monkeypatch.setattr(QMessageBox, "critical", lambda *a, **kw: None)
> assert dialog.result() == 0
Consequence: name claims "document clean" but the rollback (dialog.py:2720) is never asserted; the stubbed critical records nothing, so a path that swallowed the error silently passes; result() == 0 is the default.
Fix: record-and-assert-one-call stub; keep a reference to dialog._state.document before _on_ok, assert same object afterwards still holding start_at_login = true.

**[MEDIUM] [dim 1] tests/ui/test_layouts_pane.py:151** (to :170)
> # Simulate rename of "coding" → "dev".
> page._layouts = rebuilt
> page._renames["coding"] = "dev"
Consequence: re-implements _on_rename_layout (dialog.py:1119-1172) inline, copying its rebuild loop; the rename-tracking logic (a past bug site) and list refresh are not exercised.
Fix: stub QInputDialog.getText -> ("dev", True), call page._on_rename_layout().

**[MEDIUM] [dim 1] tests/ui/test_layouts_pane.py:129** (to :135)
> # Delete "media" without the confirm-dialog blocking.
> del page._layouts["media"]
> del page._renames["media"]
> page._dirty = True
Consequence: _on_delete_layout (dialog.py:1174-1198) never runs — confirm check, _renames clean-up, list update, dirty flag.
Fix: stub QMessageBox.question -> Yes, select "media", call page._on_delete_layout().

**[MEDIUM] [dim 1] tests/ui/test_layouts_pane.py:114**
> page.commit()
> saved_text = tomlkit.dumps(dialog._state.document)
Consequence: named "persists to toml"; all three layouts commit tests (:114, :135, :165) assert on the in-memory document after page.commit(); none goes through _commit_and_save, so the dirty flag reaching a save and the written file are never checked (test_dialog.py does check disk for General, Rules, Hotkeys, Exclusions).
Fix: call dialog._on_ok() and read the config path back, as test_general_page_persists_toggles_on_ok does.

**[MEDIUM] [dim 1] tests/ui/test_config_edit.py:271** (to :276)
> update_layout_entry(doc, "coding", 0, _entry("neovim", "left-half"))
> assert "neovim" in out
> assert "left-half" in out
Consequence: "replaces at index" but nothing checks the original (app_id = "code") is gone; an append passes.
Fix: assert '"code"' absent, or coding.windows has one entry with app_id neovim.

**[MEDIUM] [dim 1] tests/ui/test_config_edit.py:297** (to :302)
> reorder_layout_entries(doc, "coding", [2, 0, 1])
> assert first_after < first_code
Consequence: only "konsole before code"; [2, 1, 0] also passes.
Fix: assert the full app_id order equals ["konsole", "code", "firefox"].

**[MEDIUM] [dim 1] tests/ui/test_config_edit.py:327**
> assert "primary" in out
Consequence: the fixture already contains monitor = "primary" (commented_config.toml:37); passes if add_layout_entry dropped the new entry's monitor.
Fix: assert the last item of coding.windows has monitor == "primary".

**[LOW] [dim 1] tests/ui/test_config_edit.py:267**
> assert "firefox" in out
Consequence: the fixture's rule already carries app_id = "firefox" (commented_config.toml:29); cannot fail; neither assert checks the entry landed in coding.
Fix: assert on the last item of doc["layouts"]["coding"]["windows"].

**[LOW] [dim 1] tests/ui/test_config_edit.py:48** (to :65)
> apply_general(
>     doc,
>     start_at_login=False,
>     restore_on_open=False,
>     notify_on_restore=True,
Consequence: restore_on_open and notify_on_restore change but are never asserted.
Fix: parse the output, assert all four values.

**[LOW] [dim 1] tests/ui/test_dialog.py:93**
> assert len(texts) == len(SECTION_ORDER)
Consequence: compared with the source's own constant; dropping a section passes. Comment promises "Eight sections in the spec'd order"; only four labels checked.
Fix: assert texts equals the documented list, in order.

### Pre-pass verdicts
- None supplied.

### Dimensions scanned
- 1: 12 findings · 6: clean (monkeypatch-only patches; qtbot.addWidget; tmp_path/xdg_env; Path("/tmp/x.toml") at import_export:173 never written; conftest.py:17 setdefault deliberate) · 14: 1 (merged into test_dialog.py:312; other stubs record-and-assert or stand in for modals not under test; fake_save writes the same text as write_document minus the atomic step) · 4: clean · 5: clean (waitSignal calls at geometry_editor:76, 86 and key_capture:56 are the context-manager form, not the trap) · 7: N/A · 8: N/A · 9: N/A · 11: clean · 12: clean (slowest 0.20s) · 15: N/A

### Noted, not mine
- None.

### Possibly wider
- Other tests/ui page tests (profiles, rules editor) may write private fields and call page.commit() instead of driving the handler through a stubbed modal.

### Open questions
- None.

---

## Chunk tests/ui (links … windows_pane) — 11 files read (lane 9, review-tests 2026-09-25)

### Findings

**[MEDIUM] [dim 6] tests/ui/test_theming.py:137** (to :148)
> apply_theme(app, "dark")
> assert app.style().objectName().lower() == "fusion"
Consequence: perch.ui.theming keeps module globals _platform_style and _overridden; nothing resets them, and this test restores neither palette nor style, so the session QApplication is left in Fusion/dark with _overridden=True for every later file. :61 and :75 restore the palette in finally but not _overridden. In-file order dependence: :107 fails if run after :137; :123's platform snapshot is the dark palette if run after :137; :89 (..._with_unknown_scheme_is_noop) actually exercises the restore path in file order.
Fix: autouse fixture monkeypatching theming._platform_style / _overridden and snapshotting/restoring style name and palette.

**[MEDIUM] [dim 1] tests/ui/test_tray_icon_states.py:139** (to :177; same shape test_status_bridge.py:175)
> return TrayIcons(normal=QIcon(), warning=QIcon(), error=QIcon())
Consequence: docstring says icons are "distinct enough to is-compare", but all three are identical null icons and no test compares an icon; the swap tests (:155, :167, status_bridge :175) assert only tray.toolTip(). A wrong icon, or _update_icon (tray.py:364) never called, passes.
Fix: three distinguishable icons; assert tray.icon().cacheKey() matches the expected member.

**[MEDIUM] [dim 1] tests/ui/test_onboarding.py:209**
> def test_show_config_dialog_only_on_finish(
Consequence: only the rejected path; asserts show_config_dialog is False, which also passes if hard-coded False or unwired.
Fix: parametrise on accepted; assert show_config_dialog is accepted with the box ticked.

**[MEDIUM] [dim 1] tests/ui/test_profiles_pane.py:161** (to :166; same :181-189)
> # Simulate delete bypassing the confirmation dialog.
> page._deleted_originals.append(0)
> del page._profiles[0]
> del page._origin[0]
> page._dirty = True
Consequence: rebuilds the delete handler's internals by hand; real delete regressions pass. test_add_profile_then_commit_appends_aot_entry has the same problem for add.
Fix: monkeypatch QMessageBox.question -> Yes and call the page's own delete and add handlers.

**[LOW] [dim 1] tests/ui/test_profiles_pane.py:95** (also :110-111)
> page.name_edit.setText("Mobile")
> page._on_name_edited()
Consequence: the slot is called by hand, so the line edit -> handler connection is untested.
Fix: qtbot.keyClicks, or emit the signal the page connects (e.g. textEdited).

**[LOW] [dim 1] tests/ui/test_tray.py:404**
> tray._on_activated(QSystemTrayIcon.ActivationReason.MiddleClick)
Consequence: private slot called directly; a dropped activated connect passes.
Fix: tray.activated.emit(...MiddleClick).

**[LOW] [dim 6] tests/ui/test_status_bridge.py:151**
> target_logger.setLevel(_logging.WARNING)
Consequence: the level on the real perch.ui.status logger is never restored; stays WARNING for the session. (The adjacent patch("perch.ui.status.log", target_logger) swaps in the same object and does nothing.)
Fix: save/restore the level in finally, or caplog.at_level(..., logger="perch.ui.status").

### Pre-pass verdicts
- setenv_call test_sni_probe.py:47,48,56,57,64,65,72,73: false positive (monkeypatch; :80-81 delenv).
- setenv_call test_tray_icon_states.py:126: false positive (monkeypatch; sys.prefix and _dev_icon_dir patches at :127-131 monkeypatched too).

### Dimensions scanned
- 1: 5 findings (tray menu tests do assert on the intent emitted via real QAction triggers; structure assertions are pinned to docs/08) · 4: clean · 5: none (waitSignal context-manager form; assertNotEmitted(wait=100) bounded) · 6: 2 findings · 7: N/A · 8: N/A · 9: none (sni_probe injects probes; onboarding passes have_host/gnome; links assert the OpenUrl intent; nothing calls QDesktopServices) · 11: none · 12: clean (slowest 0.11s) · 14: none (test_status_bridge.py:228 replaces sys.excepthook with its own capture and asserts it empty) · 15: N/A

### Noted, not mine
- None.

### Possibly wider
- Other tests reaching perch.ui.theming.apply_theme (e.g. a ConfigDialog Apply path) inherit and mutate the theming globals and the session QApplication style/palette.
- Other ui tests may set private page state by hand or call private _on_* slots.

### Open questions
- test_tray_icon_states.py:192 and :93: _load calls QIcon.fromTheme(name, fallback) first (icons.py:98-108) without isolating the host icon theme; with a system-installed perch-tray-symbolic, :192 would log no warning and fail, :93 would pass with a bundled SVG missing. Check with QIcon.setThemeSearchPaths([...]). Fix if confirmed: monkeypatch QIcon.fromTheme to return its fallback.
- test_status_bridge.py:212: relies on PySide6 sending slot exceptions from a direct emit() to sys.excepthook; confirm with a deliberately raising slot.
- test_windows_pane.py:257: StateStore left dirty with a debounced flush pending; if a QTimer, it could fire during a later test and write to this test's tmp_path.
- Lane note: workspace_search returned 0 matches for apply_theme under tests/ though test_theming.py contains it; Grep was correct.
