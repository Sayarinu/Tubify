from PySide6.QtCore import QCoreApplication, QObject, Signal

from youtube_music_native.playback import Playback


class FakeWorker(QObject):
    succeeded = Signal(int, dict)
    failed = Signal(int, dict)

    def __init__(self):
        super().__init__()
        self.requests = []

    def request(self, operation, payload):
        self.requests.append((operation, payload))
        return len(self.requests)

    def cancelQueued(self, identifier):
        pass

    def close(self):
        pass


class FakeAudio(QObject):
    updated = Signal(dict)
    ended = Signal(bool)

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
