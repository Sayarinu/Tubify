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

from .lounge import Lounge, SCREEN_ID, state_payload

SECRET_PREFIX = "tl1:"
SYNC_MS = 10000
NAME = "Tubify Listen Along"
VIDEO = re.compile(r"[A-Za-z0-9_-]{11}")


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
