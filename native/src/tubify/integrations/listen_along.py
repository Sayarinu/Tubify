"""Listen Along: share playback with friends through a Lounge screen that only broadcasts.

The host runs its own Lounge screen, separate from phone casting. Friends bind to it as
remotes and receive the current song, position and play state. The host ignores every
command a remote sends, so a friend can never control the host's player. The screen ID
travels only inside the Discord join secret and never reaches logs or status text.
"""

import hashlib
import json
import re

from PySide6.QtCore import QObject, Property, QSettings, QTimer, Signal, Slot

from .cast_receiver import details_from, request_details
from .lounge import STATES, Lounge, SCREEN_ID, number, state_payload

SECRET_PREFIX = "tl1:"
SYNC_MS = 10000
NAME = "Tubify Listen Along"
VIDEO = re.compile(r"[A-Za-z0-9_-]{11}")
# A follower within this many seconds of the host is left alone.
DRIFT_S = 3.
# The host resyncs every 10 seconds while playing; this much silence means it is gone.
SILENCE_MS = 45000
# When a different song starts here, wait this long for the host's next song before deciding the
# listener chose it themselves (autoplay can start a radio song just before the host moves on).
GRACE_MS = 8000
LABEL = "Listening Along"


def secret_for(screen_id):
    return SECRET_PREFIX + screen_id if SCREEN_ID.fullmatch(screen_id or "") else ""


def screen_from_secret(secret):
    """The host screen ID inside a join secret, or "" when the secret isn't one of ours."""
    if not isinstance(secret, str) or not secret.startswith(SECRET_PREFIX):
        return ""
    screen = secret[len(SECRET_PREFIX):]
    return screen if SCREEN_ID.fullmatch(screen) else ""


def party_for(screen_id):
    # Discord shows the party ID to friends, so it is a hash rather than the screen ID itself.
    return hashlib.sha256(screen_id.encode()).hexdigest()[:32] if screen_id else ""


class ListenAlongHost(QObject):
    changed = Signal()

    def __init__(self, player, settings_path, parent=None, lounge_factory=Lounge):
        super().__init__(parent)
        self.player = player
        self.settings = QSettings(str(settings_path), QSettings.Format.IniFormat)
        self.lounge_factory, self.lounge = lounge_factory, None
        self._followers, self._last = 0, None
        self.sync = QTimer(self)
        self.sync.setInterval(SYNC_MS)
        self.sync.timeout.connect(self._sync)
        player.changed.connect(self._player_changed)
        player.seeked.connect(lambda _position: self._send_state(force=True))

    @Property(bool, notify=changed)
    def active(self):
        return self.lounge is not None

    @Property(int, notify=changed)
    def followers(self):
        return self._followers

    @property
    def secret(self):
        return secret_for(self.lounge.screen_id) if self.lounge and self.lounge.ready else ""

    @property
    def party_id(self):
        return party_for(self.lounge.screen_id) if self.lounge and self.lounge.ready else ""

    def start(self):
        if self.lounge:
            return
        self.lounge = self.lounge_factory(self.settings, NAME, self, prefix="listenAlong")
        self.lounge.command.connect(self._command)
        self.lounge.connected.connect(self._connected)
        self.lounge.stateChanged.connect(lambda _state: self.changed.emit())
        self.lounge.start()
        self.sync.start()
        self.changed.emit()

    def stop(self):
        if not self.lounge:
            return
        self.sync.stop()
        if self.lounge:
            lounge, self.lounge = self.lounge, None
            lounge.stop()
            lounge.deleteLater()
        self._followers, self._last = 0, None
        self.changed.emit()

    @Slot()
    def reset(self):
        """Give the screen a new identity, which revokes every friend who joined before."""
        if self.lounge:
            self._followers = 0
            self.lounge.forget()
        else:
            self.settings.remove("listenAlong/screenId")
        self.changed.emit()

    def close(self):
        self.stop()

    # --- Friends → host: only presence and a state request are honoured ----------------------
    def _connected(self):
        self._send_now_playing()
        self.changed.emit()

    def _command(self, name, payload):
        if name == "loungeStatus":
            try:
                devices = json.loads(payload.get("devices", "[]"))
            except (TypeError, ValueError):
                devices = []
            self._followers = sum(1 for device in devices if isinstance(device, dict) and device.get("type") == "REMOTE_CONTROL") if isinstance(devices, list) else 0
        elif name == "remoteConnected":
            self._followers += 1
        elif name == "remoteDisconnected":
            self._followers = max(0, self._followers - 1)
        elif name == "getNowPlaying":
            self._send_now_playing()
            return
        else:
            # setPlaylist, play, pause, seekTo, next, setVolume… a friend never controls the host.
            return
        self.changed.emit()
        if name != "remoteDisconnected":
            self._send_now_playing()

    # --- Host → friends ----------------------------------------------------------------------
    def _send(self, name, payload):
        if self.lounge and self.lounge.ready:
            self.lounge.send(name, payload)

    def _video(self):
        return str(self.player.currentTrack.get("videoId", "")) if self.player.hasTrack else ""

    def _send_now_playing(self):
        payload = state_payload(self.player)
        video = self._video()
        if VIDEO.fullmatch(video):
            payload["videoId"] = video
        self._send("nowPlaying", payload)
        self._last = (video, payload["state"])

    def _send_state(self, force=False):
        payload = state_payload(self.player)
        state = (self._video(), payload["state"])
        if force or state != self._last:
            self._last = state
            self._send("onStateChange", payload)

    def _player_changed(self):
        if self._video() != (self._last[0] if self._last else ""):
            self._send_now_playing()
        else:
            self._send_state()

    def _sync(self):
        if self.player.playing:
            self._send_state(force=True)


class ListenAlongFollower(QObject):
    """Plays what a friend's Tubify plays, from the join secret Discord hands over."""
    changed = Signal()

    def __init__(self, player, settings_path, worker=None, cache_path="", parent=None, lounge_factory=Lounge, fixture=False):
        super().__init__(parent)
        self.player, self.worker, self.cache_path, self.fixture = player, worker, str(cache_path), fixture
        self.settings = QSettings(str(settings_path), QSettings.Format.IniFormat)
        self.lounge_factory, self.lounge = lounge_factory, None
        self._video, self._host_state, self._status, self._lookups = "", STATES["idle"], "", {}
        self.silence = QTimer(self)
        self.silence.setSingleShot(True)
        self.silence.setInterval(SILENCE_MS)
        self.silence.timeout.connect(lambda: self.leave("Lost the connection to your friend. Stopped listening along."))
        self.grace = QTimer(self)
        self.grace.setSingleShot(True)
        self.grace.setInterval(GRACE_MS)
        self.grace.timeout.connect(lambda: self.leave("Stopped listening along."))
        player.trackStarted.connect(self._track_started)
        if worker:
            worker.succeeded.connect(self._lookup_done)
            worker.failed.connect(lambda identifier, _error: self._lookups.pop(identifier, None))

    @Property(bool, notify=changed)
    def following(self):
        return self.lounge is not None

    @Property(str, notify=changed)
    def status(self):
        return self._status

    def _set_status(self, text):
        if text != self._status:
            self._status = text
            self.changed.emit()

    @Slot(str)
    def join(self, secret):
        screen = screen_from_secret(secret)
        if not screen:
            self._set_status("That Listen Along invitation isn't valid.")
            return
        if self.fixture:
            self._set_status("Listen Along is disabled in the visual fixture.")
            return
        self._close_lounge()
        self._video, self._host_state = "", STATES["idle"]
        self.lounge = self.lounge_factory(self.settings, "Tubify", self, prefix="listenAlongRemote", role="remote", screen_id=screen)
        self.lounge.command.connect(self._command)
        self.lounge.stateChanged.connect(self._lounge_state)
        self._status = "Joining your friend…"
        self.changed.emit()
        self.lounge.start()

    @Slot()
    def stop(self):
        self.leave("Stopped listening along.")

    def leave(self, message=""):
        was = self.lounge is not None
        self._close_lounge()
        if was or message != self._status:
            self._status = message
            self.changed.emit()

    def close(self):
        self._close_lounge()

    def _close_lounge(self):
        self.silence.stop()
        self.grace.stop()
        if self.lounge:
            lounge, self.lounge = self.lounge, None
            lounge.stop()
            lounge.deleteLater()

    def _lounge_state(self, state):
        if state == "unavailable":
            self.leave("Your friend stopped sharing. Stopped listening along.")
        elif state == "retrying":
            self._set_status("Reconnecting to your friend…")
        elif state == "ready":
            self._set_status("Listening along with a friend.")

    # --- Host → follower ---------------------------------------------------------------------
    def _command(self, name, payload):
        if name not in {"nowPlaying", "onStateChange"} or not self.lounge:
            return
        state = int(number(payload.get("state"), STATES["idle"]))
        position = max(0., number(payload.get("currentTime")))
        video = str(payload.get("videoId", "")) if name == "nowPlaying" else self._video
        if (name == "nowPlaying" and not VIDEO.fullmatch(video)) or state == STATES["idle"]:
            self.leave("Your friend stopped playing. Stopped listening along.")
            return
        self._host_state = state
        if state == STATES["playing"]:
            self.silence.start()
        else:
            self.silence.stop()
        if video != self._video:
            self.grace.stop()
            self._video = video
            self.player.playTracks([{"kind": "song", "videoId": video}], 0, LABEL, position)
            if state == STATES["paused"]:
                self.player.pause()
            return
        if self.grace.isActive() or state == STATES["loading"]:
            # The listener is on another song for now; don't steer it.
            return
        if abs(number(self.player.position) - position) > DRIFT_S:
            self.player.seek(position)
        if state == STATES["playing"] and not self.player.playing:
            self.player.resume()
        elif state == STATES["paused"] and self.player.playing:
            self.player.pause()

    # --- Follower → local player ---------------------------------------------------------------
    def _track_started(self, track):
        if not self.lounge:
            return
        video = str(track.get("videoId", ""))
        if video != self._video:
            # Either autoplay ran ahead of the host or the listener picked something else.
            self.grace.start()
            return
        self.grace.stop()
        if self.worker and not track.get("title"):
            self._lookups[request_details(self.worker, self.cache_path, video)] = video

    def _lookup_done(self, identifier, result):
        video = self._lookups.pop(identifier, None)
        details = details_from(result, video) if video else {}
        if details:
            self.player.updateTrack(video, details)
