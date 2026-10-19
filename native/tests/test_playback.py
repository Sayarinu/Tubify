from PySide6.QtCore import QCoreApplication, QObject, Signal

from youtube_music_native.playback import Playback


class FakeWorker(QObject):
    succeeded = Signal(int, dict)
    failed = Signal(int, dict)

    def __init__(self):
        super().__init__()
        self.requests = []
        self.resets = 0
        self.cancelled = []

    def request(self, operation, payload):
        self.requests.append((operation, payload))
        return len(self.requests)

    def cancelQueued(self, identifier):
        pass

    def cancel(self, identifier):
        self.cancelled.append(identifier)

    def close(self):
        pass

    def reset(self):
        self.resets += 1


class FakeAudio(QObject):
    updated = Signal(dict)
    ended = Signal(bool)
    deviceFailed = Signal()
    outputChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.loads = []
        self.paused = False

    def load(self, source, position, paused):
        self.loads.append((source, position, paused))

    def volume(self, value):
        self.level = value

    def pause(self, value):
        self.paused = value

    def seek(self, value):
        self.updated.emit({"time-pos": value})

    def stop(self):
        pass

    def close(self):
        pass


TRACKS = [{"videoId": "abcdefghijk", "title": "First", "duration": 120}, {"videoId": "lmnopqrstuv", "title": "Next", "duration": 180}]


def test_queue_restores_paused_and_stale_resolver_results_cannot_start_audio(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    worker = FakeWorker()
    player = Playback(tmp_path, worker, audio_factory=FakeAudio)
    player.playTracks(TRACKS)
    player.next()
    worker.succeeded.emit(1, {"kind": "remote", "source": "https://private.invalid/signed"})
    assert player.audio is None
    worker.succeeded.emit(2, {"kind": "local", "source": "/fixture/track.opus"})
    assert player.currentTrack["title"] == "Next" and player.playing
    player.seek(32)
    player.togglePlayback()
    assert player.audio.paused
    player.close()
    restored = Playback(tmp_path, FakeWorker(), audio_factory=FakeAudio)
    assert restored.currentTrack["title"] == "Next"
    assert restored.position == 32 and not restored.playing and restored.audio is None
    assert "private.invalid" not in restored.path.read_text()
    restored.close()


def test_manual_play_cancels_active_prefetch_and_ignores_its_late_result(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    worker = FakeWorker()
    player = Playback(tmp_path, worker, audio_factory=FakeAudio)
    player.playTracks(TRACKS)
    worker.succeeded.emit(1, {"kind": "local", "source": "/fixture/first.wav"})
    prefetch = player._prepare_request
    assert prefetch is not None
    player.play(TRACKS[0])
    assert prefetch in worker.cancelled
    worker.succeeded.emit(prefetch, {"kind": "remote", "source": "https://media.invalid/stale", "videoId": TRACKS[1]["videoId"]})
    assert not player._prepared
    worker.succeeded.emit(len(worker.requests), {"kind": "local", "source": "/fixture/first.wav"})
    assert player.sourceKind == "local" and player.playing
    player.close()


def test_restored_queue_preloads_paused_and_preserves_position_when_offline(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    seed = Playback(tmp_path, FakeWorker(), audio_factory=FakeAudio)
    seed.playTracks(TRACKS)
    seed.seek(32)
    seed.close()
    worker = FakeWorker()
    restored = Playback(tmp_path, worker, audio_factory=FakeAudio)
    app.processEvents()
    assert worker.requests[-1][1]["videoId"] == TRACKS[0]["videoId"]
    worker.failed.emit(len(worker.requests), {"message": "Offline"})
    app.processEvents()
    assert not restored.playing and restored.currentTrack == TRACKS[0] and restored.position == 32
    restored.resume()
    source = {"kind": "remote", "source": "https://media.invalid/first", "videoId": TRACKS[0]["videoId"]}
    worker.succeeded.emit(len(worker.requests), source)
    assert restored.playing and restored.audio.loads[-1][1:] == (32, False)
    restored.close()


def test_restored_audio_is_loaded_paused_until_play_without_another_resolution(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    seed = Playback(tmp_path, FakeWorker(), audio_factory=FakeAudio)
    seed.playTracks(TRACKS[:1])
    seed.close()
    worker = FakeWorker()
    restored = Playback(tmp_path, worker, audio_factory=FakeAudio)
    app.processEvents()
    worker.succeeded.emit(1, {"kind": "local", "source": "/fixture/first.wav"})
    assert not restored.playing and restored.audio.loads[-1][2] is True
    restored.resume()
    assert restored.playing and not restored.audio.paused and len(worker.requests) == 1
    restored.close()


def test_desktop_play_unpauses_loaded_audio_while_waiting_for_cache(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    worker = FakeWorker()
    player = Playback(tmp_path, worker, audio_factory=FakeAudio)
    try:
        player.playTracks(TRACKS[:1])
        worker.succeeded.emit(1, {"kind": "local", "source": "/fixture/first.wav"})
        player.pause()
        player.audio.updated.emit({"paused-for-cache": True})
        player.resume()
        assert player.playing and not player.audio.paused
        assert not player._want_paused and len(worker.requests) == 1
        player.audio.updated.emit({"paused-for-cache": False})
        assert player.playing and not player.busy
    finally:
        player.close()


def test_failed_paused_preload_retries_paused_and_keeps_the_queue_selection(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    seed = Playback(tmp_path, FakeWorker(), audio_factory=FakeAudio)
    seed.playTracks(TRACKS)
    seed.seek(32)
    seed.close()
    worker = FakeWorker()
    player = Playback(tmp_path, worker, audio_factory=FakeAudio)
    source = {"kind": "remote", "source": "https://media.invalid/first", "videoId": TRACKS[0]["videoId"]}
    try:
        app.processEvents()
        worker.succeeded.emit(1, source)
        player.audio.ended.emit(True)
        worker.succeeded.emit(len(worker.requests), source)
        assert not player.playing and player.audio.loads[-1][1:] == (32, True)
        player.audio.ended.emit(True)
        assert not player.playing and not player.busy
        assert player.currentTrack == TRACKS[0] and player.position == 32
    finally:
        player.close()


def test_restoring_at_end_of_song_keeps_playback_paused_and_replays_on_play(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    seed = Playback(tmp_path, FakeWorker(), audio_factory=FakeAudio)
    seed.playTracks(TRACKS)
    seed.seek(TRACKS[0]["duration"])
    seed.close()
    worker = FakeWorker()
    player = Playback(tmp_path, worker, audio_factory=FakeAudio)
    source = {"kind": "local", "source": "/fixture/first.wav"}
    try:
        app.processEvents()
        worker.succeeded.emit(1, source)
        player.audio.ended.emit(False)
        assert not player.playing and player.currentTrack == TRACKS[0]
        player.resume()
        worker.succeeded.emit(len(worker.requests), source)
        assert player.playing and player.audio.loads[-1][1:] == (0, False)
    finally:
        player.close()


def test_failed_source_retries_once_then_skips_and_prepares_upcoming(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    worker = FakeWorker()
    player = Playback(tmp_path, worker, audio_factory=FakeAudio)
    player.playTracks(TRACKS)
    worker.succeeded.emit(1, {"kind": "remote", "source": "https://media.invalid/first"})
    assert worker.requests[1][1]["videoId"] == TRACKS[1]["videoId"]
    player.audio.ended.emit(True)
    retry_id = len(worker.requests)
    assert worker.requests[-1][1]["force"] is True
    worker.succeeded.emit(retry_id, {"kind": "remote", "source": "https://media.invalid/retry"})
    player.audio.ended.emit(True)
    assert player.currentTrack["title"] == "Next"
    assert not worker.requests[-1][1]["force"]
    player.close()


def test_previous_reuses_recent_source_after_worker_hibernation_without_saving_it(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    worker = FakeWorker()
    player = Playback(tmp_path, worker, audio_factory=FakeAudio)
    first = {"kind": "remote", "source": "https://media.invalid/first-signed", "videoId": TRACKS[0]["videoId"], "expires": 4102444800, "headers": []}
    upcoming = {**first, "source": "https://media.invalid/next-signed", "videoId": TRACKS[1]["videoId"]}
    player.playTracks(TRACKS)
    worker.succeeded.emit(1, first)
    worker.succeeded.emit(player._prepare_request, upcoming)
    player.next()
    assert worker.requests[-1][1]["prepared"] == upcoming
    worker.succeeded.emit(len(worker.requests), upcoming)
    player.previous()
    assert worker.requests[-1][1]["prepared"] == first
    player.close()
    assert "media.invalid" not in player.path.read_text()


def test_stale_autoplay_result_cannot_replace_a_new_manual_queue(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    worker, radio = FakeWorker(), FakeWorker()
    player = Playback(tmp_path, worker, radio_worker=radio, audio_factory=FakeAudio)
    player.playTracks(TRACKS, 1)
    worker.succeeded.emit(1, {"kind": "local", "source": "/fixture/track.opus"})
    player.audio.ended.emit(False)
    assert radio.requests[-1][1]["route"] == "radio"
    player.play(TRACKS[0])
    radio.succeeded.emit(1, {"items": [TRACKS[1]]})
    assert len(player.entries) == 1 and player.currentTrack["title"] == "First"
    player.close()


def test_session_reset_keeps_local_audio_and_stops_old_remote_credentials(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    worker = FakeWorker()
    player = Playback(tmp_path, worker, audio_factory=FakeAudio)
    player.playTracks(TRACKS[:1])
    worker.succeeded.emit(1, {"kind": "local", "source": "/fixture/track.opus"})
    player.resetSession()
    assert player.playing and worker.resets == 1
    player.playTracks(TRACKS[:1])
    worker.succeeded.emit(2, {"kind": "remote", "source": "https://media.invalid/stream"})
    player.resetSession()
    assert not player.playing and worker.resets == 2
    assert player.currentTrack["title"] == "First"
    player.close()


def test_duplicate_queue_edits_preserve_current_audio_and_position(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    worker = FakeWorker()
    player = Playback(tmp_path, worker, audio_factory=FakeAudio)
    player.playTracks([TRACKS[0], TRACKS[0], TRACKS[1]])
    worker.succeeded.emit(1, {"kind": "local", "source": "/fixture/track.opus"})
    player.seek(37)
    first, duplicate, last = [entry["key"] for entry in player.entries]
    player.moveToKey(first, last)
    player.removeKey(duplicate)
    assert player.queue.current["key"] == first
    assert player.position == 37 and player.playing and len(player.audio.loads) == 1
    player.moveKey("stale", -1)
    player.removeKey("stale")
    assert len(player.entries) == 2
    player.removeKey(first)
    assert player.currentTrack == TRACKS[1] and player.position == 0
    player.close()
