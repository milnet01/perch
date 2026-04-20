# Perch bundled KWin script

Runs inside KWin on Plasma 6 Wayland and bridges the KWin Scripting API to
the Perch Python process over D-Bus. The Python side owns the service name
`io.github.milnet01.Perch`; this script calls *out* to that service (the
KWin JS sandbox cannot register a service itself).

Authoritative design: [`docs/05-backend-kwin.md`](../../../../../docs/05-backend-kwin.md).

## Files

- `metadata.json` — KPackage manifest. `KPlugin.Version` is pinned by the
  Python backend: Perch refuses to load a script whose version does not
  match the bundled one, so JS and Python halves cannot drift.
- `contents/code/main.js` — the script itself.

## Install

`perch` installs this tree into
`$XDG_DATA_HOME/kwin/scripts/org.milnet01.perch/` on first run. From that
location KWin can load it via `org.kde.KWin.Scripting.loadScript()`.

For manual testing:

```
$ kpackagetool6 -t KWin/Script -i src/perch/backend/kwin/script
$ qdbus6 org.kde.KWin /Scripting loadScript \
      ~/.local/share/kwin/scripts/org.milnet01.perch/contents/code/main.js \
      org.milnet01.perch
$ qdbus6 org.kde.KWin /Scripting/Script0 run
```

Unload via `kpackagetool6 -t KWin/Script -r org.milnet01.perch`.

## Why JSON strings everywhere

KWin bug 486024: `callDBus(…, numericArg, …)` goes through Qt's best-guess
type coercion, which silently mangles numeric D-Bus signatures (`i`, `u`).
To sidestep this every argument sent between the script and Perch is a
JSON-encoded string. Costs a few microseconds per call. Makes the
script robust against KWin's marshalling quirks.
