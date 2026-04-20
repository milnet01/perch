// Perch — KWin in-process bridge.
//
// Runs inside KWin (Plasma 6). Subscribes to workspace.* signals and reports
// them to the Perch Python process over D-Bus. Listens on a long-poll callback
// chain against PollCommand so Python can push commands into the JS context
// with one D-Bus round-trip of latency and zero wakeups while idle.
//
// JSON strings end-to-end: KWin bug 486024 makes typed variadic callDBus
// marshalling unreliable for numeric signatures (i / u). Every arg in and
// out is "s".
//
// Authoritative docs: docs/05-backend-kwin.md. Version in metadata.json
// must match the value the Python side pins.

const SVC = "io.github.milnet01.Perch";
const OBJ = "/KWin";
const IF  = "io.github.milnet01.Perch.KWin1";

const GEOMETRY_DEBOUNCE_MS = 50;

// ── Identity / serialisation ───────────────────────────────────────────────

function winId(w) {
    return w && w.internalId ? w.internalId.toString() : "";
}

function outputName(output) {
    // KWin::Output — exposes .name (QString).
    if (!output) return "";
    return output.name || "";
}

function windowTypeString(w) {
    // WindowType enum is numeric; map to the strings Perch expects.
    // Values: 0=Normal, 1=Desktop, 2=Dock, 3=Toolbar, 4=Menu, 5=Dialog,
    //         6=Override, 7=TopMenu, 8=Utility, 9=Splash, 10+=others.
    switch (w.windowType) {
        case 0: return "normal";
        case 1: return "desktop";
        case 2: return "dock";
        case 3: return "toolbar";
        case 4: return "menu";
        case 5: return "dialog";
        case 7: return "menu";
        case 8: return "utility";
        case 9: return "splash";
        default: return "unknown";
    }
}

function windowStateString(w) {
    if (w.fullScreen) return "fullscreen";
    if (w.minimized) return "minimized";
    // maximizeMode: 0=restore, 1=vertical, 2=horizontal, 3=full.
    if (w.maximizeMode === 3) return "maximized";
    return "normal";
}

function describeWindow(w) {
    var g = w.frameGeometry;
    return {
        id: winId(w),
        app_id: w.resourceName || "",
        wm_class: w.resourceClass || "",
        title: w.caption || "",
        pid: (typeof w.pid === "number") ? w.pid : 0,
        type: windowTypeString(w),
        state: windowStateString(w),
        x: g ? g.x : 0,
        y: g ? g.y : 0,
        w: g ? g.width : 0,
        h: g ? g.height : 0,
        output: outputName(w.output),
        desktop: (w.desktops && w.desktops.length > 0) ? (w.desktops[0].x11DesktopNumber - 1) : -1,
        role: w.windowRole || ""
    };
}

function describeOutput(output) {
    var g = output.geometry;
    return {
        name: output.name || "",
        x: g ? g.x : 0,
        y: g ? g.y : 0,
        w: g ? g.width : 0,
        h: g ? g.height : 0,
        scale: (typeof output.scale === "number") ? output.scale : 1.0,
        refresh_mhz: (typeof output.refreshRate === "number") ? Math.round(output.refreshRate * 1000) : 0
    };
}

// ── Outbound notifications ─────────────────────────────────────────────────

function emitWindowAdded(w) {
    if (!w) return;
    // Withhold until resourceName / resourceClass is non-empty — some apps
    // (Java Swing, a handful of Electron builds) set WM_CLASS a tick after map.
    if (!w.resourceName && !w.resourceClass) {
        // Retry once after 1 s; if it's still empty, fire with empty app_id
        // and let Perch fall back to title-based identity.
        const retry = setInterval(function () {
            clearInterval(retry);
            callDBus(SVC, OBJ, IF, "WindowAdded", JSON.stringify(describeWindow(w)));
        }, 1000);
        return;
    }
    callDBus(SVC, OBJ, IF, "WindowAdded", JSON.stringify(describeWindow(w)));
}

function emitWindowRemoved(w) {
    if (!w) return;
    callDBus(SVC, OBJ, IF, "WindowRemoved", JSON.stringify({ id: winId(w) }));
}

// frameGeometryChanged fires on every pixel of a user drag; debounce so the
// D-Bus wire sees one notification per ~50 ms burst.
const _geomTimers = {};
function emitWindowGeometryChanged(w) {
    if (!w) return;
    const id = winId(w);
    if (!id) return;
    if (_geomTimers[id]) {
        // Reset the timer instead of queueing another call.
        _geomTimers[id].stop();
    }
    const timer = new QTimer();
    timer.interval = GEOMETRY_DEBOUNCE_MS;
    timer.singleShot = true;
    timer.triggered.connect(function () {
        delete _geomTimers[id];
        const payload = JSON.stringify(describeWindow(w));
        callDBus(SVC, OBJ, IF, "WindowGeometryChanged", payload);
    });
    timer.start();
    _geomTimers[id] = timer;
}

function emitWindowPropertiesChanged(w) {
    if (!w) return;
    callDBus(SVC, OBJ, IF, "WindowPropertiesChanged", JSON.stringify(describeWindow(w)));
}

function emitOutputsChanged() {
    callDBus(SVC, OBJ, IF, "OutputsChanged", "");
}

// ── Command dispatcher ─────────────────────────────────────────────────────

function findWindow(id) {
    const all = workspace.windowList();
    for (var i = 0; i < all.length; i++) {
        if (winId(all[i]) === id) return all[i];
    }
    return null;
}

function findOutput(name) {
    const screens = workspace.screens;
    if (!screens) return null;
    for (var i = 0; i < screens.length; i++) {
        if (screens[i].name === name) return screens[i];
    }
    return null;
}

function runBatch(ops) {
    // Apply every op in-tick so the result lands in a single compositor frame.
    const results = [];
    for (var i = 0; i < ops.length; i++) {
        results.push(runOne(ops[i]));
    }
    return results;
}

function runOne(op) {
    if (!op || typeof op.op !== "string") {
        return { ok: false, error: "missing op" };
    }
    try {
        switch (op.op) {
            case "setFrameGeometry":        return doSetFrameGeometry(op);
            case "setFullScreen":           return doSetFullScreen(op);
            case "setMinimized":            return doSetMinimized(op);
            case "setMaximizeMode":         return doSetMaximizeMode(op);
            case "closeWindow":             return doCloseWindow(op);
            case "queryWindows":            return doQueryWindows();
            case "queryOutputs":            return doQueryOutputs();
            case "queryCurrentDesktop":     return doQueryCurrentDesktop();
            case "queryDesktopCount":       return doQueryDesktopCount();
            case "queryWindow":             return doQueryWindow(op);
            case "setDesktop":              return doSetDesktop(op);
            default:                        return { ok: false, error: "unknown op: " + op.op };
        }
    } catch (e) {
        return { ok: false, error: "exception: " + (e && e.message ? e.message : e) };
    }
}

function doSetFrameGeometry(op) {
    const w = findWindow(op.id);
    if (!w) return { ok: false, error: "unknown_window", id: op.id };
    if (op.output) {
        const s = findOutput(op.output);
        if (!s) return { ok: false, error: "unknown_output", output: op.output };
        // Move to the target output first so frameGeometry is applied in the
        // correct coordinate space. workspace.sendClientToOutput (Plasma 6).
        if (typeof workspace.sendClientToScreen === "function") {
            workspace.sendClientToScreen(w, s);
        } else if (typeof w.output !== "undefined") {
            w.output = s;
        }
    }
    w.frameGeometry = Qt.rect(op.x | 0, op.y | 0, op.w | 0, op.h | 0);
    if (op.preplace) {
        // Best-effort: stack predictably during first-frame placement, then
        // clear once the window has had one repaint to settle.
        w.keepAbove = true;
        const release = new QTimer();
        release.interval = 120;
        release.singleShot = true;
        release.triggered.connect(function () { w.keepAbove = false; });
        release.start();
    }
    return { ok: true };
}

function doSetFullScreen(op) {
    const w = findWindow(op.id);
    if (!w) return { ok: false, error: "unknown_window", id: op.id };
    w.fullScreen = !!op.value;
    return { ok: true };
}

function doSetMinimized(op) {
    const w = findWindow(op.id);
    if (!w) return { ok: false, error: "unknown_window", id: op.id };
    w.minimized = !!op.value;
    return { ok: true };
}

function doSetMaximizeMode(op) {
    const w = findWindow(op.id);
    if (!w) return { ok: false, error: "unknown_window", id: op.id };
    // setMaximize(vertical:bool, horizontal:bool) — Plasma 6.
    const v = !!op.vertical;
    const h = !!op.horizontal;
    if (typeof w.setMaximize === "function") {
        w.setMaximize(v, h);
    } else {
        // Defensive fallback; should never fire on Plasma 6.
        w.maximizeMode = (v && h) ? 3 : (v ? 1 : (h ? 2 : 0));
    }
    return { ok: true };
}

function doCloseWindow(op) {
    const w = findWindow(op.id);
    if (!w) return { ok: false, error: "unknown_window", id: op.id };
    w.closeWindow();
    return { ok: true };
}

function doSetDesktop(op) {
    const w = findWindow(op.id);
    if (!w) return { ok: false, error: "unknown_window", id: op.id };
    const target = (op.desktop | 0);
    if (target < 0) {
        // -1 = sticky / all desktops.
        w.onAllDesktops = true;
        return { ok: true };
    }
    w.onAllDesktops = false;
    const desktops = workspace.desktops;
    if (!desktops || target >= desktops.length) {
        return { ok: false, error: "unknown_desktop", desktop: target };
    }
    w.desktops = [desktops[target]];
    return { ok: true };
}

function doQueryWindows() {
    const all = workspace.windowList();
    const out = [];
    for (var i = 0; i < all.length; i++) {
        if (all[i].normalWindow) {
            out.push(describeWindow(all[i]));
        }
    }
    return { ok: true, windows: out };
}

function doQueryOutputs() {
    const screens = workspace.screens || [];
    const out = [];
    for (var i = 0; i < screens.length; i++) {
        out.push(describeOutput(screens[i]));
    }
    return { ok: true, outputs: out };
}

function doQueryCurrentDesktop() {
    const cur = workspace.currentDesktop;
    // currentDesktop is a VirtualDesktop object in Plasma 6; x11DesktopNumber is 1-based.
    const idx = (cur && typeof cur.x11DesktopNumber === "number")
        ? (cur.x11DesktopNumber - 1)
        : 0;
    return { ok: true, desktop: idx };
}

function doQueryDesktopCount() {
    const desktops = workspace.desktops;
    return { ok: true, count: desktops ? desktops.length : 1 };
}

function doQueryWindow(op) {
    const w = findWindow(op.id);
    if (!w) return { ok: false, error: "unknown_window", id: op.id };
    return { ok: true, window: describeWindow(w) };
}

// ── Long-poll loop ─────────────────────────────────────────────────────────

function poll() {
    callDBus(SVC, OBJ, IF, "PollCommand", function (reply) {
        try {
            const cmd = JSON.parse(reply);
            if (cmd && cmd.nop) {
                // Heartbeat ceiling or invalidation — just re-arm.
            } else if (cmd && typeof cmd.seq === "number") {
                var result;
                if (cmd.batch && cmd.batch.length) {
                    result = { ok: true, batch: runBatch(cmd.batch) };
                } else if (typeof cmd.op === "string") {
                    result = runOne(cmd);
                } else {
                    result = { ok: false, error: "malformed command" };
                }
                callDBus(SVC, OBJ, IF, "CommandDone",
                    JSON.stringify({ seq: cmd.seq, result: result }));
            }
        } catch (e) {
            // Drop malformed replies and re-arm; Python will retry.
        }
        poll();
    });
}

// ── Subscriptions ──────────────────────────────────────────────────────────

workspace.windowAdded.connect(function (w) {
    emitWindowAdded(w);
    if (w) {
        // Wire per-window signals the first time we see this window.
        if (w.frameGeometryChanged) w.frameGeometryChanged.connect(function () { emitWindowGeometryChanged(w); });
        if (w.captionChanged)       w.captionChanged.connect(function ()       { emitWindowPropertiesChanged(w); });
        if (w.fullScreenChanged)    w.fullScreenChanged.connect(function ()    { emitWindowPropertiesChanged(w); });
        if (w.minimizedChanged)     w.minimizedChanged.connect(function ()     { emitWindowPropertiesChanged(w); });
        if (w.maximizedChanged)     w.maximizedChanged.connect(function ()     { emitWindowPropertiesChanged(w); });
        if (w.desktopsChanged)      w.desktopsChanged.connect(function ()      { emitWindowPropertiesChanged(w); });
        if (w.outputChanged)        w.outputChanged.connect(function ()        { emitWindowGeometryChanged(w); });
    }
});
workspace.windowRemoved.connect(emitWindowRemoved);
workspace.screensChanged.connect(emitOutputsChanged);
if (workspace.currentDesktopChanged) {
    workspace.currentDesktopChanged.connect(emitOutputsChanged);
}

// Also wire the windows that already exist when the script loads.
(function wireExisting() {
    const all = workspace.windowList();
    for (var i = 0; i < all.length; i++) {
        const w = all[i];
        if (!w) continue;
        if (w.frameGeometryChanged) w.frameGeometryChanged.connect(function () { emitWindowGeometryChanged(w); });
        if (w.captionChanged)       w.captionChanged.connect(function ()       { emitWindowPropertiesChanged(w); });
        if (w.fullScreenChanged)    w.fullScreenChanged.connect(function ()    { emitWindowPropertiesChanged(w); });
        if (w.minimizedChanged)     w.minimizedChanged.connect(function ()     { emitWindowPropertiesChanged(w); });
        if (w.maximizedChanged)     w.maximizedChanged.connect(function ()     { emitWindowPropertiesChanged(w); });
        if (w.desktopsChanged)      w.desktopsChanged.connect(function ()      { emitWindowPropertiesChanged(w); });
        if (w.outputChanged)        w.outputChanged.connect(function ()        { emitWindowGeometryChanged(w); });
    }
})();

poll();
callDBus(SVC, OBJ, IF, "ScriptReady", JSON.stringify({ version: "1.0.0" }));
