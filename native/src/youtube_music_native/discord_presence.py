"""Opt-in Discord presence over nonblocking local IPC, with no account/session access."""

import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import struct
import sys
import time
import uuid

from PySide6.QtCore import QObject, Property, QSettings, QTimer, Signal, Slot
from PySide6.QtNetwork import QLocalSocket

DEFAULT_APPLICATION_ID = "1563325756040286280"

MAX_FRAME = 1024 * 1024


def ipc_paths(platform=sys.platform, environment=None):
    env = os.environ if environment is None else environment
    if platform == "win32":
        return ["discord-ipc-" + str(index) for index in range(10)]
    roots = list(dict.fromkeys(env.get(key) for key in ("XDG_RUNTIME_DIR", "TMPDIR", "TMP", "TEMP") if env.get(key))) + ["/tmp"]
    # Flatpak exposes the same IPC endpoint beneath its application runtime folder.
    roots += [str(PurePosixPath(root) / "app/com.discordapp.Discord") for root in roots[:]]
    return [str(PurePosixPath(root) / ("discord-ipc-" + str(index))) for root in dict.fromkeys(roots) for index in range(10)]


def activity_for(player, buttons=False, now=None):
    if not player.hasTrack or not player.playing:
        return None
    track = player.currentTrack
    artist = " · ".join(str(row.get("name", "")) for row in track.get("artists", []) if isinstance(row, dict) and row.get("name")) or str(track.get("artist") or "")
    activity = {"type": 2, "details": str(track.get("title") or "Unknown track")[:128], "state": (artist or "YouTube Music")[:128]}
    now = time.time() if now is None else now
    duration, position = player.duration, player.position
    if all(isinstance(value, (float, int)) and math.isfinite(value) for value in (duration, position)) and duration > 0:
        activity["timestamps"] = {"start": int(now - max(0., position)), "end": int(now + max(0., duration - position))}
    video = track.get("videoId") or track.get("id")
    if buttons and isinstance(video, str) and re.fullmatch(r"[A-Za-z0-9_-]{11}", video):
        activity["buttons"] = [{"label": "Listen on YouTube Music", "url": "https://music.youtube.com/watch?v=" + video}]
    return activity


class DiscordPipe(QObject):
    """One bounded IPC attempt; every operation returns to Qt's event loop."""
    ready = Signal()
    failed = Signal(str)
    acknowledged = Signal()

    def __init__(self, client_id, parent=None, paths=None):
        super().__init__(parent)
        self.client_id = client_id
        self.paths = list(ipc_paths() if paths is None else paths)
        self.socket = None
        self.buffer = bytearray()
        self.connected = False
        self.closed = False
        self.pending = ""
        self.latest = None
        self.has_latest = False
        self.connect_timer = QTimer(self)
        self.connect_timer.setSingleShot(True)
        self.connect_timer.timeout.connect(self._next)
        self.deadline = QTimer(self)
        self.deadline.setSingleShot(True)
        self.deadline.timeout.connect(self._timeout)

    @Slot()
    def _timeout(self):
        if not self.connected and self.paths:
            self._next()
        else:
            self._fail("Discord did not respond. Retry after opening the desktop app.")

    @Slot()
    def _disconnected(self):
        self._fail("Discord disconnected. Retrying shortly.")

    def start(self):
        self._next()

    def _dispose_socket(self):
        if self.socket:
            socket, self.socket = self.socket, None
            socket.blockSignals(True)
            socket.abort()
            socket.deleteLater()

    def _next(self):
        if self.closed:
            return
        self._dispose_socket()
        self.buffer.clear()
        if not self.paths:
            self._fail("Discord desktop is unavailable. Open Discord and retry.")
            return
        path = self.paths.pop(0)
        socket = self.socket = QLocalSocket(self)
        socket.setReadBufferSize(MAX_FRAME + 8)
        socket.connected.connect(self._handshake)
        socket.readyRead.connect(self._read)
        socket.errorOccurred.connect(self._socket_error)
        socket.disconnected.connect(self._disconnected)
        self.deadline.start(3000)
        socket.connectToServer(path)

    def _socket_error(self, error):
        if self.connected:
            self._fail("Discord disconnected. Retrying shortly.")
        elif not self.closed:
            self.deadline.stop()
            # Queue the next path so immediate missing-pipe failures cannot recurse.
            self._dispose_socket()
            self.connect_timer.start(0)

    def _write(self, opcode, payload):
        if not self.socket or self.closed:
            return
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.socket.write(struct.pack("<II", opcode, len(body)) + body)

    def _handshake(self):
        self._write(0, {"v": 1, "client_id": self.client_id})
        self.deadline.start(5000)

    def _read(self):
        if not self.socket or self.closed:
            return
        self.buffer.extend(bytes(self.socket.readAll()))
        while len(self.buffer) >= 8:
            opcode, size = struct.unpack("<II", self.buffer[:8])
            if size > MAX_FRAME:
                self._fail("Discord returned an invalid response.")
                return
            if len(self.buffer) < size + 8:
                return
            raw = bytes(self.buffer[8:8 + size])
            del self.buffer[:8 + size]
            try:
                body = json.loads(raw)
            except (ValueError, UnicodeError, RecursionError):
                self._fail("Discord returned an invalid response.")
                return
            if opcode == 3:
                self._write(4, body)
            elif opcode == 2 or not isinstance(body, dict):
                self._fail("Discord rejected the connection. Check your application ID.")
                return
            elif opcode == 1 and body.get("evt") == "ERROR":
                self._fail("Discord rejected the presence. Check your application ID and activity settings.")
                return
            elif opcode == 1 and body.get("evt") == "READY" and not self.connected:
                self.connected = True
                self.deadline.stop()
                self.ready.emit()
            elif opcode == 1 and self.pending and body.get("nonce") == self.pending:
                self.pending = ""
                self.deadline.stop()
                self.acknowledged.emit()
                if self.has_latest:
                    value, self.has_latest = self.latest, False
                    self.publish(value)

    def publish(self, activity):
        if not self.connected or self.closed:
            return
        if self.pending:
            self.latest, self.has_latest = activity, True
            return
        self.pending = uuid.uuid4().hex
        self._write(1, {"cmd": "SET_ACTIVITY", "args": {"pid": os.getpid(), "activity": activity}, "nonce": self.pending})
        self.deadline.start(5000)

    def _fail(self, message):
        if self.closed:
            return
        self.close()
        self.failed.emit(message)

    def close(self, clear=False):
        if clear and self.connected and not self.closed:
            # A final clear is best effort; disconnect also removes this process's activity.
            self._write(1, {"cmd": "SET_ACTIVITY", "args": {"pid": os.getpid(), "activity": None}, "nonce": uuid.uuid4().hex})
            self.socket.flush()
        self.closed, self.connected = True, False
        self.deadline.stop()
        self.connect_timer.stop()
        self._dispose_socket()
        self.buffer.clear()


class DiscordPresence(QObject):
    changed = Signal()

    def __init__(self, player, settings_path, parent=None, pipe_factory=DiscordPipe, fixture=False):
        super().__init__(parent)
        self.player, self.factory, self.fixture = player, pipe_factory, fixture
        self.settings = QSettings(str(settings_path), QSettings.Format.IniFormat)
        self._enabled = self.settings.value("discord/enabled", False, type=bool)
        self._client = str(self.settings.value("discord/clientId", "") or DEFAULT_APPLICATION_ID)
        self._buttons = self.settings.value("discord/buttons", False, type=bool)
        self._status, self.pipe, self._attempts = "Disabled", None, 0
        self._closed, self._last_sent = False, 0.
        self.update_timer = QTimer(self)
        self.update_timer.setSingleShot(True)
        self.update_timer.timeout.connect(self._publish)
        self.retry_timer = QTimer(self)
        self.retry_timer.setSingleShot(True)
        self.retry_timer.setInterval(30000)
        self.retry_timer.timeout.connect(self._connect)
        player.changed.connect(self._refresh)
        player.seeked.connect(self._refresh)
        self._refresh()

    @Property(bool, notify=changed)
    def enabled(self):
        return self._enabled

    @Property(str, constant=True)
    def defaultClientId(self):
        return DEFAULT_APPLICATION_ID

    @Property(str, notify=changed)
    def clientId(self):
        return self._client

    @Property(bool, notify=changed)
    def buttons(self):
        return self._buttons

    @Property(str, notify=changed)
    def status(self):
        return self._status

    def _set_status(self, status):
        if status != self._status:
            self._status = status
            self.changed.emit()

    @Slot(bool)
    def setEnabled(self, value):
        self._enabled = value
        self.settings.setValue("discord/enabled", value)
        self._attempts = 0
        self.changed.emit()
        self._refresh()

    @Slot(str)
    def setClientId(self, value):
        value = value.strip()
        if value and not re.fullmatch(r"[0-9]{17,20}", value):
            self._set_status("Enter the numeric Application ID from the Discord Developer Portal.")
            return
        self._disconnect()
        self._client, self._attempts = value or DEFAULT_APPLICATION_ID, 0
        self.settings.setValue("discord/clientId", value)
        self.changed.emit()
        self._refresh()

    @Slot(bool)
    def setButtons(self, value):
        self._buttons = value
        self.settings.setValue("discord/buttons", value)
        self.changed.emit()
        self._refresh()

    @Slot()
    def retry(self):
        self._disconnect()
        self._attempts = 0
        self._refresh()

    def _disconnect(self):
        self.update_timer.stop()
        self.retry_timer.stop()
        if self.pipe:
            pipe, self.pipe = self.pipe, None
            pipe.close(clear=True)
            pipe.deleteLater()

    def _refresh(self, *args):
        if self._closed:
            return
        configured = bool(re.fullmatch(r"[0-9]{17,20}", self._client))
        if not self._enabled or not configured or not self.player.playing or not self.player.hasTrack:
            self._disconnect()
            self._attempts = 0
            self._set_status("Disabled" if not self._enabled else
                             "Setup Required — save your Discord Application ID." if not configured else
                             "Ready — presence appears while music plays.")
        elif self.fixture:
            self._set_status("Presence is disabled in the visual fixture.")
        elif self.pipe and self.pipe.connected:
            if not self.update_timer.isActive():
                self.update_timer.start(max(0, round((15 - (time.monotonic() - self._last_sent)) * 1000)))
        elif not self.pipe and not self.retry_timer.isActive() and self._attempts < 5:
            self._connect()

    def _connect(self):
        if self._closed or not self._enabled or not self.player.playing or self.fixture or self.pipe:
            return
        self._attempts += 1
        self._set_status("Connecting to Discord…")
        pipe = self.pipe = self.factory(self._client, self)
        pipe.ready.connect(self._ready)
        pipe.failed.connect(self._failed)
        pipe.acknowledged.connect(self._acknowledged)
        pipe.start()

    @Slot()
    def _ready(self):
        if self.sender() is self.pipe:
            self._publish()

    @Slot()
    def _acknowledged(self):
        if self.sender() is self.pipe:
            self._attempts = 0
            self._set_status("Sharing listening activity")

    def _publish(self):
        if self.pipe and self.pipe.connected and self._enabled and not self._closed:
            self._last_sent = time.monotonic()
            self.pipe.publish(activity_for(self.player, self._buttons))

    @Slot(str)
    def _failed(self, message):
        pipe = self.sender()
        if pipe is not self.pipe:
            return
        self.pipe = None
        pipe.deleteLater()
        self.update_timer.stop()
        self._set_status(message if self._attempts < 5 else "Discord is unavailable. Use Retry after opening the desktop app.")
        if self._enabled and self.player.playing and self._attempts < 5:
            self.retry_timer.start()

    def close(self):
        self._closed = True
        self._disconnect()
