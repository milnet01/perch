// Perch KWin IPC spike script.
//
// Subscribes to workspace.windowAdded and fires WindowAdded outbound on the
// Python-owned service io.github.milnet01.Perch.spike at /KWin. Maintains a
// long-poll callback chain against PollCommand so Python can push work into
// the KWin JS context with ~one-D-Bus-round-trip latency and zero wakeups
// while idle.
//
// All payloads are JSON strings — KWin bug 486024 makes typed variadic
// marshalling unreliable, so every arg we pass through callDBus is an "s".

const SVC = "io.github.milnet01.Perch.spike";
const OBJ = "/KWin";
const IF  = "io.github.milnet01.Perch.spike.KWin1";

function fireWindowAdded(w) {
    const payload = JSON.stringify({
        id: w.internalId.toString(),
        caption: w.caption || "",
    });
    callDBus(SVC, OBJ, IF, "WindowAdded", payload);
}

function poll() {
    callDBus(SVC, OBJ, IF, "PollCommand", function (reply) {
        try {
            const cmd = JSON.parse(reply);
            if (cmd && !cmd.nop && typeof cmd.seq === "number") {
                callDBus(SVC, OBJ, IF, "CommandDone",
                    JSON.stringify({ seq: cmd.seq, result: cmd.echo }));
            }
        } catch (e) {
            // Malformed reply — drop and re-arm. The harness counts mismatches
            // on the Python side.
        }
        poll();
    });
}

workspace.windowAdded.connect(fireWindowAdded);
poll();
callDBus(SVC, OBJ, IF, "ScriptReady", "");
