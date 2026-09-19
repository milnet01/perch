"""One Perch per user session.

See ``docs/01-architecture.md`` §Why one process. A second copy would write
the same ``state.json`` and claim the same KWin bus name as the first, so it
refuses to start instead. The guard is a :class:`QLockFile`: Qt checks
whether the process holding a lock still exists, so a lock left behind by a
crash is recovered on the next start.
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QLockFile, QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from . import paths

#: The one request a second copy can make of the running one.
SETTINGS_REQUEST = b"settings\n"


def lock_path() -> Path:
    """``$XDG_RUNTIME_DIR/perch.lock``, else the state directory's.

    The runtime directory is per-session and cleared at logout, which is
    the lifetime the lock describes.
    """
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime and Path(runtime).is_absolute():
        return Path(runtime) / "perch.lock"
    return paths.state_dir() / "perch.lock"


def acquire_instance_lock() -> QLockFile | None:
    """Take the lock, or return ``None`` when another Perch holds it.

    The caller keeps the returned object for the life of the process;
    releasing it (or exiting) frees the lock.
    """
    path = lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(path))
    # Never treat a live holder's lock as stale by age: Perch runs for the
    # whole session. A dead holder is still detected by process check.
    lock.setStaleLockTime(0)
    if lock.tryLock(0):
        return lock
    return None


def socket_path() -> Path:
    """The running copy's request socket, beside the lock."""
    return lock_path().with_name("perch.sock")


class InstanceChannel(QObject):
    """The running copy's end of the socket ``perch --settings`` writes to.

    Only the lock holder creates one, so a socket file left by a crashed
    copy is safe to remove before listening.
    """

    settings_requested = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._on_connection)

    def listen(self) -> bool:
        path = str(socket_path())
        QLocalServer.removeServer(path)
        return self._server.listen(path)

    def error_string(self) -> str:
        return self._server.errorString()

    def _on_connection(self) -> None:
        while (conn := self._server.nextPendingConnection()) is not None:
            conn.readyRead.connect(lambda c=conn: self._on_ready(c))

    def _on_ready(self, conn: QLocalSocket) -> None:
        request = bytes(conn.readAll().data())
        # One request per connection: close it and let Qt free it once this
        # slot has returned, before acting on what it asked for.
        conn.abort()
        conn.deleteLater()
        if request == SETTINGS_REQUEST:
            self.settings_requested.emit()


def request_settings(timeout_ms: int = 2000) -> bool:
    """Ask the running copy to open its settings window. True if delivered."""
    sock = QLocalSocket()
    sock.connectToServer(str(socket_path()))
    if not sock.waitForConnected(timeout_ms):
        return False
    sock.write(SETTINGS_REQUEST)
    delivered = sock.waitForBytesWritten(timeout_ms)
    sock.disconnectFromServer()
    return delivered
