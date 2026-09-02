/*
 * Perch — GNOME Shell extension bridge.
 *
 * Authoritative design: docs/06-backend-stubs.md §Mutter / GNOME Shell.
 *
 * Responsibilities:
 *   - Export io.github.milnet01.Perch.Mutter1 on the session bus.
 *   - Enumerate windows + outputs, translating Mutter's shape into the
 *     JSON envelope that perch.backend.mutter._decode_window / _decode_output
 *     consume.
 *   - Implement set_geometry / set_state / close_window via
 *     Meta.Window.move_resize_frame and friends, honouring the
 *     unmaximize-then-move dance documented in docs/06.
 *   - Register hotkeys via Main.wm.addKeybinding.
 *
 * This file is a minimal scaffold. GNOME Shell extension APIs break every
 * major release; the bundled source of truth for wire-level compatibility
 * lives under per-GNOME-version git branches (see STATUS.md).
 */

import GLib from 'gi://GLib';
import Gio from 'gi://Gio';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

const BUS_NAME = 'io.github.milnet01.Perch.Mutter';
const OBJECT_PATH = '/Mutter';
const INTERFACE_NAME = 'io.github.milnet01.Perch.Mutter1';

// JSON reply envelope: success or typed error.
const OK = () => JSON.stringify({ok: true});
const ERR = (kind, message) => JSON.stringify({ok: false, error: kind, message});

// The service is on the session bus, so any peer at the same UID can call
// it -- including a Flatpak holding --socket=session-bus. Geometry fields
// therefore arrive untrusted and are checked before they reach Mutter,
// rather than being handed to move_resize_frame as whatever JSON.parse
// produced. A non-finite or absurd value is a caller error, not a window
// to place somewhere impossible.
const COORD_LIMIT = 1000000;

function isCoord(value) {
    return Number.isInteger(value) && Math.abs(value) <= COORD_LIMIT;
}

function isExtent(value) {
    return Number.isInteger(value) && value > 0 && value <= COORD_LIMIT;
}

const INTERFACE_XML = `
<node>
  <interface name="${INTERFACE_NAME}">
    <method name="ping">
      <arg type="s" direction="out"/>
    </method>
    <method name="list_windows">
      <arg type="s" direction="out"/>
    </method>
    <method name="get_window">
      <arg type="s" direction="in" name="wid"/>
      <arg type="s" direction="out"/>
    </method>
    <method name="list_outputs">
      <arg type="s" direction="out"/>
    </method>
    <method name="current_workspace">
      <arg type="i" direction="out"/>
    </method>
    <method name="workspace_count">
      <arg type="i" direction="out"/>
    </method>
    <method name="set_geometry">
      <arg type="s" direction="in" name="request_json"/>
      <arg type="s" direction="out"/>
    </method>
    <method name="set_state">
      <arg type="s" direction="in" name="wid"/>
      <arg type="s" direction="in" name="state"/>
      <arg type="s" direction="out"/>
    </method>
    <method name="close_window">
      <arg type="s" direction="in" name="wid"/>
      <arg type="s" direction="out"/>
    </method>
    <method name="register_hotkey">
      <arg type="s" direction="in" name="callback_id"/>
      <arg type="s" direction="in" name="accel"/>
      <arg type="s" direction="out"/>
    </method>
    <method name="unregister_hotkey">
      <arg type="s" direction="in" name="callback_id"/>
    </method>
    <signal name="HotkeyFired">
      <arg type="s" name="callback_id"/>
    </signal>
  </interface>
</node>`;


class PerchMutterService {
    constructor() {
        this._dbus = Gio.DBusExportedObject.wrapJSObject(INTERFACE_XML, this);
        this._busId = 0;
        this._hotkeys = new Map();  // callback_id -> gnome-shell action id
    }

    export() {
        this._dbus.export(Gio.DBus.session, OBJECT_PATH);
        this._busId = Gio.bus_own_name(
            Gio.BusType.SESSION,
            BUS_NAME,
            Gio.BusNameOwnerFlags.NONE,
            null,
            null,
            () => log('Perch: lost session bus name')
        );
    }

    unexport() {
        for (const [callback_id] of this._hotkeys)
            this.unregister_hotkey(callback_id);
        this._dbus.unexport();
        if (this._busId) {
            Gio.bus_unown_name(this._busId);
            this._busId = 0;
        }
    }

    // ── Meta helpers ────────────────────────────────────────────────────

    _windowById(wid) {
        for (const w of global.display.list_all_windows())
            if (String(w.get_id()) === wid) return w;
        return null;
    }

    _describeWindow(w) {
        const rect = w.get_frame_rect();
        const monitorIndex = w.get_monitor();
        const monitor = global.display.get_monitor_geometry(monitorIndex);
        const outputs = Meta.MonitorManager.get().get_logical_monitors();
        const mname = outputs[monitorIndex]?.get_monitors()?.[0]?.get_display_name?.()
                   ?? `Monitor-${monitorIndex}`;
        return {
            id: String(w.get_id()),
            app_id: String(w.get_wm_class_instance() || '').toLowerCase(),
            wm_class: w.get_wm_class() || '',
            title: w.get_title() || '',
            pid: w.get_pid() || null,
            type: this._typeString(w.get_window_type()),
            state: this._stateString(w),
            x: rect.x, y: rect.y, w: rect.width, h: rect.height,
            monitor: mname,
            desktop: w.get_workspace()?.index() ?? 0,
        };
    }

    _typeString(metaType) {
        switch (metaType) {
            case Meta.WindowType.DIALOG:  return 'dialog';
            case Meta.WindowType.MODAL_DIALOG: return 'dialog';
            case Meta.WindowType.SPLASHSCREEN: return 'splash';
            case Meta.WindowType.UTILITY: return 'utility';
            case Meta.WindowType.TOOLBAR: return 'toolbar';
            case Meta.WindowType.MENU:    return 'menu';
            case Meta.WindowType.DOCK:    return 'dock';
            case Meta.WindowType.DESKTOP: return 'desktop';
            default:                      return 'normal';
        }
    }

    _stateString(w) {
        if (w.is_fullscreen()) return 'fullscreen';
        if (w.minimized)       return 'minimized';
        if (w.get_maximized() === Meta.MaximizeFlags.BOTH) return 'maximized';
        return 'normal';
    }

    _describeMonitor(index) {
        const geom = global.display.get_monitor_geometry(index);
        const work = global.display.get_workspace_manager()
                          .get_active_workspace()
                          .get_work_area_for_monitor(index);
        const primaryIndex = global.display.get_primary_monitor();
        const outputs = Meta.MonitorManager.get().get_logical_monitors();
        const mname = outputs[index]?.get_monitors()?.[0]?.get_display_name?.()
                   ?? `Monitor-${index}`;
        return {
            name: mname,
            x: geom.x, y: geom.y, w: geom.width, h: geom.height,
            work_area: {x: work.x, y: work.y, w: work.width, h: work.height},
            scale: outputs[index]?.get_scale() ?? 1.0,
            refresh_mhz: 0,  // Mutter doesn't expose mode refresh cleanly here
            is_primary: index === primaryIndex,
            is_connected: true,
        };
    }

    // ── D-Bus methods ───────────────────────────────────────────────────

    ping() {
        return '1.0.0';
    }

    list_windows() {
        const out = global.display.list_all_windows()
            .filter(w => !w.is_override_redirect())
            .map(w => this._describeWindow(w));
        return JSON.stringify(out);
    }

    get_window(wid) {
        const w = this._windowById(wid);
        if (!w) return ERR('unknown_window', `no window with id ${wid}`);
        return JSON.stringify(this._describeWindow(w));
    }

    list_outputs() {
        const n = global.display.get_n_monitors();
        const out = [];
        for (let i = 0; i < n; i++)
            out.push(this._describeMonitor(i));
        return JSON.stringify(out);
    }

    current_workspace() {
        return global.display.get_workspace_manager().get_active_workspace_index();
    }

    workspace_count() {
        return global.display.get_workspace_manager().get_n_workspaces();
    }

    set_geometry(request_json) {
        let req;
        try { req = JSON.parse(request_json); }
        catch { return ERR('unsupported', 'invalid request JSON'); }
        if (!isCoord(req.x) || !isCoord(req.y) || !isExtent(req.w) || !isExtent(req.h))
            return ERR('unsupported', 'geometry must be integer x/y and positive w/h');
        if (req.desktop !== null && req.desktop !== undefined
            && !(Number.isInteger(req.desktop) && req.desktop >= 0))
            return ERR('unsupported', 'desktop must be a non-negative integer');
        if (req.monitor !== null && req.monitor !== undefined
            && typeof req.monitor !== 'string')
            return ERR('unsupported', 'monitor must be an output name');

        const w = this._windowById(req.id);
        if (!w) return ERR('unknown_window', `no window with id ${req.id}`);

        // Tiled / maximised windows ignore geometry writes — unmaximize
        // first (docs/06 §move_resize_frame caveats).
        if (w.get_maximized() !== 0)
            w.unmaximize(Meta.MaximizeFlags.HORIZONTAL | Meta.MaximizeFlags.VERTICAL);

        if (req.desktop !== null && req.desktop !== undefined) {
            const ws = global.display.get_workspace_manager().get_workspace_by_index(req.desktop);
            if (ws) w.change_workspace(ws);
        }

        if (req.monitor) {
            const n = global.display.get_n_monitors();
            for (let i = 0; i < n; i++) {
                if (this._describeMonitor(i).name === req.monitor) {
                    w.move_to_monitor(i);
                    break;
                }
            }
        }

        // Idle-schedule the move: window-created + immediate write races
        // on Mutter, so we let the frame settle before asking.
        GLib.idle_add(GLib.PRIORITY_DEFAULT, () => {
            if (w.get_display()) {
                w.move_resize_frame(true, req.x, req.y, req.w, req.h);
            }
            return GLib.SOURCE_REMOVE;
        });
        return OK();
    }

    set_state(wid, state) {
        const w = this._windowById(wid);
        if (!w) return ERR('unknown_window', `no window with id ${wid}`);
        switch (state) {
            case 'normal':
                if (w.is_fullscreen()) w.unmake_fullscreen();
                if (w.minimized) w.unminimize();
                if (w.get_maximized() !== 0)
                    w.unmaximize(Meta.MaximizeFlags.HORIZONTAL | Meta.MaximizeFlags.VERTICAL);
                return OK();
            case 'maximized':
                w.maximize(Meta.MaximizeFlags.HORIZONTAL | Meta.MaximizeFlags.VERTICAL);
                return OK();
            case 'minimized':
                w.minimize();
                return OK();
            case 'fullscreen':
                w.make_fullscreen();
                return OK();
            default:
                return ERR('unsupported', `unknown state ${state}`);
        }
    }

    close_window(wid) {
        const w = this._windowById(wid);
        if (!w) return ERR('unknown_window', `no window with id ${wid}`);
        w.delete(global.get_current_time());
        return OK();
    }

    register_hotkey(callback_id, accel) {
        if (this._hotkeys.has(callback_id))
            return OK();  // idempotent — already registered
        const settings = this._getSettings();
        try {
            const actionId = Main.wm.addKeybinding(
                `perch-${callback_id}`,
                settings,
                Meta.KeyBindingFlags.NONE,
                Shell.ActionMode.NORMAL,
                () => this._dbus.emit_signal('HotkeyFired',
                    new GLib.Variant('(s)', [callback_id]))
            );
            this._hotkeys.set(callback_id, actionId);
            return OK();
        } catch (e) {
            return ERR('unsupported', `addKeybinding failed: ${e.message}`);
        }
    }

    unregister_hotkey(callback_id) {
        if (!this._hotkeys.has(callback_id)) return;
        Main.wm.removeKeybinding(`perch-${callback_id}`);
        this._hotkeys.delete(callback_id);
    }

    _getSettings() {
        // Each extension that calls addKeybinding needs its own settings
        // schema. The landing commit ships a placeholder that callers
        // must finish — the schema file lives alongside extension.js
        // in the per-GNOME branch (GSchema compilation is version-
        // specific). See STATUS.md §Schema.
        return Extension.lookupByUUID('perch@milnet01.github.io')
                        ?.getSettings?.()
             ?? null;
    }
}


export default class PerchExtension extends Extension {
    enable() {
        this._svc = new PerchMutterService();
        this._svc.export();
    }

    disable() {
        this._svc?.unexport();
        this._svc = null;
    }
}
