"""Native playback, queue persistence and source selection exposed to QML."""

from collections import deque
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import time

from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot

from .audio import Audio
from .queue import Queue
from ..util import atomic_write, parse_duration
from .video import has_video


def track_duration(track):
    """Seconds from a track's duration, which may be a number or a "3:41" label."""
    return parse_duration(track.get("duration") if isinstance(track, dict) else None)


STALL_SECONDS = 25
MAX_STALL_RECOVERIES = 2
MAX_CONSECUTIVE_FAILURES = 3
EXPIRY_MARGIN = 30
# Signed sources stay in memory only, keyed by videoId, until shortly before they expire.
PREPARED_LIMIT = 50
SOURCE_MARGIN = 60
PREFETCH_AHEAD = 3
# An unanswered click older than this is presumed stuck and its worker is restarted.
STALE_REQUEST_SECONDS = 4
PREFETCH_RETRY_SECONDS = 120
# Hover and focus pre-resolution is limited to a few songs per window.
WARM_LIMIT, WARM_WINDOW = 4, 10.
VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")


class Playback(QObject):
    changed = Signal()
    # The queue list has its own signal: rebuilding and handing QML thousands of rows
    # on every pause, buffer or position change made long playlists slow to start.
    entriesChanged = Signal()
    audioOptionsChanged = Signal()
    positionChanged = Signal()
    manualQueueCleared = Signal()
    trackStarted = Signal("QVariantMap")
    stateSaveFailed = Signal()
    seeked = Signal(float)

    def __init__(self, data_dir, worker, radio_worker=None, cache_path=None, fixture=None, audio_factory=Audio, parent=None, prefetch_worker=None):
        super().__init__(parent)
        self.data_dir = Path(data_dir)
        self.path = self.data_dir / "playback.json"
        self.worker, self.radio_worker, self.cache_path = worker, radio_worker, str(cache_path or self.data_dir / "metadata.sqlite3")
        # Prefetches use their own worker when given one, so a click never waits behind them.
        self.prefetch_worker = prefetch_worker or worker
        self.queue = Queue()
        self.audio_factory, self.audio = audio_factory, None
        self._fixture = fixture is not None
        self._position, self._duration, self._volume = 0., 0., 70
        self._playing, self._loaded, self._busy = False, False, False
        self._message, self._source_kind = "", ""
        self._request, self._radio_request = None, None
        self._request_worker, self._request_started, self._request_force = None, 0., False
        self._prepare_request = None
        self._preparing_video, self._preparing_warm = None, False
        # A hovered song resolved on the idle click worker while a queue prefetch is busy.
        self._side_request, self._side_video = None, None
        self._prepared, self._local_ids, self._prefetch_failures = {}, {}, {}
        self._warm_target, self._warm_times = "", deque()
        # Whether the current song already had its one fresh-source retry after a playback failure.
        self._retried_source, self._failures = False, set()
        self._entries, self._entries_signature, self._entries_revision = [], None, 0
        self._start_position, self._want_paused = 0., False
        self._autoplay = True
        self._nonlinear_volume, self._skip_disliked = False, False
        self._speaker_fill = False
        self._audio_options = {}
        self._saver = ThreadPoolExecutor(max_workers=1, thread_name_prefix="playback-state")
        self._closed = False
        self._transport_revision, self._stopped, self._device_wait = 0, False, False
        self._source_expires, self._last_progress = 0., time.monotonic()
        self._stall_recoveries, self._consecutive_failures = 0, 0
        # Requests answered from a prefetched URL get negative identifiers, never a worker's.
        self._local_request_id = 0
        # What the queue was started from, so autoplay can continue with a matching radio.
        self._context, self._radio_prefetch, self._context_radio_failed = {}, False, False
        self.autoplay_store = None
        # Video plays only while the expanded player shows it and the user prefers it.
        self._video_surface, self._video_preferred = False, True
        self._source_video, self._request_video, self._video_failed = False, False, ""
        self.video_store = None
        self.stateSaveFailed.connect(self._save_failed)
        if fixture:
            self.queue.replace(fixture.get("shelves", [{}])[0].get("items", []))
            self._duration = track_duration(self.currentTrack) or 120.
            self._position, self._playing = self._duration * 0.6, True
        elif self.path.is_file():
            try:
                if self.path.stat().st_size <= 32 * 1024 * 1024:
                    saved = json.loads(self.path.read_text())
                    self._position = max(0., self.queue.restore(saved))
                    if isinstance(saved.get("context"), dict):
                        self._context = {key: str(value) for key, value in saved["context"].items() if key in {"kind", "playlistId"}}
            except (OSError, ValueError, TypeError):
                pass
            # A bad duration must not discard the restored queue or leave the seek bar at the start.
            self._duration = track_duration(self.currentTrack)
            if self._duration:
                self._position = min(self._position, self._duration)
            self.positionChanged.emit()
        if worker:
            worker.succeeded.connect(self._resolved)
            worker.failed.connect(self._failed)
        if prefetch_worker is not None and prefetch_worker is not worker:
            prefetch_worker.succeeded.connect(lambda identifier, source: self._resolved(identifier, source, prefetch_worker))
            prefetch_worker.failed.connect(lambda identifier, error: self._failed(identifier, error, prefetch_worker))
        if radio_worker:
            radio_worker.succeeded.connect(self._radio_result)
            radio_worker.failed.connect(self._radio_failed)
        self.changed.connect(self._check_entries)
        self.save_timer = QTimer(self)
        self.save_timer.setInterval(10000)
        self.save_timer.timeout.connect(self.save)
        self.watchdog = QTimer(self)
        self.watchdog.setInterval(5000)
        self.watchdog.timeout.connect(self._check_stall)
        if not self._fixture:
            self.save_timer.start()
            self.watchdog.start()
            QTimer.singleShot(0, self._restore_current)

    def _restore_current(self):
        if not self._closed and not self._transport_revision and self.hasTrack and self.worker:
            self._start(self._position, paused=True)

    @Property("QVariantMap", notify=changed)
    def currentTrack(self):
        return self.queue.current["track"] if self.queue.current else {}

    @Property("QVariantMap", notify=changed)
    def upcomingTrack(self):
        upcoming = self.queue.peek(automatic=True)
        return upcoming["track"] if upcoming else {}

    @Property("QVariantList", notify=changed)
    def upcomingTracks(self):
        return [entry["track"] for entry in self.queue.upcoming(2)]

    @Property(str, notify=changed)
    def nextGroup(self):
        return "Next From " + self.queue.source_label if self.queue.source_label else "Next Up"

    def _entry_groups(self):
        return (("Now playing", [self.queue.current] if self.queue.current else []),
                ("Next in queue", self.queue.manual), (self.nextGroup, self.queue.remaining))

    def _signature(self, groups):
        return (self._entries_revision,) + tuple((group, tuple(entry["key"] for entry in entries)) for group, entries in groups)

    @Property("QVariantList", notify=entriesChanged)
    def entries(self):
        groups = self._entry_groups()
        signature = self._signature(groups)
        if signature != self._entries_signature:
            self._entries_signature = signature
            self._entries = [{**entry["track"], "key": entry["key"], "current": group == "Now playing", "group": group,
                              "movable": group != "Now playing"} for group, entries in groups for entry in entries]
        return self._entries

    def _check_entries(self):
        if self._signature(self._entry_groups()) != self._entries_signature:
            self.entriesChanged.emit()

    @Property(int, notify=changed)
    def manualCount(self):
        return len(self.queue.manual)

    @Property(bool, notify=changed)
    def hasTrack(self):
        return self.queue.current is not None

    @Property(bool, notify=changed)
    def playing(self):
        return self._playing

    @Property(bool, notify=changed)
    def wantsPlayback(self):
        return self._playing or self._busy and not self._want_paused

    @Property(bool, notify=changed)
    def stopped(self):
        return self._stopped or not self.hasTrack

    @Property(bool, notify=changed)
    def busy(self):
        return self._busy

    @Property(str, notify=changed)
    def message(self):
        return self._message

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

    @Property(bool, notify=changed)
    def videoAvailable(self):
        return self._video_supported() and has_video(self.currentTrack) and self.currentTrack.get("videoId") != self._video_failed

    @Property(bool, notify=changed)
    def videoPreferred(self):
        return self._video_preferred

    @Property(bool, notify=changed)
    def showingVideo(self):
        return self._source_video and self._loaded

    @Property(QObject, notify=changed)
    def videoFrames(self):
        return getattr(self.audio, "frames", None) if self.audio else None

    def _video_supported(self):
        return not self._fixture and self.worker is not None and (self.audio is None or getattr(self.audio, "videoCapable", False))

    def _wants_video(self):
        return self._video_surface and self._video_preferred and self.videoAvailable

    def _sync_video(self):
        """Reload at the same position when the wanted mode differs from what is playing."""
        if not self.hasTrack or self._stopped or not (self._loaded or self._busy):
            self.changed.emit()
            return
        current = self._request_video if self._request is not None else self._source_video
        if self._wants_video() != current:
            self._start(self._position, paused=self._want_paused)
        else:
            self.changed.emit()

    @Slot(bool)
    def setVideoSurface(self, visible):
        if bool(visible) != self._video_surface:
            self._video_surface = bool(visible)
            self._sync_video()

    @Slot(bool)
    def setVideoPreferred(self, value):
        if bool(value) != self._video_preferred:
            self._video_preferred = bool(value)
            if self.video_store:
                self.video_store(self._video_preferred)
            self._sync_video()

    def setContext(self, context):
        """Describe where the queue came from (artist, playlist, album or radio)."""
        self._context = {key: str(value) for key, value in (context or {}).items() if key in {"kind", "playlistId"} and value}
        self._context_radio_failed = False

    def current_context(self):
        return dict(self._context)

    def setAutoplay(self, enabled):
        if bool(enabled) != self._autoplay:
            self._autoplay = bool(enabled)
            self.changed.emit()

    @Slot("QVariantList", int)
    def playTracks(self, tracks, index=0, source_label="", position=0.):
        self._transport_revision += 1
        self._context = {}
        self.queue.replace([dict(track) for track in tracks], index, source_label)
        self._failures, self._consecutive_failures = set(), 0
        self._start(max(0., float(position)))

    @Slot("QVariantMap")
    def play(self, track):
        self.playTracks([track], 0)

    def updateTrack(self, identifier, values):
        for entry in self.queue.all_entries:
            if entry["track"].get("videoId") == identifier:
                entry["track"].update(values)
        self._entries_revision += 1
        self._queue_changed()

    @Slot("QVariantList")
    def playShuffledTracks(self, tracks, source_label=""):
        self._transport_revision += 1
        self._context = {}
        self.queue.replace([dict(track) for track in tracks], source_label=source_label)
        self.queue.shuffle_all()
        self._failures, self._consecutive_failures = set(), 0
        self._start()

    @Slot("QVariantList", bool)
    def enqueue(self, tracks, next=False):
        had_track, paused = self.hasTrack, not self.wantsPlayback
        self.queue.append([dict(track) for track in tracks], next=next)
        if not had_track and self.hasTrack:
            self._position = 0.
            self._duration = track_duration(self.currentTrack)
            self._want_paused, self._playing, self._stopped = True, False, False
        if self._radio_request is not None and not self._radio_prefetch and self.queue.manual:
            entry, skipped = self._advance_entry()
            if entry:
                self._start(paused=paused)
            elif skipped:
                self._stop_disliked()
        else:
            self._queue_changed()

    def appendContext(self, tracks):
        self.queue.append_context(tracks)
        self._queue_changed()

    @Slot()
    def clearManualQueue(self):
        self.manualQueueCleared.emit()
        self.queue.clear_manual()
        self._queue_changed()

    @Slot(int)
    def select(self, index):
        self._transport_revision += 1
        if self.queue.select(index):
            self._failures, self._consecutive_failures = set(), 0
            self._start()

    def _key_index(self, key):
        return next((index for index, entry in enumerate(self.queue.entries) if entry["key"] == key), -1)

    @Slot(str)
    def selectKey(self, key):
        index = self._key_index(key)
        if index >= 0:
            self.select(index)

    @Slot(str)
    def removeKey(self, key):
        index = self._key_index(key)
        if index >= 0:
            self.remove(index)

    @Slot(str, int)
    def moveKey(self, key, direction):
        index = self._key_index(key)
        if index >= 0:
            self.move(index, index + direction)

    @Slot(str, str)
    def moveToKey(self, key, target):
        source, destination = self._key_index(key), self._key_index(target)
        if source >= 0 and destination >= 0:
            self.move(source, destination)

    @Slot(str, str, bool)
    def moveToManual(self, key, target="", after=False):
        if self.queue.move_to_manual(key, target, after):
            self._queue_changed()

    def _start(self, position=0, paused=False, force=False, damaged=False):
        self._stopped, self._device_wait = False, False
        video_id = self.currentTrack.get("videoId", "") if self.hasTrack else ""
        video = self.hasTrack and self._wants_video()
        adopt = None
        if self.worker:
            self._drop_request(force)
            if self._prepare_request is not None and self.prefetch_worker is self.worker:
                if self._preparing_video == video_id and not force and not video:
                    # The prefetch is already resolving this song; killing it would only
                    # force a cold worker start for the same answer.
                    adopt = self._prepare_request
                else:
                    self.worker.cancel(self._prepare_request)
                self._prepare_request, self._preparing_video = None, None
            # A separate prefetch worker keeps going: its answer is cached, and if it is
            # for this song it may start playback before the click's own resolve does.
            if self._side_request is not None and self._side_video == video_id and not force and not video:
                # The hovered song is already resolving on the click worker.
                adopt = self._side_request
                self._side_request, self._side_video = None, None
        if self.radio_worker and self._radio_request is not None:
            self.radio_worker.cancelQueued(self._radio_request)
        self._radio_request = None
        self._radio_prefetch = False
        self._request, self._request_worker = None, None
        self._busy, self._playing, self._loaded = False, False, False
        self._source_video, self._request_video = False, video
        self._last_progress = time.monotonic()
        if not force:
            self._stall_recoveries = 0
        self._position, self._duration = float(position), track_duration(self.currentTrack)
        self._source_kind, self._message = "", ""
        self._start_position, self._want_paused = float(position), paused
        if self.audio:
            self.audio.stop()
        if not force:
            self._retried_source = False
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
            # Video requests leave the prefetched audio source for switching back.
            prepared = None if video else self._prepared.get(video_id)
            self._request_worker, self._request_force = self.worker, bool(force or damaged)
            self._request_started = time.monotonic()
            if adopt is not None:
                self._request = adopt
            elif not force and not damaged and not video and self._usable(prepared, video_id):
                # A prefetched signed URL plays immediately without a worker round trip.
                self._local_request_id -= 1
                self._request = identifier = self._local_request_id
                QTimer.singleShot(0, lambda: self._resolved(identifier, prepared))
            else:
                self._request_worker = self._click_lane()
                self._request = self._request_worker.request("resolve", {"data_dir": str(self.data_dir), "videoId": video_id, "force": force, "damaged": damaged, "prepared": prepared, "available": self.currentTrack.get("available", True), "video": video})
        self._queue_changed()

    def _two_lanes(self):
        return self.prefetch_worker is not None and self.prefetch_worker is not self.worker

    @staticmethod
    def _lane_ready(worker):
        ready = getattr(worker, "ready", None)
        return bool(ready and ready())

    def _click_lane(self):
        """The click worker, unless an earlier resolve still occupies it and the prefetch worker is free."""
        if self._two_lanes() and not self._lane_ready(self.worker) and self._lane_ready(self.prefetch_worker):
            # The earlier resolve finishes in the background and its answer is cached.
            return self.prefetch_worker
        return self.worker

    @Slot()
    def keepWarm(self):
        """Keep the resolve workers from idling out while someone listens or browses."""
        if self._fixture or self._closed:
            return
        for worker in (self.worker, self.prefetch_worker) if self._two_lanes() else (self.worker,):
            keep = getattr(worker, "keepWarm", None)
            if keep:
                keep()

    def _drop_request(self, force):
        """Stop waiting for the previous click without restarting a healthy worker."""
        if self._request is None or self._request <= 0 or self._request_worker is None:
            return
        if force or self._request_video or time.monotonic() - self._request_started > STALE_REQUEST_SECONDS:
            self._request_worker.cancel(self._request)
        else:
            # A recent resolve finishes in the background and its answer is cached;
            # killing it would make the next click pay a cold worker start.
            self._request_worker.cancelQueued(self._request)

    def prepareAudio(self):
        """Create libmpv ahead of the first song; failures surface when playback starts."""
        if self.audio is None and not self._fixture and not self._closed:
            try:
                self._ensure_audio()
            except Exception:
                self.audio = None

    def _ensure_audio(self):
        if self.audio is None:
            audio = self.audio_factory(parent=self)
            audio.updated.connect(self._audio_update)
            audio.ended.connect(self._ended)
            audio.deviceFailed.connect(self._output_failed)
            audio.outputChanged.connect(self._output_changed)
            audio.optionsChanged.connect(self._audio_options_changed)
            audio.setSpeakerFill(self._speaker_fill)
            audio.volume(self.outputVolume)
            self.audio = audio

    @Slot(int, dict)
    def _resolved(self, identifier, source, worker=None):
        worker = worker or self.worker
        if worker is self.prefetch_worker and identifier == self._prepare_request:
            self._prepare_request, self._preparing_video, self._preparing_warm = None, None, False
            self._prefetched(source)
            return
        if self._side_request is not None and worker is self.worker and identifier == self._side_request:
            self._side_request, self._side_video = None, None
            self._prefetched(source)
            return
        if identifier != self._request or worker is not self._request_worker:
            # A superseded answer is still a valid source for its own song.
            self._remember_source(source)
            return
        self._play_source(source)

    def _prefetched(self, source):
        self._remember_source(source)
        if source.get("videoId") == self._warm_target:
            self._warm_target = ""
        video_id = self.currentTrack.get("videoId", "") if self.hasTrack else ""
        if (self._request is not None and self._request > 0 and self._request_worker is not None
                and self._two_lanes() and not self._request_video and not self._request_force
                and self._usable(source, video_id)):
            # The prefetch for the clicked song answered first; the click's own resolve
            # still finishes in the background and is cached.
            self._request_worker.cancelQueued(self._request)
            self._play_source(source)
        else:
            self._prepare_next()

    def _play_source(self, source):
        self._request, self._request_worker, self._busy = None, None, False
        self._remember_source(source)
        try:
            self._ensure_audio()
            self._source_kind = source["kind"]
            self._source_video = bool(source.get("video"))
            if hasattr(self.audio, "setVideo") and self.audio.setVideo(self._source_video) is False and self._source_video:
                # This libmpv cannot render video; the stream still plays as audio.
                self._source_video = False
                self._video_failed = self.currentTrack.get("videoId", "")
            self._source_expires = float(source.get("expires") or 0)
            self._last_progress = time.monotonic()
            self.audio.load(source, self._start_position, self._want_paused)
            self._loaded, self._playing = True, not self._want_paused
            self.trackStarted.emit(self.currentTrack)
            # Advances come from prefetches; without this the click worker idles out
            # during passive listening and the next click pays a cold start.
            self.keepWarm()
            if self._start_position:
                self.seeked.emit(self._start_position)
            self._prepare_next()
        except Exception:
            self._message = "Tubify could not start playback. Check the audio device and libmpv installation."
            self._playing = False
        self.changed.emit()

    @staticmethod
    def _fresh(source, video_id):
        return (isinstance(source, dict) and source.get("kind") == "remote" and source.get("videoId") == video_id
                and isinstance(source.get("expires"), (int, float)) and source["expires"] > time.time() + SOURCE_MARGIN
                and str(source.get("source", "")).startswith("https://"))

    def _usable(self, source, video_id):
        """Only an unexpired remote source for this song skips resolution."""
        return self._fresh(source, video_id) and self.currentTrack.get("available", True) is not False

    def _remember_source(self, source):
        if not isinstance(source, dict) or not isinstance(source.get("videoId"), str) or source.get("video"):
            return
        video_id = source["videoId"]
        if source.get("kind") == "local":
            self._local_ids.pop(video_id, None)
            self._local_ids[video_id] = True
            while len(self._local_ids) > 500:
                self._local_ids.pop(next(iter(self._local_ids)))
        elif source.get("kind") == "remote":
            # Recent sources survive new queues and worker restarts, only in memory.
            self._local_ids.pop(video_id, None)
            self._prepared.pop(video_id, None)
            self._prepared[video_id] = source
            for key in [key for key, value in self._prepared.items() if not self._fresh(value, key)]:
                self._prepared.pop(key)
            while len(self._prepared) > PREPARED_LIMIT:
                self._prepared.pop(next(iter(self._prepared)))

    @Slot(int, dict)
    def _failed(self, identifier, error, worker=None):
        worker = worker or self.worker
        if worker is self.prefetch_worker and identifier == self._prepare_request:
            failed = self._preparing_video
            self._prepare_request, self._preparing_video, self._preparing_warm = None, None, False
            self._prefetch_failed(failed)
            return
        if self._side_request is not None and worker is self.worker and identifier == self._side_request:
            failed = self._side_video
            self._side_request, self._side_video = None, None
            self._prefetch_failed(failed)
            return
        if identifier != self._request or worker is not self._request_worker:
            return
        if self._request_video:
            # A missing or blocked video stream falls back to the song's audio.
            self._video_failed = self.currentTrack.get("videoId", "")
            self._message = error.get("message", "This video could not be loaded. Playing audio instead.")
            message = self._message
            self._start(self._position, paused=self._want_paused)
            self._message = message
            self.changed.emit()
            return
        self._request, self._request_worker, self._busy = None, None, False
        self._message = error.get("message", "This song could not be played.")
        self.changed.emit()
        if not self._want_paused:
            QTimer.singleShot(0, self._skip_failed)

    def _prefetch_failed(self, failed):
        if failed:
            self._prefetch_failures[failed] = time.monotonic()
            if failed == self._warm_target:
                self._warm_target = ""
        self._prepare_next()

    @Slot(dict)
    def _audio_update(self, values):
        if self._closed:
            return
        if self._loaded and isinstance(values.get("time-pos"), (int, float)):
            position = max(0., float(values["time-pos"]))
            if position != self._position:
                self._last_progress = time.monotonic()
                if position > self._start_position + 2:
                    # The song really plays, so earlier failures were not systemic.
                    self._consecutive_failures, self._retried_source = 0, False
            self._position = position
            self.positionChanged.emit()
        if self._loaded and isinstance(values.get("duration"), (int, float)) and values["duration"] > 0:
            self._duration = float(values["duration"])
            if self.hasTrack and not track_duration(self.currentTrack):
                # Remember the length of songs whose metadata had none, so a restart
                # restores the seek bar before the stream loads again.
                self.queue.current["track"]["duration"] = round(self._duration)
                self._entries_revision += 1
                self._check_entries()
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
            if not self._retried_source:
                self._retried_source = True
                self._start(self._position, paused=self._want_paused, force=True, damaged=self._source_kind == "local")
            elif self._want_paused:
                self._playing, self._busy = False, False
                self._message = "This song could not be played. Press Play to retry."
                self.changed.emit()
            else:
                self._message = "This song could not be played. Skipping to the next song."
                self._skip_failed()
        elif self._want_paused:
            self._playing, self._busy = False, False
            self.changed.emit()
        else:
            self._failures, self._consecutive_failures = set(), 0
            self._advance(automatic=True)

    @Slot()
    def _check_stall(self):
        """Recover from mpv waiting on a dead connection; nothing else would ever notice."""
        if self._closed or not self._loaded or self._want_paused or not self.audio:
            return
        if time.monotonic() - self._last_progress < STALL_SECONDS:
            return
        if self._stall_recoveries < MAX_STALL_RECOVERIES:
            self._stall_recoveries += 1
            self._start(self._position, force=True)
        else:
            self._message = "This song stopped loading. Skipping to the next song."
            self._skip_failed()

    def _skip_failed(self):
        if self._closed or self._want_paused:
            return
        self._loaded = False
        self._consecutive_failures += 1
        if self._consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            # Auth, extractor or network failures affect every song; draining the queue hides them.
            self._consecutive_failures = 0
            self._playing, self._busy, self._want_paused = False, False, True
            reason = self._message or "Songs could not be played."
            self._message = "Several songs in a row could not be played. " + reason.replace(" Skipping to the next song.", "") + " Press Play to retry."
            self.changed.emit()
            return
        if self.queue.current:
            self._failures.add(self.queue.current["key"])
        upcoming, skipped = self._advance_entry()
        if skipped and upcoming is None:
            self._stop_disliked()
            return
        if upcoming is None or upcoming["key"] in self._failures:
            self._playing, self._busy = False, False
            self.changed.emit()
            return
        message = self._message
        self._start()
        self._message = message
        self.changed.emit()

    @Slot()
    def togglePlayback(self):
        self._transport_revision += 1
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
        if (not self._playing and self._source_kind == "remote" and self._source_expires
                and self._source_expires < time.time() + EXPIRY_MARGIN):
            # The signed URL expired while paused; resolve a fresh one at the same position.
            self._start(self._position, force=True)
            return
        self._playing = not self._playing
        self._want_paused = not self._playing
        if self.audio:
            self.audio.pause(not self._playing)
        self.changed.emit()
        self.save()

    @Slot()
    def pause(self):
        self._transport_revision += 1
        self._device_wait = False
        self._want_paused, self._playing = True, False
        if self.audio and self._loaded:
            self.audio.pause(True)
        self.changed.emit()
        self.save()

    @Slot()
    def resume(self):
        self._transport_revision += 1
        if self.wantsPlayback or not self.hasTrack:
            return
        if self._busy and not self._loaded:
            self._want_paused = False
            self.changed.emit()
        else:
            self.togglePlayback()

    @Slot()
    def stop(self):
        self._transport_revision += 1
        self._halt()
        self._position, self._stopped = 0., True
        self.positionChanged.emit()
        self.changed.emit()
        self.save()

    def _halt(self):
        if self.radio_worker and self._radio_request is not None:
            self.radio_worker.cancelQueued(self._radio_request)
        self._request, self._prepare_request, self._radio_request = None, None, None
        self._request_worker, self._preparing_video, self._busy = None, None, False
        self._side_request, self._side_video, self._preparing_warm = None, None, False
        self._playing, self._loaded = False, False
        self._radio_prefetch = False
        self._device_wait = False
        if self.worker:
            self.worker.reset()
        if self.audio:
            self.audio.stop()

    def interrupt(self):
        self._transport_revision += 1
        token = {"key": self.queue.current["key"] if self.hasTrack else None, "position": self._position, "playing": self.wantsPlayback, "revision": self._transport_revision}
        self._halt()
        self.changed.emit()
        self.save()
        return token

    def recover(self, token):
        current = self.queue.current["key"] if self.hasTrack else None
        if not self._closed and token["playing"] and current == token["key"] and token["revision"] == self._transport_revision:
            self._transport_revision += 1
            self._start(token["position"])

    @Slot()
    def _output_failed(self):
        self._device_wait = self.wantsPlayback
        self._loaded, self._playing, self._busy = False, False, False
        self._message = "The audio output is unavailable. Reconnect it and press Play to retry."
        self.changed.emit()
        self.save()

    @Slot()
    def _output_changed(self):
        if self._device_wait and not self._closed:
            self._start(self._position)

    @Slot()
    def next(self):
        self._transport_revision += 1
        self._failures, self._consecutive_failures = set(), 0
        self._advance()

    def _advance_entry(self, automatic=False):
        return self._eligible_entry(self.queue.advance(automatic))

    def _eligible_entry(self, entry):
        visited = set()
        while entry and self._skip_disliked and entry["track"].get("rating") == "DISLIKE":
            if entry["key"] in visited:
                return None, True
            visited.add(entry["key"])
            # A disliked repeat-one track must not trap the transition forever.
            entry = self.queue.advance(False)
        return entry, bool(visited)

    def _advance(self, automatic=False, paused=False):
        entry, skipped = self._advance_entry(automatic)
        if entry:
            self._start(paused=paused)
        elif skipped:
            self._stop_disliked()
        elif self._continues_with_radio():
            self._busy, self._playing = True, False
            # A radio prefetched before the last song ended is still on its way; wait for it.
            self._radio_prefetch = False
            if self._radio_request is None:
                self._request_radio()
            self.changed.emit()
        else:
            self._playing, self._stopped = False, True
            if self.audio:
                self.audio.pause(True)
            self.changed.emit()
            self.save()

    def _stop_disliked(self):
        self._halt()
        self._stopped, self._want_paused = True, True
        self._message = "No eligible songs remain. Skip disliked songs is enabled."
        self._queue_changed()

    def _continues_with_radio(self):
        return self._autoplay and self.repeat == "off" and self.radio_worker is not None and self.hasTrack

    def _radio_params(self):
        params = {"id": self.currentTrack.get("videoId", "")}
        playlist = self._context.get("playlistId", "")
        if playlist and not self._context_radio_failed and self._context.get("kind") != "radio":
            playlist = playlist[2:] if playlist.startswith("VL") else playlist
            # Artist mixes are already radios; playlists and albums get their own radio.
            params["playlistId"] = playlist if playlist.startswith("RD") else "RDAMPL" + playlist
        return params

    def _request_radio(self):
        self._radio_request = self.radio_worker.request("catalog", {"cache_path": self.cache_path, "route": "radio", "params": self._radio_params(), "refresh": True})

    def _radio_result(self, identifier, result):
        if identifier != self._radio_request:
            return
        prefetch, self._radio_prefetch = self._radio_prefetch, False
        paused = not self.wantsPlayback
        self._radio_request = None
        if not prefetch:
            self._busy = False
        heard = {entry["track"].get("videoId") for entry in self.queue.all_entries}
        tracks, seen = [], set()
        for track in result.get("items", []):
            video_id = track.get("videoId")
            if (video_id in heard or video_id in seen or not track.get("available", True)
                    or self._skip_disliked and track.get("rating") == "DISLIKE"):
                continue
            seen.add(video_id)
            tracks.append(track)
        if tracks:
            self.queue.append_context(tracks)
            self.queue.source_label = "Autoplay"
            self._context = {"kind": "radio"}
            if prefetch:
                # Queued ahead of time; the current song keeps playing and hands off gaplessly.
                self._queue_changed()
            else:
                self._advance(paused=paused)
        elif prefetch:
            return
        else:
            self._playing, self._stopped = False, True
            if self._skip_disliked and result.get("items"):
                self._message = "No eligible autoplay songs remain."
            self.changed.emit()

    def _radio_failed(self, identifier, error):
        if identifier != self._radio_request:
            return
        prefetch, self._radio_prefetch = self._radio_prefetch, False
        self._radio_request = None
        if self._context.get("playlistId") and not self._context_radio_failed:
            # Fall back to a radio seeded by the current song.
            self._context_radio_failed = True
            if not prefetch:
                self._request_radio()
            return
        if prefetch:
            return
        self._busy = False
        self._message = "Autoplay is unavailable. Choose a song from your queue or downloads."
        self.changed.emit()

    @Slot()
    def previous(self):
        self._transport_revision += 1
        if self._position > 3:
            self.seek(0)
        elif self.queue.previous():
            self._start()

    @Slot(float)
    def seek(self, position):
        self._transport_revision += 1
        self._position = min(self._duration, max(0., float(position)))
        if self.audio and self._loaded:
            try:
                self.audio.seek(self._position)
            except Exception:
                self._message = "This song could not seek yet. Try again after playback starts."
                self.changed.emit()
        self.positionChanged.emit()
        self.seeked.emit(self._position)
        self.save()

    @Slot(float)
    def seekFraction(self, fraction):
        self.seek(float(fraction) * self._duration)

    @property
    def outputVolume(self):
        return self._volume * self._volume / 100. if self._nonlinear_volume else self._volume

    def setNonlinearVolume(self, enabled):
        self._nonlinear_volume = bool(enabled)
        if self.audio:
            self.audio.volume(self.outputVolume)

    @Property("QVariantMap", notify=audioOptionsChanged)
    def audioOptions(self):
        return self._audio_options

    @Slot(dict)
    def _audio_options_changed(self, state):
        if state != self._audio_options:
            self._audio_options = state
            self.audioOptionsChanged.emit()

    def setSpeakerFill(self, enabled):
        self._speaker_fill = bool(enabled)
        if self.audio:
            self.audio.setSpeakerFill(self._speaker_fill)

    @Slot()
    def retrySpeakerFill(self):
        self.setSpeakerFill(self._speaker_fill)

    def setSkipDisliked(self, enabled):
        self._skip_disliked = bool(enabled)

    @Slot(int)
    def setVolume(self, value):
        self._volume = max(0, min(100, value))
        if self.audio:
            self.audio.volume(self.outputVolume)

    @Slot(int)
    def remove(self, index):
        paused = not self.wantsPlayback
        if self.queue.remove(index):
            entry, skipped = self._eligible_entry(self.queue.current)
            if entry or not skipped:
                self._start(paused=paused)
            else:
                self._stop_disliked()
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
        if self.autoplay_store:
            self.autoplay_store(self._autoplay)
        self._queue_changed()

    @Slot(str)
    def setRepeat(self, value):
        if value in {"off", "one", "all"} and value != self.queue.repeat:
            self.queue.repeat = value
            self._queue_changed()

    @Slot(bool)
    def setShuffle(self, value):
        if value != self.queue.shuffled:
            self.handleAction("shuffle")

    def _queue_changed(self):
        if self._loaded:
            self._prepare_next()
        self.changed.emit()
        self.positionChanged.emit()
        self.save()

    def _prepare_next(self):
        upcoming = self.queue.peek(automatic=True)
        if upcoming is None and self._loaded and self._radio_request is None and self._continues_with_radio():
            # Fetch the continuation radio while the last song plays, not after it ends.
            self._radio_prefetch = True
            self._request_radio()
        if not self.prefetch_worker or self._closed:
            return
        wanted = self._prefetch_wanted()
        if self._prepare_request is not None:
            if self._two_lanes():
                # One prefetch at a time; the next starts when this answer arrives. A
                # hovered song does not wait behind a queue prefetch, though.
                self._warm_aside(wanted)
                return
            if self._preparing_video in wanted:
                return
            self.worker.cancel(self._prepare_request)
            self._prepare_request, self._preparing_video = None, None
        if wanted:
            self._preparing_video = wanted[0]
            self._preparing_warm = wanted[0] == self._warm_target
            self._prepare_request = self.prefetch_worker.request("resolve", {"data_dir": str(self.data_dir), "videoId": wanted[0]})

    def _warm_aside(self, wanted):
        """Resolve a hovered song on the idle click worker while a queue prefetch is busy.

        Only one at a time, only while no click is pending, and only instead of, never as
        well as, the prefetch worker resolving it, so request volume stays the same.
        """
        target = self._warm_target
        if (target and wanted and wanted[0] == target and target != self._preparing_video and not self._preparing_warm
                and self._side_request is None and self._request is None and self._lane_ready(self.worker)):
            self._side_video = target
            self._side_request = self.worker.request("resolve", {"data_dir": str(self.data_dir), "videoId": target})

    def _prefetch_wanted(self):
        """Songs worth resolving ahead: a hovered song first, then the next few in the queue."""
        now = time.monotonic()
        for key in [key for key, failed in self._prefetch_failures.items() if now - failed > PREFETCH_RETRY_SECONDS]:
            self._prefetch_failures.pop(key)
        candidates = [self._warm_target] if self._warm_target else []
        if self._loaded:
            for entry in self.queue.upcoming(PREFETCH_AHEAD):
                track = entry["track"]
                if track.get("available", True) and not (self._skip_disliked and track.get("rating") == "DISLIKE"):
                    candidates.append(track.get("videoId", ""))
        current = self.currentTrack.get("videoId", "") if self.hasTrack else ""
        wanted = []
        for video_id in candidates:
            if (isinstance(video_id, str) and VIDEO_ID.fullmatch(video_id) and video_id not in wanted
                    and not self._fresh(self._prepared.get(video_id), video_id) and video_id not in self._local_ids
                    and video_id not in self._prefetch_failures and video_id != self._side_video
                    and not (video_id == current and self._request is not None)):
                wanted.append(video_id)
        # A shared worker also serves clicks, so it only ever looks one song ahead.
        return wanted if self.prefetch_worker is not self.worker else wanted[:1]

    @Slot("QVariantMap", result=bool)
    def warm(self, media):
        """Resolve a hovered or focused song ahead of a likely click; cheap and rate limited."""
        media = media or {}
        video_id = media.get("videoId", "")
        # Browsing means a click may follow: bring back a click worker that idled out.
        self.keepWarm()
        if (self._fixture or self._closed or not self.prefetch_worker or not isinstance(video_id, str) or not VIDEO_ID.fullmatch(video_id)
                or media.get("available", True) is False or media.get("downloadState") == "ready"
                or media.get("kind", "song") not in {"song", "video", ""}
                or video_id in self._local_ids or self._fresh(self._prepared.get(video_id), video_id)
                or video_id in (self._warm_target, self._preparing_video, self._side_video) or video_id in self._prefetch_failures
                or self.hasTrack and video_id == self.currentTrack.get("videoId") and (self._loaded or self._busy)):
            return False
        now = time.monotonic()
        while self._warm_times and now - self._warm_times[0] > WARM_WINDOW:
            self._warm_times.popleft()
        if len(self._warm_times) >= WARM_LIMIT:
            return False
        self._warm_times.append(now)
        self._warm_target = video_id
        self._prepare_next()
        return True

    @Slot()
    def _save_failed(self):
        if not self._closed:
            self._message = "Your queue could not be saved. Check available disk space and folder permissions."
            self.changed.emit()

    def save(self):
        if not self._fixture and not self._closed:
            future = self._saver.submit(atomic_write, self.path, json.dumps({**self.queue.snapshot(self._position), "context": self._context}, separators=(",", ":")))
            future.add_done_callback(lambda completed: self.stateSaveFailed.emit() if completed.exception() else None)

    def resetSession(self):
        self._request, self._prepare_request, self._radio_request = None, None, None
        self._request_worker, self._preparing_video, self._busy = None, None, False
        self._side_request, self._side_video, self._preparing_warm = None, None, False
        # Signed URLs belong to the old account; drop every cached one.
        self._prepared, self._local_ids, self._prefetch_failures, self._warm_target = {}, {}, {}, ""
        if self.worker:
            self.worker.reset()
        if self.prefetch_worker and self.prefetch_worker is not self.worker:
            self.prefetch_worker.reset()
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
        if self.prefetch_worker and self.prefetch_worker is not self.worker:
            self.prefetch_worker.close()
        self._saver.shutdown(wait=True)
