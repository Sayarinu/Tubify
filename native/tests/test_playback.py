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
    optionsChanged = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.loads = []
        self.paused = False

    def load(self, source, position, paused):
        self.loads.append((source, position, paused))

    def setSpeakerFill(self, value):
        self.speaker_fill = value

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


def test_manual_queue_prefetch_and_context_switch_use_same_next_entry(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    worker = FakeWorker()
    player = Playback(tmp_path, worker, audio_factory=FakeAudio)
    player.playTracks(TRACKS)
    worker.succeeded.emit(1, {"kind": "local", "source": "/fixture/first.wav"})
    old_prepare = player._prepare_request
    manual = {"videoId": "manual12345", "title": "Manual", "duration": 80}
    player.enqueue([manual])
    assert old_prepare in worker.cancelled
    assert worker.requests[-1][1]["videoId"] == manual["videoId"]
    assert player.queue.peek()["track"] == manual
    player.playTracks(TRACKS, 1)
    assert player.currentTrack == TRACKS[1] and player.manualCount == 1
    player.next()
    assert player.currentTrack == manual and player.manualCount == 0
    assert worker.requests[-1][1]["videoId"] == manual["videoId"]
    player.close()


def test_empty_and_paused_enqueue_stay_paused_and_clear_preserves_position(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    worker = FakeWorker()
    player = Playback(tmp_path, worker, audio_factory=FakeAudio)
    player.enqueue(TRACKS)
    assert player.currentTrack == TRACKS[0] and not player.playing and not worker.requests
    assert player.duration == 120 and player.manualCount == 1
    player.resume()
    worker.succeeded.emit(1, {"kind": "local", "source": "/fixture/first.wav"})
    player.seek(18)
    player.pause()
    player.enqueue(TRACKS)
    assert not player.wantsPlayback and player.position == 18
    player.clearManualQueue()
    assert not player.manualCount and player.currentTrack == TRACKS[0] and player.position == 18
    assert not player.wantsPlayback and len(player.audio.loads) == 1
    player.close()


def test_unavailable_manual_entries_are_skipped_once_before_offline_source(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    worker = FakeWorker()
    player = Playback(tmp_path, worker, audio_factory=FakeAudio)
    player.playTracks(TRACKS)
    worker.succeeded.emit(1, {"kind": "local", "source": "/fixture/first.wav"})
    player.enqueue([{"videoId": "missingone1", "available": False}, {"videoId": "missingtwo2", "available": False}])
    player.next()
    player._skip_failed()
    player._skip_failed()
    assert player.currentTrack == TRACKS[1] and not player.manualCount
    worker.succeeded.emit(player._request, {"kind": "local", "source": "/fixture/second.wav"})
    assert player.sourceKind == "local" and player.playing
    player.close()


def test_manual_group_and_history_restore_paused_with_duplicate_keys_preserved(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    player = Playback(tmp_path, FakeWorker(), audio_factory=FakeAudio)
    player.playTracks(TRACKS)
    player.enqueue([TRACKS[0], TRACKS[0]])
    player.next()
    player.seek(15)
    saved = player.queue.snapshot(15)
    player.close()
    restored = Playback(tmp_path, FakeWorker(), audio_factory=FakeAudio)
    assert restored.queue.snapshot(restored.position) == saved and not restored.playing
    assert restored.manualCount == 1
    restored.previous()
    assert restored.currentTrack == TRACKS[0] and restored.manualCount == 1
    restored.close()


def test_current_removal_while_paused_does_not_start_playing(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    player = Playback(tmp_path, FakeWorker(), audio_factory=FakeAudio)
    player.enqueue(TRACKS)
    player.removeKey(player.entries[0]["key"])
    assert player.currentTrack == TRACKS[1] and not player.wantsPlayback
    player.close()


def test_manual_addition_while_autoplay_is_loading_cancels_stale_radio(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    worker, radio = FakeWorker(), FakeWorker()
    player = Playback(tmp_path, worker, radio_worker=radio, audio_factory=FakeAudio)
    player.playTracks(TRACKS[:1])
    worker.succeeded.emit(1, {"kind": "local", "source": "/fixture/first.wav"})
    player.audio.ended.emit(False)
    request = player._radio_request
    player.pause()
    player.enqueue(TRACKS[1:])
    assert player.currentTrack == TRACKS[1] and not player.wantsPlayback
    radio.succeeded.emit(request, {"items": [{"videoId": "staleradio1"}]})
    assert len(player.queue.source) == 1 and player._radio_request is None
    player.close()


def test_source_label_survives_pagination_manual_queue_and_restart(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    player = Playback(tmp_path, FakeWorker(), audio_factory=FakeAudio)
    player.playTracks(TRACKS, source_label="Evening mix")
    player.enqueue(TRACKS[:1])
    player.appendContext(TRACKS[1:])
    assert [entry["group"] for entry in player.entries] == ["Now playing", "Next in queue", "Next From Evening mix", "Next From Evening mix"]
    player.close()
    restored = Playback(tmp_path, FakeWorker(), audio_factory=FakeAudio)
    assert restored.entries[-1]["group"] == "Next From Evening mix"
    restored.playTracks(TRACKS)
    assert restored.entries[-1]["group"] == "Next Up"
    restored.playTracks(TRACKS, source_label="Radio")
    assert restored.entries[-1]["group"] == "Next From Radio"
    restored.close()


def test_entries_hide_history_without_changing_previous_or_snapshot(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    player = Playback(tmp_path, FakeWorker(), audio_factory=FakeAudio)
    player.playTracks([*TRACKS, {"videoId": "uvwxyz12345", "title": "Third"}], source_label="Time & Space")
    player.select(1)

    assert [(entry["title"], entry["group"], entry["movable"]) for entry in player.entries] == [
        ("Next", "Now playing", False),
        ("Third", "Next From Time & Space", True),
    ]
    assert [entry["track"]["title"] for entry in player.queue.history] == ["First"]
    assert player.queue.snapshot()["history"] == [player.queue.history[0]["key"]]
    player.previous()
    assert player.currentTrack["title"] == "First"
    assert [entry["title"] for entry in player.entries] == ["First", "Next", "Third"]
    player.close()


def test_selecting_history_key_restarts_playback_at_that_session_position(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    player = Playback(tmp_path, FakeWorker(), audio_factory=FakeAudio)
    player.playTracks(TRACKS)
    first_key = player.queue.current["key"]
    player.next()

    player.selectHistoryKey(first_key)

    assert player.currentTrack["title"] == "First"
    assert [entry["title"] for entry in player.entries] == ["First", "Next"]
    assert player.entries[0]["group"] == "Now playing"
    assert not any(entry["group"] == "Previously played" for entry in player.entries)
    player.close()


def test_dragging_source_song_into_manual_queue_updates_playback_model(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    player = Playback(tmp_path, FakeWorker(), audio_factory=FakeAudio)
    player.playTracks(TRACKS, source_label="Album")
    source_key = player.queue.remaining[0]["key"]
    player.moveToManual(source_key)
    assert player.entries[1]["key"] == source_key
    assert player.entries[1]["group"] == "Next in queue"
    assert all(entry["key"] != source_key for entry in player.queue.remaining)
    player.close()


def test_long_manual_projection_preserves_duplicate_occurrences_and_source(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    player = Playback(tmp_path, FakeWorker(), audio_factory=FakeAudio)
    player.playTracks(TRACKS, source_label="Album")
    player.enqueue([TRACKS[0]] * 10000)
    entries = player.entries
    assert len(entries) == 10002
    assert len({entry["key"] for entry in entries}) == len(entries)
    assert sum(entry["current"] for entry in entries) == 1
    assert all(entry["group"] == "Next in queue" for entry in entries[1:-1])
    assert entries[-1]["group"] == "Next From Album"
    first, last = entries[1]["key"], entries[-2]["key"]
    player.moveToManual(first, last, True)
    assert player.entries[-2]["key"] == first
    player.removeKey(last)
    assert player.manualCount == 9999
    player.clearManualQueue()
    assert [entry["title"] for entry in player.entries] == ["First", "Next"]
    player.close()


def test_empty_and_exhausted_queue_keeps_source_heading_without_history_rows(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    player = Playback(tmp_path, FakeWorker(), audio_factory=FakeAudio)
    assert player.entries == [] and player.nextGroup == "Next Up"
    player.playTracks(TRACKS, source_label="Album")
    player.next()
    assert len(player.entries) == 1 and player.nextGroup == "Next From Album"
    assert player.queue.history
    player.close()
    restored = Playback(tmp_path, FakeWorker(), audio_factory=FakeAudio)
    assert len(restored.entries) == 1 and restored.queue.history
    restored.previous()
    assert restored.currentTrack == TRACKS[0]
    restored.close()
