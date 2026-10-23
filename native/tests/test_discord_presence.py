import json
import struct
import time

from PySide6.QtCore import QCoreApplication, QObject, Signal
from PySide6.QtNetwork import QLocalServer
from PySide6.QtTest import QTest

from youtube_music_native.discord_presence import DiscordPipe, DiscordPresence, activity_for, ipc_paths


class Player(QObject):
    changed = Signal()
    seeked = Signal(float)
    hasTrack = True
    playing = True
    currentTrack = {"videoId": "abcdefghijk", "title": "Fixture song", "artists": [{"name": "Fixture artist"}], "source": "https://private.invalid/signed", "session": "private"}
    position = 30.
    duration = 180.


class Pipe(QObject):
    ready = Signal()
    failed = Signal(str)
    acknowledged = Signal()
    def __init__(self, client, parent):
        super().__init__(parent)
        self.client, self.connected, self.sent, self.closed = client, False, [], False
    def start(self):
        pass
    def publish(self, value):
        self.sent.append(value)
    def close(self, clear=False):
        self.closed = True
        self.cleared = clear


def wait_for(predicate):
    deadline = time.monotonic() + 2
    while not predicate() and time.monotonic() < deadline:
        QTest.qWait(5)
    assert predicate()


def test_public_payload_has_only_allowlisted_metadata():
    player = Player()
    result = activity_for(player, True, now=1000)
    assert result == {"type": 2, "details": "Fixture song", "state": "Fixture artist", "timestamps": {"start": 970, "end": 1150}, "buttons": [{"label": "Listen on YouTube Music", "url": "https://music.youtube.com/watch?v=abcdefghijk"}]}
    assert "private" not in json.dumps(result)
    player.currentTrack = {"title": "A" * 300, "artist": "Fallback", "videoId": "invalid&token=private"}
    assert len(activity_for(player)["details"]) == 128
    assert "buttons" not in activity_for(player, True)
    player.playing = False
    assert activity_for(player) is None


def test_paths_are_platform_local():
    assert ipc_paths("win32", {}) == ["discord-ipc-" + str(i) for i in range(10)]
    paths = ipc_paths("linux", {"XDG_RUNTIME_DIR": "/fixture/runtime"})
    assert paths[0] == "/fixture/runtime/discord-ipc-0"
    assert "/fixture/runtime/app/com.discordapp.Discord/discord-ipc-0" in paths


def test_disabled_idle_then_state_transitions_and_throttle(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    player = Player()
    service = DiscordPresence(player, tmp_path / "settings.ini", pipe_factory=Pipe)
    QTest.qWait(10)
    assert not service.enabled and service.pipe is None
    assert not service.retry_timer.isActive() and not service.update_timer.isActive()
    service.setEnabled(True)
    assert service.pipe is None and "Application ID" in service.status
    service.setClientId("123456789012345678")
    pipe = service.pipe
    pipe.connected = True
    pipe.ready.emit()
    assert len(pipe.sent) == 1
    for _ in range(20):
        player.changed.emit()
    assert service.update_timer.isActive() and len(pipe.sent) == 1
    player.position = 45
    player.seeked.emit(45)
    service.update_timer.stop()
    service._publish()
    assert len(pipe.sent) == 2
    service.setButtons(True)
    service.update_timer.stop()
    service._publish()
    assert "buttons" in pipe.sent[-1]
    player.playing = False
    player.changed.emit()
    assert service.pipe is None and pipe.closed and pipe.cleared
    assert not service.retry_timer.isActive() and not service.update_timer.isActive()
    player.playing = True
    player.changed.emit()
    resumed = service.pipe
    service.setEnabled(False)
    assert resumed.closed and service.pipe is None
    service.close()


def test_missing_discord_is_bounded_and_manual_retry_works(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    service = DiscordPresence(Player(), tmp_path / "settings.ini", pipe_factory=Pipe)
    service.setClientId("123456789012345678")
    service.setEnabled(True)
    for index in range(5):
        pipe = service.pipe
        # Reaching READY but getting a rejected presence must not reset the budget.
        pipe.connected = True
        pipe.ready.emit()
        pipe.failed.emit("Unavailable")
        assert service.retry_timer.isActive() == (index < 4)
        service.retry_timer.stop()
        if index < 4:
            service._connect()
    assert service.pipe is None and "Retry" in service.status
    service.player.changed.emit()
    assert service.pipe is None
    service.retry()
    assert service.pipe is not None
    service.close()


def test_settings_persist_and_fixture_never_connects(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    path = tmp_path / "settings.ini"
    service = DiscordPresence(Player(), path, pipe_factory=lambda *args: (_ for _ in ()).throw(AssertionError("fixture must not connect")), fixture=True)
    service.setClientId("123456789012345678")
    service.setButtons(True)
    service.setEnabled(True)
    assert service.pipe is None and "fixture" in service.status
    service.close()
    restored = DiscordPresence(Player(), path, fixture=True)
    assert restored.enabled and restored.buttons and restored.clientId == "123456789012345678"
    restored.close()


def test_actual_local_ipc_framing_ack_coalescing_and_invalid_length(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    server = QLocalServer()
    endpoint = str(tmp_path / "discord-fixture")
    assert server.listen(endpoint)
    pipe = DiscordPipe("123456789012345678", paths=[endpoint])
    ready, errors = [], []
    pipe.ready.connect(lambda: ready.append(True))
    pipe.failed.connect(errors.append)
    pipe.start()
    wait_for(server.hasPendingConnections)
    peer = server.nextPendingConnection()
    def receive():
        wait_for(lambda: peer.bytesAvailable() >= 8)
        raw = bytes(peer.readAll())
        opcode, size = struct.unpack("<II", raw[:8])
        assert len(raw[8:]) == size
        return opcode, json.loads(raw[8:])
    def send(opcode, body):
        data = json.dumps(body).encode()
        peer.write(struct.pack("<II", opcode, len(data)) + data)
        peer.flush()
    assert receive() == (0, {"v": 1, "client_id": "123456789012345678"})
    send(1, {"evt": "READY"})
    wait_for(lambda: bool(ready))
    pipe.publish({"details": "First"})
    opcode, first = receive()
    assert opcode == 1 and first["cmd"] == "SET_ACTIVITY"
    pipe.publish({"details": "Second"})
    pipe.publish({"details": "Latest"})
    send(1, {"nonce": first["nonce"]})
    opcode, latest = receive()
    assert latest["args"]["activity"] == {"details": "Latest"}
    send(1, {"nonce": latest["nonce"]})
    wait_for(lambda: not pipe.pending)
    send(3, {"nonce": "ping"})
    assert receive() == (4, {"nonce": "ping"})
    peer.write(struct.pack("<II", 1, 1024 * 1024 + 1))
    peer.flush()
    wait_for(lambda: bool(errors))
    assert pipe.closed and not pipe.deadline.isActive()
    pipe.close()
    peer.close()
    server.close()


def test_stalled_endpoint_falls_through_and_nested_frame_closes(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    servers = [QLocalServer(), QLocalServer()]
    paths = [str(tmp_path / f"discord-fixture-{i}") for i in range(2)]
    for server, path in zip(servers, paths):
        assert server.listen(path)
    pipe = DiscordPipe("123456789012345678", paths=paths)
    errors = []
    pipe.failed.connect(errors.append)
    pipe.start()
    wait_for(servers[0].hasPendingConnections)
    first = servers[0].nextPendingConnection()
    pipe._timeout()
    wait_for(servers[1].hasPendingConnections)
    second = servers[1].nextPendingConnection()
    wait_for(lambda: second.bytesAvailable() >= 8)
    second.readAll()
    ready = json.dumps({"evt": "READY"}).encode()
    frame = struct.pack("<II", 1, len(ready)) + ready
    second.write(frame[:5]); second.flush()
    QTest.qWait(10)
    assert not pipe.connected and not errors
    second.write(frame[5:]); second.flush()
    wait_for(lambda: pipe.connected)
    nested = b'[' * 2000 + b'0' + b']' * 2000
    second.write(struct.pack("<II", 1, len(nested)) + nested); second.flush()
    wait_for(lambda: bool(errors))
    assert pipe.closed and not pipe.deadline.isActive()
    first.close(); second.close()
    for server in servers:
        server.close()
