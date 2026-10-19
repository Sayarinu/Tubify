"""Native playback, queue persistence and source selection exposed to QML."""

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import tempfile

from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot

from .audio import Audio
from .queue import Queue


def write_state(path, content):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, encoding="utf-8", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


class Playback(QObject):
    changed = Signal()
    positionChanged = Signal()
    trackStarted = Signal("QVariantMap")
    stateSaveFailed = Signal()

    def __init__(self, data_dir, worker, radio_worker=None, cache_path=None, fixture=None, audio_factory=Audio, parent=None):
        super().__init__(parent)
        self.data_dir = Path(data_dir)
        self.path = self.data_dir / "playback.json"
        self.worker, self.radio_worker, self.cache_path = worker, radio_worker, str(cache_path or self.data_dir / "metadata.sqlite3")
        self.queue = Queue()
        self.audio_factory, self.audio = audio_factory, None
        self._fixture = fixture is not None
        self._position, self._duration, self._volume = 0., 0., 70
        self._playing, self._loaded, self._busy = False, False, False
        self._message, self._source_kind = "", ""
        self._request, self._radio_request = None, None
        self._prepare_request = None
        self._preparing_video = None
        self._prepared = {}
        self._retry, self._failures = False, 0
        self._start_position, self._want_paused = 0., False
        self._autoplay = True
        self._saver = ThreadPoolExecutor(max_workers=1, thread_name_prefix="playback-state")
        self._closed = False
        self.stateSaveFailed.connect(self._save_failed)
        if fixture:
            self.queue.replace(fixture.get("shelves", [{}])[0].get("items", []))
            self._duration = float(self.currentTrack.get("duration", 120))
            self._position, self._playing = self._duration * 0.6, True
        elif self.path.is_file():
            try:
                if self.path.stat().st_size <= 32 * 1024 * 1024:
                    self._position = self.queue.restore(json.loads(self.path.read_text()))
                    self._duration = float(self.currentTrack.get("duration") or 0)
            except (OSError, ValueError, TypeError):
                pass
        if worker:
            worker.succeeded.connect(self._resolved)
            worker.failed.connect(self._failed)
        if radio_worker:
            radio_worker.succeeded.connect(self._radio_result)
            radio_worker.failed.connect(self._radio_failed)
        self.save_timer = QTimer(self)
        self.save_timer.setInterval(10000)
        self.save_timer.timeout.connect(self.save)
        if not self._fixture:
            self.save_timer.start()

    @Property("QVariantMap", notify=changed)
    def currentTrack(self):
        return self.queue.current["track"] if self.queue.current else {}

    @Property("QVariantList", notify=changed)
    def entries(self):
        return [{**entry["track"], "key": entry["key"], "current": index == self.queue.index} for index, entry in enumerate(self.queue.entries)]

    @Property(bool, notify=changed)
    def hasTrack(self):
        return self.queue.current is not None

    @Property(bool, notify=changed)
    def playing(self):
        return self._playing

    @Property(bool, notify=changed)
    def busy(self):
        return self._busy

    @Property(str, notify=changed)
    def message(self):
        return self._message

    @Property(str, notify=changed)
    def sourceKind(self):
        return self._source_kind

    @Property(float, notify=positionChanged)
    def position(self):
        return self._position

    @Property(float, notify=positionChanged)
    def duration(self):
        return self._duration

    @Property(float, notify=positionChanged)
    def progress(self):
        return min(1., max(0., self._position / self._duration)) if self._duration else 0.

    @Property(str, notify=positionChanged)
    def progressText(self):
        def formatted(value):
            minutes, seconds = divmod(max(0, int(value)), 60)
            hours, minutes = divmod(minutes, 60)
            return f"{hours}:{minutes:02}:{seconds:02}" if hours else f"{minutes}:{seconds:02}"
        return f"{formatted(self._position)} / {formatted(self._duration)}"

    @Property(str, notify=changed)
    def repeat(self):
        return self.queue.repeat

    @Property(bool, notify=changed)
    def shuffled(self):
        return self.queue.shuffled

    @Property(bool, notify=changed)
    def autoplay(self):
        return self._autoplay

    @Slot("QVariantList", int)
    def playTracks(self, tracks, index=0):
        self._prepared = {}
        self.queue.replace([dict(track) for track in tracks], index)
        self._failures = 0
        self._start()

    @Slot("QVariantMap")
    def play(self, track):
        self.playTracks([track], 0)

    @Slot("QVariantList")
    def playShuffledTracks(self, tracks):
        self._prepared = {}
        self.queue.replace([dict(track) for track in tracks])
        self.queue.shuffle_all()
        self._failures = 0
        self._start()

    @Slot("QVariantList", bool)
    def enqueue(self, tracks, next=False):
        self.queue.append([dict(track) for track in tracks], next=next)
        self._queue_changed()

    @Slot(int)
    def select(self, index):
        if self.queue.select(index):
            self._failures = 0
            self._start()

    def _start(self, position=0, paused=False, force=False, damaged=False):
        if self.worker:
            if self._request is not None:
                self.worker.cancelQueued(self._request)
            if self._prepare_request is not None:
                self.worker.cancelQueued(self._prepare_request)
        if self.radio_worker and self._radio_request is not None:
            self.radio_worker.cancelQueued(self._radio_request)
        self._radio_request, self._prepare_request, self._preparing_video = None, None, None
        self._request = None
        self._busy, self._playing, self._loaded = False, False, False
        self._position, self._duration = float(position), float(self.currentTrack.get("duration") or 0)
        self._source_kind, self._message = "", ""
        self._start_position, self._want_paused = float(position), paused
        if self.audio:
            self.audio.stop()
        if not force:
            self._retry = False
        if not self.hasTrack:
            self._queue_changed()
            return
        if self._fixture and self.currentTrack.get("available") is False:
            self._message = "This song is unavailable. Skipping to the next song."
            QTimer.singleShot(0, self._skip_failed)
        elif self._fixture:
            self._playing = not paused
        elif self.worker:
            self._busy = True
            video_id = self.currentTrack.get("videoId", "")
            self._request = self.worker.request("resolve", {"data_dir": str(self.data_dir), "videoId": video_id, "force": force, "damaged": damaged, "prepared": self._prepared.pop(video_id, None), "available": self.currentTrack.get("available", True)})
        self._queue_changed()

    @Slot(int, dict)
    def _resolved(self, identifier, source):
        if identifier == self._prepare_request:
            self._prepare_request, self._preparing_video = None, None
            if source.get("videoId"):
                self._prepared = {source["videoId"]: source}
            return
        if identifier != self._request:
            return
        self._request, self._busy = None, False
        try:
            if self.audio is None:
                self.audio = self.audio_factory(parent=self)
                self.audio.updated.connect(self._audio_update)
                self.audio.ended.connect(self._ended)
                self.audio.volume(self._volume)
            self._source_kind = source["kind"]
            self.audio.load(source, self._start_position, self._want_paused)
            self._loaded, self._playing = True, not self._want_paused
            self.trackStarted.emit(self.currentTrack)
            self._prepare_next()
        except Exception:
            self._message = "The native player could not start. Check the audio device and libmpv installation."
            self._playing = False
        self.changed.emit()

    @Slot(int, dict)
    def _failed(self, identifier, error):
        if identifier == self._prepare_request:
            self._prepare_request, self._preparing_video = None, None
            return
        if identifier != self._request:
            return
        self._request, self._busy = None, False
        self._message = error.get("message", "This song could not be played.")
        self.changed.emit()
        QTimer.singleShot(0, self._skip_failed)

    @Slot(dict)
    def _audio_update(self, values):
        if self._closed:
            return
        if self._loaded and isinstance(values.get("time-pos"), (int, float)):
            self._position = max(0., float(values["time-pos"]))
            self.positionChanged.emit()
        if self._loaded and isinstance(values.get("duration"), (int, float)):
            self._duration = max(0., float(values["duration"]))
            self.positionChanged.emit()
        if "paused-for-cache" in values and self._loaded:
            self._busy = bool(values["paused-for-cache"])
            self.changed.emit()

    @Slot(bool)
    def _ended(self, failed):
        if self._closed or not self._loaded:
            return
        self._loaded = False
        if failed:
            if not self._retry:
                self._retry = True
                self._start(self._position, force=True, damaged=self._source_kind == "local")
            else:
                self._message = "This song could not be played. Skipping to the next song."
                self._skip_failed()
        else:
            self._failures = 0
            self._advance(automatic=True)

    def _skip_failed(self):
        self._loaded = False
        self._failures += 1
        if self._failures >= len(self.queue.entries) or not self.queue.advance():
            self._playing, self._busy = False, False
            self.changed.emit()
            return
        message = self._message
        self._start()
        self._message = message
        self.changed.emit()

    @Slot()
    def togglePlayback(self):
        if not self.hasTrack:
            return
        if not self._loaded and not self._fixture:
            if self._busy:
                self._want_paused = not self._want_paused
                self._playing = False
                self.changed.emit()
            else:
                self._start(0 if self._duration and self._position >= self._duration - 0.2 else self._position)
            return
        self._playing = not self._playing
        if self.audio:
            self.audio.pause(not self._playing)
        self.changed.emit()
        self.save()

    @Slot()
    def next(self):
        self._failures = 0
        self._advance()

    def _advance(self, automatic=False):
        if self.queue.advance(automatic):
            self._start()
        elif self._autoplay and self.repeat == "off" and self.radio_worker and self.hasTrack:
            self._busy, self._playing = True, False
            self._radio_request = self.radio_worker.request("catalog", {"cache_path": self.cache_path, "route": "radio", "params": {"id": self.currentTrack.get("videoId", "")}, "refresh": True})
            self.changed.emit()
        else:
            self._playing = False
            if self.audio:
                self.audio.pause(True)
            self.changed.emit()
            self.save()

    def _radio_result(self, identifier, result):
        if identifier != self._radio_request:
            return
        self._radio_request, self._busy = None, False
        video_id = self.currentTrack.get("videoId")
        tracks = [track for track in result.get("items", []) if track.get("videoId") != video_id and track.get("available", True)]
        if tracks:
            self.queue.append(tracks)
            self.queue.advance()
            self._start()
        else:
            self.changed.emit()

    def _radio_failed(self, identifier, error):
        if identifier == self._radio_request:
            self._radio_request, self._busy = None, False
            self._message = "Autoplay is unavailable. Choose a song from your queue or downloads."
            self.changed.emit()

    @Slot()
    def previous(self):
        if self._position > 3:
            self.seek(0)
        elif self.queue.previous():
            self._start()

    @Slot(float)
    def seek(self, position):
        self._position = min(self._duration, max(0., float(position)))
        if self.audio and self._loaded:
            try:
                self.audio.seek(self._position)
            except Exception:
                self._message = "This song could not seek yet. Try again after playback starts."
                self.changed.emit()
        self.positionChanged.emit()
        self.save()

    @Slot(float)
    def seekFraction(self, fraction):
        self.seek(float(fraction) * self._duration)

    @Slot(int)
    def setVolume(self, value):
        self._volume = max(0, min(100, value))
        if self.audio:
            self.audio.volume(self._volume)

    @Slot(int)
    def remove(self, index):
        if self.queue.remove(index):
            self._start()
        else:
            self._queue_changed()

    @Slot(int, int)
    def move(self, source, destination):
        self.queue.move(source, destination)
        self._queue_changed()

    @Slot(str)
    def handleAction(self, action):
        if action == "next":
            self.next()
        elif action == "previous":
            self.previous()
        elif action == "shuffle":
            self.queue.toggle_shuffle()
            self._queue_changed()
        elif action == "repeat":
            self.queue.cycle_repeat()
            self._queue_changed()

    @Slot()
    def toggleAutoplay(self):
        self._autoplay = not self._autoplay
        self.changed.emit()

    def _queue_changed(self):
        if self._loaded:
            self._prepare_next()
        self.changed.emit()
        self.positionChanged.emit()
        self.save()

    def _prepare_next(self):
        upcoming = self.queue.index + 1
        if self.worker and upcoming < len(self.queue.entries):
            track = self.queue.entries[upcoming]["track"]
            if track.get("available", True):
                video_id = track.get("videoId", "")
                if video_id in self._prepared or self._prepare_request is not None and video_id == self._preparing_video:
                    return
                if self._prepare_request is not None:
                    self.worker.cancelQueued(self._prepare_request)
                self._preparing_video = video_id
                self._prepare_request = self.worker.request("resolve", {"data_dir": str(self.data_dir), "videoId": video_id})

    @Slot()
    def _save_failed(self):
        if not self._closed:
            self._message = "Your queue could not be saved. Check available disk space and folder permissions."
            self.changed.emit()

    def save(self):
        if not self._fixture and not self._closed:
            future = self._saver.submit(write_state, self.path, json.dumps(self.queue.snapshot(self._position), separators=(",", ":")))
            future.add_done_callback(lambda completed: self.stateSaveFailed.emit() if completed.exception() else None)

    def resetSession(self):
        self._request, self._prepare_request, self._radio_request = None, None, None
        self._prepared, self._preparing_video, self._busy = {}, None, False
        if self.worker:
            self.worker.reset()
        if self._source_kind == "remote":
            self._playing, self._loaded = False, False
            if self.audio:
                self.audio.stop()
        self.changed.emit()

    def close(self):
        self.save_timer.stop()
        self.save()
        self._closed = True
        if self.audio:
            self.audio.close()
        if self.worker:
            self.worker.close()
        self._saver.shutdown(wait=True)
