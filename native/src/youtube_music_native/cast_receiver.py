"""Experimental: let the YouTube Music phone app cast to Tubify (opt-in, off by default).

Phone commands drive the existing player; the player's state is reported back so the phone
shows what Tubify is playing. Local controls in Tubify always win and are reported too.
"""

import json
import math
import re
import uuid

from PySide6.QtCore import QObject, Property, QSettings, QSysInfo, QTimer, Signal, Slot

from .cast_dial import DialServer
from .lounge import Lounge

VIDEO = re.compile(r"[A-Za-z0-9_-]{11}")
MAX_CAST_TRACKS = 500
SYNC_MS = 10000
DESCRIPTION_WAIT_MS = 5000
STATES = {"idle": -1, "playing": 1, "paused": 2, "loading": 3}


def default_name():
    host = re.sub(r"[^\w .-]", "", QSysInfo.machineHostName() or "").strip()[:40]
    return f"Tubify on {host}" if host else "Tubify"


def clean_name(value):
    value = re.sub(r"[\x00-\x1f\x7f<>&\"]", "", str(value or "")).strip()[:60]
    return value or default_name()


def cast_ids(payload):
    raw = str(payload.get("videoIds", "") or "")
    ids = [value for value in raw.split(",") if VIDEO.fullmatch(value)][:MAX_CAST_TRACKS]
    if not ids and VIDEO.fullmatch(str(payload.get("videoId", ""))):
        ids = [payload["videoId"]]
    return ids


def number(value, default=0.):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


class CastReceiver(QObject):
    changed = Signal()

    def __init__(self, player, shell, settings_path, worker=None, cache_path="", parent=None, fixture=False, lounge_factory=Lounge, dial_factory=DialServer):
        super().__init__(parent)
        self.player, self.shell, self.worker, self.cache_path, self.fixture = player, shell, worker, str(cache_path), fixture
        self.settings = QSettings(str(settings_path), QSettings.Format.IniFormat)
        self._enabled = self.settings.value("cast/enabled", False, type=bool)
        self._name = clean_name(self.settings.value("cast/name", ""))
        udn = str(self.settings.value("cast/udn", "") or "")
        if not re.fullmatch(r"[0-9a-f-]{36}", udn):
            udn = str(uuid.uuid4())
            self.settings.setValue("cast/udn", udn)
        self.lounge_factory, self.dial_factory, self.udn = lounge_factory, dial_factory, udn
        self.lounge = self.dial = None
        self._status, self._remotes = "Off", 0
        self._list_id, self._ids = "", []
        self._last = None
        self._lookups = {}
        self.sync = QTimer(self)
        self.sync.setInterval(SYNC_MS)
        self.sync.timeout.connect(self._sync)
        self.volume_timer = QTimer(self)
        self.volume_timer.setSingleShot(True)
        self.volume_timer.setInterval(300)
        self.volume_timer.timeout.connect(self._send_volume)
        # A device that searches but never asks for the description was probably stopped by a firewall.
        self.discovery = QTimer(self)
        self.discovery.setSingleShot(True)
        self.discovery.setInterval(DESCRIPTION_WAIT_MS)
        self.discovery.timeout.connect(self._description_missing)
        self._found = False
        player.changed.connect(self._player_changed)
        player.seeked.connect(lambda _position: self._send_state(force=True))
        player.trackStarted.connect(self._track_started)
        shell.volumeChanged.connect(self.volume_timer.start)
        if worker:
            worker.succeeded.connect(self._lookup_done)
            worker.failed.connect(lambda identifier, _error: self._lookups.pop(identifier, None))
        if self._enabled:
            self._start()

    # --- Settings -------------------------------------------------------------------------
    @Property(bool, notify=changed)
    def enabled(self):
        return self._enabled

    @Property(str, notify=changed)
    def name(self):
        return self._name

    @Property(str, notify=changed)
    def status(self):
        return self._status

    @Property(bool, notify=changed)
    def connected(self):
        return bool(self._remotes)

    @Slot(bool)
    def setEnabled(self, value):
        value = bool(value)
        if value == self._enabled:
            return
        self._enabled = value
        self.settings.setValue("cast/enabled", value)
        self._start() if value else self._stop()
        self.changed.emit()

    @Slot(str)
    def setName(self, value):
        name = clean_name(value)
        if name == self._name:
            return
        self._name = name
        self.settings.setValue("cast/name", name)
        if self.dial:
            self.dial.name = name
        if self.lounge:
            self.lounge.rename(name)
        self.changed.emit()

    def close(self):
        self._stop()

    def _set_status(self, text):
        if text != self._status:
            self._status = text
            self.changed.emit()

    # --- Lifecycle ------------------------------------------------------------------------
    def _start(self):
        if self.fixture:
            self._set_status("Casting is unavailable in the visual fixture.")
            return
        self.dial = self.dial_factory(self._name, self.udn, parent=self)
        error = self.dial.start()
        if error:
            self.dial = None
            self._set_status(error)
            return
        self.dial.launched.connect(self._launched)
        self.dial.searched.connect(self._searched)
        self.dial.described.connect(self._described)
        self.dial.stopRequested.connect(lambda: self._remote_change("remoteDisconnected", {}))
        self.lounge = self.lounge_factory(self.settings, self._name, parent=self)
        self.lounge.command.connect(self._command)
        self.lounge.connected.connect(self._session_ready)
        self.lounge.stateChanged.connect(self._lounge_state)
        self.lounge.start()

    def _stop(self):
        self.sync.stop()
        self.discovery.stop()
        self._found = False
        for item in (self.lounge, self.dial):
            if item is not None:
                item.stop()
                item.deleteLater()
        self.lounge = self.dial = None
        self._remotes = 0
        self._last = None
        self._set_status("Off")

    def _lounge_state(self, state):
        if state == "connecting":
            self._set_status("Connecting to YouTube…")
        elif state == "retrying":
            self._set_status("Can't reach YouTube. Retrying…")
        elif state == "ready":
            self._update_ready_status()

    def _update_ready_status(self):
        if self._remotes:
            status = "Connected to a phone."
        elif self._found:
            status = f"A device on your network found Tubify. Choose “{self._name}” from Cast in the YouTube Music app."
        else:
            status = f"Ready. No device has looked for Tubify yet. Open Cast in the YouTube Music app on the same network and choose “{self._name}”."
        self._set_status(status)
        if self._remotes:
            self.sync.start()
        else:
            self.sync.stop()

    def _searched(self):
        if not self._found and not self._remotes and not self.discovery.isActive():
            self.discovery.start()

    def _described(self):
        self.discovery.stop()
        self._found = True
        if self.lounge and self.lounge.ready:
            self._update_ready_status()

    def _description_missing(self):
        if not self._found and not self._remotes and self.dial:
            self._set_status(f"A device searched for Tubify but could not connect. Check that your firewall allows Tubify on TCP port {self.dial.port}.")

    def _launched(self, code, theme):
        if self.lounge:
            self.lounge.register_pairing_code(code, lambda ok: None if ok else self._set_status("A phone could not pair. Try casting again."))

    def _session_ready(self):
        self._last = None
        self._send_now_playing()

    # --- Phone → Tubify -------------------------------------------------------------------
    def _command(self, name, payload):
        player = self.player
        if name in {"loungeStatus", "remoteConnected", "remoteDisconnected"}:
            self._remote_change(name, payload)
        elif name == "setPlaylist":
            self._set_playlist(payload)
        elif name == "updatePlaylist":
            self._update_playlist(payload)
        elif name == "play":
            player.resume()
        elif name in {"pause", "stopVideo"}:
            player.pause()
        elif name == "seekTo":
            player.seek(max(0., number(payload.get("newTime"))))
        elif name == "next":
            player.next()
        elif name == "previous":
            player.previous()
        elif name == "setVolume":
            muted = str(payload.get("muted", "")).lower() == "true"
            self.shell.setVolume(0 if muted else int(max(0., min(100., number(payload.get("volume"), self.shell.volume)))))
        elif name == "getVolume":
            self._send_volume()
        elif name == "getNowPlaying":
            self._send_now_playing()
        elif name == "setAutoplayMode":
            self._send("onAutoplayModeChanged", {"autoplayMode": "UNSUPPORTED"})

    def _remote_change(self, name, payload):
        if name == "loungeStatus":
            # Only device types are read; IDs, names and keys are never kept.
            try:
                devices = json.loads(payload.get("devices", "[]"))
            except (TypeError, ValueError):
                devices = []
            self._remotes = sum(1 for device in devices if isinstance(device, dict) and device.get("type") == "REMOTE_CONTROL") if isinstance(devices, list) else 0
        elif name == "remoteConnected":
            self._remotes += 1
        else:
            self._remotes = max(0, self._remotes - 1)
        self._update_ready_status()
        self.changed.emit()
        if self._remotes:
            self._send("onAutoplayModeChanged", {"autoplayMode": "UNSUPPORTED"})
            self._send_volume()
            self._send_now_playing()

    def _set_playlist(self, payload):
        ids = cast_ids(payload)
        if not ids:
            return
        index = min(len(ids) - 1, max(0, int(number(payload.get("currentIndex")))))
        position = max(0., number(payload.get("currentTime")))
        self._list_id = str(payload.get("listId", ""))[:200]
        if ids == self._ids and self.player.currentTrack.get("videoId") == ids[index]:
            self.player.seek(position)
            self.player.resume()
            return
        self._ids = ids
        self._last = None
        self.player.playTracks([{"kind": "song", "videoId": video} for video in ids], index, "", position)

    def _update_playlist(self, payload):
        ids = cast_ids(payload)
        if not ids or not self._ids:
            return
        added = [video for video in ids if video not in self._ids]
        self._ids = ids
        if added:
            self.player.appendContext([{"kind": "song", "videoId": video} for video in added])
        self._send_has_next()

    def _track_started(self, track):
        video = str(track.get("videoId", ""))
        if not self.worker or track.get("title") or video not in self._ids:
            return
        identifier = self.worker.request("catalog", {"cache_path": self.cache_path, "route": "radio", "params": {"id": video, "radio": False}})
        self._lookups[identifier] = video

    def _lookup_done(self, identifier, result):
        video = self._lookups.pop(identifier, None)
        if video is None:
            return
        row = next((item for item in result.get("items", []) if isinstance(item, dict) and item.get("videoId") == video), None)
        if row:
            self.player.updateTrack(video, {key: value for key, value in row.items() if key in {"title", "artist", "artists", "album", "thumbnail", "largeThumbnail", "artworkVariants", "duration", "available"}})

    # --- Tubify → phone -------------------------------------------------------------------
    def _send(self, name, payload):
        if self.lounge and self.lounge.ready:
            self.lounge.send(name, payload)

    def _state(self):
        player = self.player
        if not player.hasTrack:
            return STATES["idle"]
        if player.busy:
            return STATES["loading"]
        return STATES["playing"] if player.playing else STATES["paused"]

    def _state_payload(self):
        duration = max(0., number(self.player.duration))
        return {
            "currentTime": f"{max(0., number(self.player.position)):.3f}", "duration": f"{duration:.3f}", "cpn": "tubify",
            "loadedTime": f"{duration:.3f}", "state": self._state(), "seekableStartTime": 0, "seekableEndTime": f"{duration:.3f}",
        }

    def _send_now_playing(self):
        video = str(self.player.currentTrack.get("videoId", "")) if self.player.hasTrack else ""
        payload = self._state_payload() if VIDEO.fullmatch(video) else {}
        if payload:
            payload["videoId"] = video
            if video in self._ids:
                payload["currentIndex"] = self._ids.index(video)
                if self._list_id:
                    payload["listId"] = self._list_id
        self._send("nowPlaying", payload)
        self._send_has_next()
        self._last = (video, self._state())

    def _send_state(self, force=False):
        state = (str(self.player.currentTrack.get("videoId", "")), self._state())
        if force or state != self._last:
            self._last = state
            self._send("onStateChange", self._state_payload())

    def _send_has_next(self):
        self._send("onHasPreviousNextChanged", {"hasPrevious": str(self.player.hasTrack).lower(), "hasNext": str(bool(self.player.upcomingTrack)).lower()})

    def _send_volume(self):
        volume = int(self.shell.volume)
        self._send("onVolumeChanged", {"volume": volume, "muted": str(volume == 0).lower()})

    def _player_changed(self):
        video = str(self.player.currentTrack.get("videoId", "")) if self.player.hasTrack else ""
        if video != (self._last[0] if self._last else ""):
            self._send_now_playing()
        else:
            self._send_state()

    def _sync(self):
        if self.player.playing:
            self._send_state(force=True)
