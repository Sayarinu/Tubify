import json

from PySide6.QtCore import QCoreApplication, QObject, Signal

from youtube_music_native.integrations.cast_receiver import CastReceiver, cast_ids, clean_name
from youtube_music_native.playback.playback import Playback


class Player(QObject):
    changed = Signal()
    seeked = Signal(float)
    trackStarted = Signal("QVariantMap")

    def __init__(self):
        super().__init__()
        self.tracks, self.index, self.position, self.duration = [], 0, 0., 0.
        self.playing, self.busy, self.calls = False, False, []

    @property
    def hasTrack(self):
        return bool(self.tracks)

    @property
    def currentTrack(self):
        return self.tracks[self.index] if self.tracks else {}

    @property
    def upcomingTrack(self):
        return self.tracks[self.index + 1] if self.index + 1 < len(self.tracks) else {}

    def playTracks(self, tracks, index, label, position):
        self.calls.append(("playTracks", [track["videoId"] for track in tracks], index, position))
        self.tracks, self.index, self.position, self.duration, self.playing = [dict(track) for track in tracks], index, position, 200., True
        self.changed.emit()
        self.trackStarted.emit(self.currentTrack)

    def resume(self):
        self.calls.append(("resume",))
        self.playing = True
        self.changed.emit()

    def pause(self):
        self.calls.append(("pause",))
        self.playing = False
        self.changed.emit()

    def seek(self, position):
        self.calls.append(("seek", position))
        self.position = position
        self.seeked.emit(position)

    def next(self):
        self.calls.append(("next",))

    def previous(self):
        self.calls.append(("previous",))

    def appendContext(self, tracks):
        self.calls.append(("appendContext", [track["videoId"] for track in tracks]))

    def updateTrack(self, video, values):
        self.calls.append(("updateTrack", video, values))


class Shell(QObject):
    volumeChanged = Signal()

    def __init__(self):
        super().__init__()
        self.volume = 70

    def setVolume(self, value):
        self.volume = value
        self.volumeChanged.emit()


class Lounge(QObject):
    command = Signal(str, "QVariantMap")
    connected = Signal()
    stateChanged = Signal(str)
    created = []

    def __init__(self, settings, name, parent=None):
        super().__init__(parent)
        self.name, self.sent, self.ready, self.running, self.pairings = name, [], True, False, []
        Lounge.created.append(self)

    def start(self):
        self.running = True

    def stop(self):
        self.running = False

    def rename(self, name):
        self.name = name

    def send(self, name, payload=None):
        self.sent.append((name, dict(payload or {})))

    def register_pairing_code(self, code, done):
        self.pairings.append(code)
        done(True)

    def names(self):
        return [name for name, _payload in self.sent]


class Dial(QObject):
    searched = Signal()
    described = Signal()
    launched = Signal(str, str)
    stopRequested = Signal()
    created = []

    def __init__(self, name, udn, parent=None):
        super().__init__(parent)
        self.name, self.started = name, False
        Dial.created.append(self)

    def start(self):
        self.started = True
        return ""

    def stop(self):
        self.started = False


class Worker(QObject):
    succeeded = Signal(int, dict)
    failed = Signal(int, dict)

    def __init__(self):
        super().__init__()
        self.requests = []

    def request(self, operation, payload):
        self.requests.append((operation, payload))
        return len(self.requests)


def receiver(tmp_path, enabled=True, fixture=False, worker=None):
    Lounge.created.clear()
    Dial.created.clear()
    player, shell = Player(), Shell()
    settings = tmp_path / "settings.ini"
    settings.write_text("[cast]\nenabled=%s\n" % ("true" if enabled else "false"))
    cast = CastReceiver(player, shell, settings, worker=worker, parent=None, fixture=fixture, lounge_factory=Lounge, dial_factory=Dial)
    return cast, player, shell


def test_disabled_and_fixture_receivers_open_nothing(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    cast, _player, _shell = receiver(tmp_path, enabled=False)
    assert not Lounge.created and not Dial.created and cast.status == "Off"
    cast, _player, _shell = receiver(tmp_path, enabled=True, fixture=True)
    assert not Lounge.created and not Dial.created and "fixture" in cast.status
    cast, _player, _shell = receiver(tmp_path, enabled=False)
    cast.setEnabled(True)
    assert Dial.created[0].started and Lounge.created[0].running
    cast.setEnabled(False)
    assert not Dial.created[0].started and not Lounge.created[0].running and cast.status == "Off"
    assert app


def test_cast_playlist_plays_validated_ids_from_index_and_position(tmp_path):
    cast, player, _shell = receiver(tmp_path)
    lounge = Lounge.created[0]
    lounge.command.emit("setPlaylist", {"listId": "RQsecretqueue", "videoIds": "aaaaaaaaaaa,bad!,bbbbbbbbbbb,ccccccccccc", "currentIndex": "1", "currentTime": "42.5", "ctt": "SECRET"})
    assert player.calls[0] == ("playTracks", ["aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc"], 1, 42.5)
    now = next(payload for name, payload in lounge.sent if name == "nowPlaying")
    assert now["videoId"] == "bbbbbbbbbbb" and now["currentIndex"] == 1 and now["listId"] == "RQsecretqueue" and now["state"] == 1
    assert ("onHasPreviousNextChanged", {"hasPrevious": "true", "hasNext": "true"}) in lounge.sent

    # The phone re-sending the same queue only seeks; it does not restart the song.
    player.calls.clear()
    lounge.command.emit("setPlaylist", {"videoIds": "aaaaaaaaaaa,bbbbbbbbbbb,ccccccccccc", "currentIndex": "1", "currentTime": "90"})
    assert player.calls == [("seek", 90.0), ("resume",)]

    lounge.command.emit("updatePlaylist", {"videoIds": "aaaaaaaaaaa,bbbbbbbbbbb,ccccccccccc,ddddddddddd"})
    assert player.calls[-1] == ("appendContext", ["ddddddddddd"])
    lounge.command.emit("updatePlaylist", {})
    lounge.command.emit("setPlaylist", {"videoIds": "not-valid"})
    assert player.calls[-1] == ("appendContext", ["ddddddddddd"])


def test_transport_and_volume_commands_drive_player_and_report_back(tmp_path):
    cast, player, shell = receiver(tmp_path)
    lounge = Lounge.created[0]
    lounge.command.emit("setPlaylist", {"videoIds": "aaaaaaaaaaa", "currentIndex": "0"})
    lounge.sent.clear()
    for name, payload in (("pause", {}), ("seekTo", {"newTime": "75"}), ("play", {}), ("next", {}), ("previous", {}), ("seekTo", {"newTime": "nan"})):
        lounge.command.emit(name, payload)
    assert player.calls[1:] == [("pause",), ("seek", 75.0), ("resume",), ("next",), ("previous",), ("seek", 0.0)]
    states = [payload["state"] for name, payload in lounge.sent if name == "onStateChange"]
    assert states[:2] == [2, 2] and 1 in states
    lounge.command.emit("setVolume", {"volume": "40", "muted": "false"})
    assert shell.volume == 40
    lounge.command.emit("setVolume", {"volume": "40", "muted": "true"})
    assert shell.volume == 0
    lounge.command.emit("setVolume", {"volume": "900"})
    assert shell.volume == 100
    lounge.sent.clear()
    lounge.command.emit("getVolume", {})
    lounge.command.emit("setAutoplayMode", {"autoplayMode": "ENABLED"})
    assert lounge.sent == [("onVolumeChanged", {"volume": 100, "muted": "false"}), ("onAutoplayModeChanged", {"autoplayMode": "UNSUPPORTED"})]


def test_local_changes_are_reported_once(tmp_path):
    cast, player, _shell = receiver(tmp_path)
    lounge = Lounge.created[0]
    lounge.command.emit("setPlaylist", {"videoIds": "aaaaaaaaaaa", "currentIndex": "0"})
    lounge.sent.clear()
    player.changed.emit()
    player.changed.emit()
    assert lounge.sent == []
    player.playing = False
    player.changed.emit()
    assert lounge.names() == ["onStateChange"]
    player.tracks = [{"videoId": "zzzzzzzzzzz", "title": "Local pick"}]
    player.changed.emit()
    now = lounge.sent[1][1]
    assert lounge.sent[1][0] == "nowPlaying" and now["videoId"] == "zzzzzzzzzzz" and "currentIndex" not in now and "listId" not in now


def test_remote_status_never_echoes_device_data(tmp_path):
    cast, _player, _shell = receiver(tmp_path)
    lounge = Lounge.created[0]
    lounge.stateChanged.emit("ready")
    assert cast.status.startswith("Ready") and not cast.connected
    devices = [{"type": "LOUNGE_SCREEN", "id": "SCREEN-ID"}, {"type": "REMOTE_CONTROL", "name": "Phone of someone", "id": "PHONE-ID", "localChannelEncryptionKey": "KEY"}]
    lounge.command.emit("loungeStatus", {"devices": json.dumps(devices), "queueId": "RQ-SECRET"})
    assert cast.connected and cast.status == "Connected to a phone."
    assert {"onAutoplayModeChanged", "onVolumeChanged", "nowPlaying"} <= set(lounge.names())
    for secret in ("Phone of someone", "PHONE-ID", "KEY", "SCREEN-ID", "RQ-SECRET"):
        assert secret not in cast.status
    lounge.command.emit("remoteDisconnected", {})
    assert not cast.connected and cast.status.startswith("Ready")
    lounge.command.emit("loungeStatus", {"devices": "not json"})
    assert not cast.connected
    lounge.stateChanged.emit("retrying")
    assert cast.status == "Can't reach YouTube. Retrying…"


def test_dial_launch_registers_the_pairing_code(tmp_path):
    cast, _player, _shell = receiver(tmp_path)
    Dial.created[0].launched.emit("abcd-1234", "m")
    assert Lounge.created[0].pairings == ["abcd-1234"]


def test_metadata_is_filled_for_cast_songs_without_looking_up_the_lounge_queue(tmp_path):
    worker = Worker()
    cast, player, _shell = receiver(tmp_path, worker=worker)
    Lounge.created[0].command.emit("setPlaylist", {"listId": "RQsecretqueue", "videoIds": "aaaaaaaaaaa", "currentIndex": "0"})
    assert worker.requests == [("catalog", {"cache_path": "", "route": "radio", "params": {"id": "aaaaaaaaaaa", "radio": False}})]
    worker.succeeded.emit(99, {"items": [{"videoId": "aaaaaaaaaaa", "title": "Ignored"}]})
    worker.succeeded.emit(1, {"items": [{"videoId": "other", "title": "Wrong"}, {"videoId": "aaaaaaaaaaa", "title": "Song", "artists": [{"name": "Artist"}], "key": "drop"}]})
    assert player.calls[-1] == ("updateTrack", "aaaaaaaaaaa", {"title": "Song", "artists": [{"name": "Artist"}]})


def test_names_and_ids_are_sanitised():
    assert clean_name('  Living <room> & "tv"  ') == "Living room  tv"
    assert clean_name("") .startswith("Tubify")
    assert len(clean_name("x" * 200)) == 60
    assert cast_ids({"videoIds": ",".join(["aaaaaaaaaaa"] * 600)}) == ["aaaaaaaaaaa"] * 500
    assert cast_ids({"videoIds": "", "videoId": "bbbbbbbbbbb"}) == ["bbbbbbbbbbb"]
    assert cast_ids({"videoIds": "../../etc"}) == []


def test_fake_player_only_offers_what_real_playback_has():
    # The receiver is tested against this fake, so a member missing from Playback would only fail at runtime.
    fake_members = {name for name in vars(Player) if not name.startswith("_")} - {"staticMetaObject"}
    assert {name for name in fake_members if not hasattr(Playback, name)} == set()


def test_status_says_how_far_discovery_got_without_naming_any_device(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    cast, _player, _shell = receiver(tmp_path)
    lounge, dial = Lounge.created[0], Dial.created[0]
    dial.port = 38008
    lounge.ready = True
    lounge.stateChanged.emit("ready")
    assert "No device has looked for Tubify yet" in cast.status
    dial.searched.emit()
    assert cast.discovery.isActive()
    cast.discovery.stop()
    cast.discovery.timeout.emit()
    assert "firewall" in cast.status and "38008" in cast.status
    dial.described.emit()
    assert "found Tubify" in cast.status
    dial.searched.emit()
    assert not cast.discovery.isActive()
    cast.close()
