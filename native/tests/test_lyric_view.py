from PySide6.QtCore import QCoreApplication, QObject, Signal

from youtube_music_native.lyric_view import LyricView
from test_playback import FakeWorker


class Player(QObject):
    changed = Signal()
    positionChanged = Signal()
    currentTrack = {"videoId": "abcdefghijk"}
    position = 0

    def seek(self, value):
        self.position = value
        self.positionChanged.emit()


class Account(QObject):
    sessionChanged = Signal()


def test_lyrics_are_lazy_ignore_old_tracks_and_seek_timed_lines(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    player, worker, account = Player(), FakeWorker(), Account()
    view = LyricView(account, player, tmp_path, worker)
    assert not worker.requests
    view.setActive(True)
    player.currentTrack = {"videoId": "lmnopqrstuv"}
    player.changed.emit()
    worker.succeeded.emit(1, {"videoId": "abcdefghijk", "available": True})
    assert view.busy and not view.data
    worker.succeeded.emit(2, {"videoId": "lmnopqrstuv", "available": True, "timed": True, "lines": [{"text": "Original fixture", "start": 3., "end": 5.}]})
    assert not view.busy and view.currentLine == -1
    view.seekLine(0)
    assert player.position == 3 and view.currentLine == 0
    player.seek(6)
    assert view.currentLine == -1
    account.sessionChanged.emit()
    assert worker.resets == 1
    view.close()


def test_missing_lyrics_and_retry_errors_remain_separate(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    player, worker = Player(), FakeWorker()
    view = LyricView(Account(), player, tmp_path, worker)
    view.setActive(True)
    worker.succeeded.emit(1, {"videoId": "abcdefghijk", "available": False, "lines": []})
    assert not view.busy and not view.error and not view.data["available"]
    view.refresh()
    worker.failed.emit(2, {"message": "Reconnect to load lyrics."})
    assert view.error == "Reconnect to load lyrics." and not view.busy
    view.close()
