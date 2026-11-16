import json

from PySide6.QtCore import QCoreApplication, QObject, Signal

from tubify.integrations.listen_along import ListenAlongHost, party_for, screen_from_secret, secret_for

SCREEN = "host-screen-identity"


class Player(QObject):
    changed = Signal()
    seeked = Signal(float)
    trackStarted = Signal("QVariantMap")

    def __init__(self):
        super().__init__()
        self.track, self.position, self.duration = {}, 0., 0.
        self.playing, self.busy, self.calls = False, False, []

    @property
    def hasTrack(self):
        return bool(self.track)

    @property
    def currentTrack(self):
        return self.track

    def load(self, video, position=0., playing=True):
        self.track, self.position, self.duration, self.playing = {"videoId": video}, position, 200., playing
        self.changed.emit()

    def __getattr__(self, name):
        if name in {"resume", "pause", "seek", "next", "previous", "playTracks"}:
            return lambda *args: self.calls.append((name, *args))
        raise AttributeError(name)


class Lounge(QObject):
    command = Signal(str, "QVariantMap")
    connected = Signal()
    stateChanged = Signal(str)

    def __init__(self, settings, name, parent=None, **options):
        super().__init__(parent)
        self.name, self.options = name, options
        self.ready, self.screen_id, self.sent, self.forgotten = False, SCREEN, [], 0

    def start(self):
        self.ready = True
        self.connected.emit()

    def stop(self):
        self.ready = False

    def forget(self):
        self.forgotten += 1

    def send(self, name, payload=None):
        self.sent.append((name, dict(payload or {})))


def host_for(tmp_path):
    QCoreApplication.instance() or QCoreApplication([])
    player = Player()
    return player, ListenAlongHost(player, tmp_path / "settings.ini", lounge_factory=Lounge)


def test_secrets_carry_only_a_valid_screen_and_the_party_hides_it():
    assert secret_for(SCREEN) == "tl1:" + SCREEN and len(secret_for("x" * 64)) <= 128
    assert screen_from_secret("tl1:" + SCREEN) == SCREEN
    for bad in ("", "tl2:" + SCREEN, "tl1:short", "tl1:bad screen!", None, 7, "tl1:" + "x" * 65):
        assert screen_from_secret(bad) == ""
    assert secret_for("bad id!") == ""
    assert len(party_for(SCREEN)) == 32 and SCREEN not in party_for(SCREEN)


def test_the_host_uses_its_own_screen_and_offers_a_secret_once_bound(tmp_path):
    player, host = host_for(tmp_path)
    assert host.secret == "" and not host.active
    host.start()
    assert host.lounge.options["prefix"] == "listenAlong" and host.lounge.name == "Tubify Listen Along"
    assert host.active and host.secret == "tl1:" + SCREEN and host.party_id == party_for(SCREEN)
    host.stop()
    assert host.secret == "" and not host.active


def test_the_host_broadcasts_songs_seeks_and_pauses(tmp_path):
    player, host = host_for(tmp_path)
    host.start()
    lounge = host.lounge
    lounge.sent.clear()
    player.load("abcdefghijk", 12.)
    name, payload = lounge.sent[-1]
    assert name == "nowPlaying" and payload["videoId"] == "abcdefghijk" and payload["currentTime"] == "12.000" and payload["state"] == 1
    player.position = 40.
    player.seeked.emit(40.)
    assert lounge.sent[-1][0] == "onStateChange" and lounge.sent[-1][1]["currentTime"] == "40.000"
    player.playing = False
    player.changed.emit()
    assert lounge.sent[-1][0] == "onStateChange" and lounge.sent[-1][1]["state"] == 2
    count = len(lounge.sent)
    player.changed.emit()
    assert len(lounge.sent) == count


def test_friends_never_control_the_host(tmp_path):
    player, host = host_for(tmp_path)
    host.start()
    player.load("abcdefghijk")
    for name, payload in [("setPlaylist", {"videoId": "zzzzzzzzzzz"}), ("play", {}), ("pause", {}), ("seekTo", {"newTime": "5"}),
                          ("next", {}), ("previous", {}), ("setVolume", {"volume": "0"}), ("stopVideo", {})]:
        host.lounge.command.emit(name, payload)
    assert player.calls == [] and player.track == {"videoId": "abcdefghijk"} and player.playing


def test_the_host_counts_friends_and_answers_with_the_current_song(tmp_path):
    player, host = host_for(tmp_path)
    host.start()
    player.load("abcdefghijk")
    lounge = host.lounge
    lounge.command.emit("loungeStatus", {"devices": json.dumps([{"type": "LOUNGE_SCREEN"}, {"type": "REMOTE_CONTROL"}, {"type": "REMOTE_CONTROL"}])})
    assert host.followers == 2
    lounge.command.emit("remoteConnected", {})
    lounge.command.emit("remoteDisconnected", {})
    lounge.command.emit("remoteDisconnected", {})
    assert host.followers == 1
    lounge.sent.clear()
    lounge.command.emit("getNowPlaying", {})
    assert lounge.sent[0][0] == "nowPlaying" and lounge.sent[0][1]["videoId"] == "abcdefghijk"
    lounge.command.emit("loungeStatus", {"devices": "not json"})
    assert host.followers == 0


def test_reset_revokes_old_invitations(tmp_path):
    player, host = host_for(tmp_path)
    host.settings.setValue("listenAlong/screenId", SCREEN)
    host.reset()
    assert not host.settings.contains("listenAlong/screenId")
    host.start()
    host.lounge.command.emit("remoteConnected", {})
    host.reset()
    assert host.lounge.forgotten == 1 and host.followers == 0
