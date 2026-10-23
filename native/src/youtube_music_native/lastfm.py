"""Opt-in listening accounting; networking and keyring access stay in a worker."""

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import time
from uuid import uuid4

from PySide6.QtCore import QObject, Property, QSettings, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

from .jobs import Worker
from .lastfm_service import metadata
from .playback import write_state


class LastFm(QObject):
    changed = Signal()
    spoolFailed = Signal()

    def __init__(self, player, settings_path, data_dir, parent=None, worker_factory=Worker, clock=time.monotonic, wall_clock=time.time, browser=QDesktopServices.openUrl, fixture=False):
        super().__init__(parent)
        self.player, self.data_dir = player, str(data_dir)
        self.settings = QSettings(str(settings_path), QSettings.Format.IniFormat)
        self._enabled = self.settings.value("lastfm/enabled", False, type=bool) and not fixture
        self._percent = max(50, min(100, self.settings.value("lastfm/thresholdPercent", 50, type=int)))
        self._worker_factory, self._worker, self._clock, self._wall_clock = worker_factory, None, clock, wall_clock
        self._browser, self._fixture = browser, fixture
        self._requests, self._unsaved, self._status = {}, {}, {}
        self._message, self._closed, self._listen = "", False, None
        self._spool_path = Path(data_dir) / "lastfm-pending.json"
        self._saver, self._restored, self._spool_loaded = None, {}, False
        self.spoolFailed.connect(self._spool_failed)
        self._last_time, self._last_position, self._was_playing = clock(), float(player.position), False
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)
        self.retry_timer = QTimer(self)
        self.retry_timer.setSingleShot(True)
        self.retry_timer.setInterval(60000)
        self.retry_timer.timeout.connect(self.retry)
        player.trackStarted.connect(self._started)
        player.changed.connect(self._state_changed)
        player.seeked.connect(self._seeked)
        if self._enabled:
            self._load_spool()
            self._request("status")

    @Property(bool, notify=changed)
    def enabled(self):
        return self._enabled

    @Property(bool, notify=changed)
    def configured(self):
        return bool(self._status.get("configured"))

    @Property(bool, notify=changed)
    def connected(self):
        return bool(self._status.get("connected"))

    @Property(bool, notify=changed)
    def awaitingApproval(self):
        return bool(self._status.get("awaitingApproval"))

    @Property(str, notify=changed)
    def username(self):
        return self._status.get("username", "")

    @Property(str, notify=changed)
    def message(self):
        return self._message

    @Property(int, notify=changed)
    def pendingCount(self):
        return int(self._status.get("pendingCount", 0)) + len(self._unsaved)

    @Property(bool, notify=changed)
    def busy(self):
        return any(action in {"status", "configure", "authorize", "complete", "logout"} for action, _ in self._requests.values())

    @Property(int, notify=changed)
    def thresholdPercent(self):
        return self._percent

    @Slot(int)
    def setThresholdPercent(self, value):
        self._percent = max(50, min(100, int(value)))
        self.settings.setValue("lastfm/thresholdPercent", self._percent)
        self.changed.emit()

    @Slot(bool)
    def setEnabled(self, enabled):
        enabled = bool(enabled)
        if enabled == self._enabled or enabled and not self.connected:
            return
        self._enabled = enabled
        self.settings.setValue("lastfm/enabled", enabled)
        self._listen = None
        if not enabled:
            self.timer.stop()
            self.retry_timer.stop()
            self._requests.clear()
            self._save_spool()
            if self._worker:
                self._worker.close()
                self._worker = None
        else:
            self._load_spool()
            self._adopt_spool()
            self._started(self.player.currentTrack)
            self.retry()
        self._state_changed()
        self.changed.emit()

    @Slot()
    def refresh(self):
        if not self.busy:
            self._request("status")

    @Slot(str, str)
    def configure(self, api_key, secret):
        if self.busy:
            return
        self.setEnabled(False)
        self._discard_spool()
        self._request("configure", {"api_key": api_key, "secret": secret})

    @Slot()
    def authorize(self):
        if self.configured and not self.busy:
            self._request("authorize")

    @Slot()
    def complete(self):
        if self.awaitingApproval and not self.busy:
            self._request("complete")

    @Slot()
    def logout(self):
        if self.busy:
            return
        self.setEnabled(False)
        self._discard_spool()
        self._request("logout")

    @Slot()
    def retry(self):
        if not self._enabled or not self.connected or self._requests:
            return
        if self._unsaved:
            self._request("listen", next(iter(self._unsaved.values())))
        else:
            self._request("flush")

    def _request(self, action, payload=None):
        if self._closed:
            return
        if self._fixture:
            self._message = "Last.fm connections are unavailable in the synthetic preview."
            self.changed.emit()
            return
        if self._worker is None:
            self._worker = self._worker_factory(self, idle_ms=15000)
            self._worker.succeeded.connect(self._result)
            self._worker.failed.connect(self._failed)
        payload = payload or {}
        identifier = self._worker.request("lastfm", {"action": action, "data_dir": self.data_dir, **payload})
        self._requests[identifier] = (action, payload if action == "listen" else {})
        self.changed.emit()

    def _result(self, identifier, result):
        request = self._requests.pop(identifier, None)
        if request is None:
            return
        action, payload = request
        if action == "complete" and result.get("username", "").casefold() != self.username.casefold():
            self._discard_spool()
            self._listen = None
        self._status.update({key: result[key] for key in ("configured", "connected", "username", "awaitingApproval", "pendingCount") if key in result})
        self._message = result.get("message", "")
        self._adopt_spool()
        if action == "listen":
            self._unsaved.pop(payload["id"], None)
            self._save_spool()
        if result.get("reconnect"):
            self._status["connected"] = False
        if action == "authorize" and result.get("authUrl"):
            if not self._browser(QUrl(result["authUrl"])):
                self._message = "The browser could not be opened. Check your default browser and start sign-in again."
        if action == "complete":
            self._message = "Signed in. Enable listening updates when you are ready."
        self._state_changed()
        self.changed.emit()
        if self._enabled and self.connected and (self.pendingCount or action in {"status", "complete"}):
            self.retry_timer.start(60000 if result.get("retry") else 200)

    def _failed(self, identifier, error):
        request = self._requests.pop(identifier, None)
        if request is None:
            return
        action, payload = request
        self._message = error.get("message", "Last.fm could not complete this request. Retry when connected.")
        if error.get("code") in {"lastfm_auth", "lastfm_setup"}:
            self._status["connected"] = False
        if action == "listen":
            if error.get("code") in {"lastfm_metadata", "lastfm_rejected"}:
                self._unsaved.pop(payload["id"], None)
            else:
                self._unsaved[payload["id"]] = payload
            self._save_spool()
        if self._enabled and self.connected and (action in {"listen", "flush"} or self.pendingCount):
            self.retry_timer.start(60000)
        self._state_changed()
        self.changed.emit()

    def _started(self, track):
        identity = str(track.get("videoId") or track.get("id") or "")
        if self._listen and self._listen["identity"] == identity and self.player.position > 1:
            # Source refresh/device recovery resumes the same listen.
            self._seeked(self.player.position)
            return
        self._listen = {"id": uuid4().hex, "identity": identity, "track": dict(track), "elapsed": 0., "timestamp": 0, "submitted": False, "announced": False, "lastActive": self._clock()}
        self._seeked(self.player.position)
        self._state_changed()

    def _seeked(self, _position):
        self._last_time, self._last_position = self._clock(), float(self.player.position)
        self._was_playing = self.player.playing and not self.player.busy

    def _state_changed(self):
        if self._closed:
            return
        self._tick()
        active = self._enabled and self.connected and self.player.playing and not self.player.busy
        if active and not self.timer.isActive():
            self.timer.start()
        elif not active:
            self.timer.stop()

    def _tick(self):
        now, position = self._clock(), float(self.player.position)
        active = self._enabled and self.connected and self.player.playing and not self.player.busy
        delta, progress = now - self._last_time, position - self._last_position
        if active and self._listen is None and metadata(self.player.currentTrack):
            self._started(self.player.currentTrack)
            return
        listen = self._listen
        if active and listen:
            if not self._was_playing and now - listen["lastActive"] >= 30:
                listen["announced"] = False
            listen["lastActive"] = now
        # Seeks, buffering, suspension and long gaps cannot manufacture listening time.
        if active and self._was_playing and listen and 0 < delta <= 5 and 0 < progress <= delta + 1:
            listen["elapsed"] += min(delta, progress)
            if not listen["timestamp"]:
                listen["timestamp"] = int(self._wall_clock() - min(delta, progress))
            if not listen["announced"] and metadata(listen["track"]):
                listen["announced"] = True
                self._request("now_playing", {"track": listen["track"]})
            duration = float(self.player.duration)
            if duration > 30 and metadata(listen["track"]) and not listen["submitted"] and listen["elapsed"] >= min(duration * self._percent / 100, 240):
                listen["submitted"] = True
                payload = {"id": listen["id"], "timestamp": listen["timestamp"], "track": {**listen["track"], "duration": duration}}
                self._unsaved[listen["id"]] = payload
                self._save_spool()
                self._request("listen", payload)
        self._last_time, self._last_position, self._was_playing = now, position, active

    def _load_spool(self):
        if self._spool_loaded or self._fixture:
            return
        self._spool_loaded = True
        try:
            with self._spool_path.open(encoding="utf-8") as handle:
                raw = handle.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise ValueError()
            value = json.loads(raw)
            rows = value.get("listens")
            if not isinstance(value.get("owner"), str) or not isinstance(rows, list) or len(rows) > 1000:
                raise ValueError()
            if any(not isinstance(row, dict) or not isinstance(row.get("id"), str) or not re.fullmatch(r"[a-f0-9]{32}", row["id"]) or not isinstance(row.get("timestamp"), int) or not metadata(row.get("track")) for row in rows):
                raise ValueError()
            self._restored = value
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError, AttributeError):
            self._message = "Pending Last.fm listens could not be read. Check local storage."

    def _adopt_spool(self):
        if not self._restored or not self.username:
            return
        if self._restored["owner"].casefold() == self.username.casefold():
            self._unsaved.update({row["id"]: row for row in self._restored["listens"]})
        self._restored = {}
        self._save_spool()

    def _save_spool(self):
        if self._fixture or self._restored:
            return
        while len(self._unsaved) > 1000:
            self._unsaved.pop(next(iter(self._unsaved)))
        if self._saver is None:
            if not self._unsaved and not self._spool_path.exists():
                return
            self._saver = ThreadPoolExecutor(max_workers=1, thread_name_prefix="lastfm-state")
        # Persist only public scrobble metadata, never provider/session fields.
        rows = []
        for row in self._unsaved.values():
            track = metadata(row["track"])
            if track:
                rows.append({"id": row["id"], "timestamp": row["timestamp"], "track": {"title": track["track"], "artist": track["artist"], "albumName": track.get("album", ""), "duration": track.get("duration", 0)}})
        content = json.dumps({"owner": self.username, "listens": rows}, separators=(",", ":"))
        future = self._saver.submit(write_state, self._spool_path, content)
        future.add_done_callback(lambda completed: self.spoolFailed.emit() if completed.exception() else None)

    def _discard_spool(self):
        self._unsaved.clear()
        self._restored = {}
        self._spool_loaded = True
        self._save_spool()

    def _spool_failed(self):
        if not self._closed:
            self._message = "Pending Last.fm listens could not be saved. Check available disk space and folder permissions."
            self.changed.emit()

    def close(self):
        if self._closed:
            return
        self._tick()
        self._closed = True
        self.timer.stop()
        self.retry_timer.stop()
        if self._worker:
            self._worker.close()
        if self._saver:
            self._saver.shutdown(wait=True)
