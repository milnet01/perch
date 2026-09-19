// ESLint for the JavaScript Perch runs inside the compositor (PERC-0046).
//
// Each file gets the globals of the runtime it actually runs in, and no
// others. That is the point: `no-undef` is what reports a browser API such as
// setInterval used in KWin's QJSEngine, where it does not exist.
import js from "@eslint/js";
import globals from "globals";

export default [
    js.configs.recommended,
    {
        rules: {
            // A leading underscore marks a parameter a D-Bus signature
            // requires and the body deliberately does not use.
            "no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
        },
    },
    {
        // KWin script: a classic script in KWin's QJSEngine sandbox. The
        // globals are the ones a probe of kwin_wayland (Plasma 6) found
        // defined on 2026-09-19; setInterval, setTimeout and Qt are NOT.
        files: ["src/perch/backend/kwin/script/**/*.js"],
        languageOptions: {
            ecmaVersion: 2020,
            sourceType: "script",
            globals: {
                workspace: "readonly",
                options: "readonly",
                KWin: "readonly",
                QTimer: "readonly",
                callDBus: "readonly",
                print: "readonly",
                readConfig: "readonly",
                registerShortcut: "readonly",
                console: "readonly",
            },
        },
    },
    {
        // GNOME Shell extension: an ES module under gjs.
        files: ["src/perch/backend/mutter/extension/**/*.js"],
        languageOptions: {
            ecmaVersion: 2022,
            sourceType: "module",
            globals: {
                global: "readonly",
                console: "readonly",
                logError: "readonly",
            },
        },
    },
];
