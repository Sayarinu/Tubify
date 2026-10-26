"""Same-user URL handoff to the one player that owns an application data directory."""

import hashlib
import hmac
import json
from pathlib import Path
import secrets
import time

from PySide6.QtCore import QEvent, QLockFile, QObject, QTimer, Signal, Slot
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from .deep_links import parse_link, LinkError
from .playback import write_state

MAX_MESSAGE = 48 * 1024


class LinkInstance(QObject):
    linksReceived = Signal(list)
    linkRejected = Signal(str)

    def __init__(self, data_dir, parent=None):
        super().__init__(parent)
        self.root = Path(data_dir)
        self.name = "youtube-music-native-" + hashlib.sha256(str(self.root.resolve()).encode()).hexdigest()[:24]
        self.lock = QLockFile(str(self.root / "instance.lock"))
        self.lock.setStaleLockTime(0)
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.setMaxPendingConnections(8)
        self.server.newConnection.connect(self._accept)
        self._clients, self._token, self._primary = {}, "", False
        self._waiting, self._ready, self._rejection = [], False, ""
        self.manifest = self.root / "instance.json"

    def claim_or_forward(self, links):
        """Called before constructing a player; waits only during a secondary launch."""
        if len(links) > 1:
            raise LinkError("Open one music link at a time.")
        for link in links:
            parse_link(link)
        if self.lock.tryLock(0):
            QLocalServer.removeServer(self.name)
            if not self.server.listen(self.name):
                self.lock.unlock()
                raise LinkError("The application could not initialize local link handling.")
            self._primary, self._token = True, secrets.token_hex(32)
            # A private token also protects macOS, where Unix socket modes are ignored.
            try:
                write_state(self.manifest, json.dumps({"token": self._token}))
            except OSError:
                self.close()
                raise LinkError("The application could not save local link handling state.") from None
            self._waiting.extend(links)
            return True
        if self.lock.error() != QLockFile.LockError.LockFailedError:
            raise LinkError("The application data directory could not be locked. Check its permissions.")
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            try:
                if self.manifest.stat().st_size > 256:
                    raise ValueError()
                token = json.loads(self.manifest.read_text())["token"]
                if not isinstance(token, str) or len(token) != 64:
                    raise ValueError()
            except (OSError, ValueError, TypeError, KeyError):
                time.sleep(0.025)
                continue
            socket = QLocalSocket()
            socket.connectToServer(self.name)
            if socket.waitForConnected(150):
                data = json.dumps({"token": token, "links": links}, separators=(",", ":")).encode() + b"\n"
                socket.write(data)
                if socket.waitForBytesWritten(150) and socket.waitForReadyRead(700):
                    accepted = bytes(socket.readAll()) == b"ok\n"
                    socket.disconnectFromServer()
                    if accepted:
                        return False
            socket.abort()
            time.sleep(0.025)
        raise LinkError("Tubify is already opening or not responding. Try the link again shortly.")

    def _accept(self):
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            if len(self._clients) >= 8:
                socket.abort()
                socket.deleteLater()
                continue
            socket.setReadBufferSize(MAX_MESSAGE + 1)
            timer = QTimer(socket)
            timer.setSingleShot(True)
            timer.setInterval(2000)
            timer.timeout.connect(self._expired)
            socket.disconnected.connect(self._discard)
            socket.readyRead.connect(self._read)
            self._clients[socket] = bytearray()
            timer.start()
            self._consume(socket)

    @Slot()
    def _expired(self):
        timer = self.sender()
        if timer is not None:
            self._dispose(timer.parent())

    @Slot()
    def _discard(self):
        self._dispose(self.sender())

    def _dispose(self, socket):
        if socket not in self._clients:
            return
        self._clients.pop(socket)
        socket.blockSignals(True)
        socket.abort()
        socket.deleteLater()

    @Slot()
    def _read(self):
        self._consume(self.sender())

    def _consume(self, socket):
        buffer = self._clients.get(socket)
        if buffer is None:
            return
        buffer.extend(bytes(socket.readAll()))
        if len(buffer) > MAX_MESSAGE:
            socket.abort()
            return
        if b"\n" not in buffer:
            return
        try:
            value = json.loads(buffer)
            links, token = value.get("links"), value.get("token")
            if not isinstance(token, str) or not hmac.compare_digest(token, self._token) or not isinstance(links, list) or len(links) > 1:
                raise ValueError()
            for link in links:
                parse_link(link)
        except (ValueError, TypeError, AttributeError, RecursionError):
            socket.abort()
            return
        # Do not acknowledge a second cold-start action that would replace the first.
        if links and self._waiting and not self._ready:
            socket.write(b"busy\n")
            socket.flush()
            socket.disconnectFromServer()
            return
        socket.write(b"ok\n")
        socket.flush()
        socket.disconnectFromServer()
        self.deliver(links)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.FileOpen:
            self.deliver([event.url().toString()])
            return True
        return False

    def deliver(self, links):
        if self._ready:
            self.linksReceived.emit(links)
        elif not self._waiting:
            self._waiting.extend(links)
        elif links != self._waiting:
            self._rejection = "Open one music link at a time. Try the other link again when startup finishes."

    def ready(self):
        self._ready = True
        pending, self._waiting = self._waiting, []
        if pending:
            self.linksReceived.emit(pending)
        if self._rejection:
            self.linkRejected.emit(self._rejection)
            self._rejection = ""

    def close(self):
        for socket in list(self._clients):
            self._dispose(socket)
        self.server.close()
        if self._primary:
            try:
                self.manifest.unlink(missing_ok=True)
            except OSError:
                pass
            self.lock.unlock()
            self._primary = False
