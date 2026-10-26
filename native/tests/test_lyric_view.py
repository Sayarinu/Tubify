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


def test_provider_preferences_persist_and_stale_lookup_cannot_replace_current_options(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    player, worker = Player(), FakeWorker()
    view = LyricView(Account(), player, tmp_path, worker)
    view.setActive(True)
    assert not worker.requests[-1][1]["options"]["external"]
    view.setOption("external", True)
    assert worker.cancelled == [1] and len(worker.requests) == 2
    worker.succeeded.emit(1, {"videoId": "abcdefghijk", "available": True, "timed": False, "lines": [{"text": "Stale", "start": -1., "end": -1.}]})
    assert not view.data and view.busy
    view.moveProvider("better", -1)
    view.moveProvider("better", -1)
    view.setProviderEnabled("unison", False)
    view.setOption("timestamps", True)
    view.setOption("style", "word")
    count = len(worker.requests)
    view.setOption("autoOpen", True)
    assert len(worker.requests) == count, "Display-only options should not refetch lyrics"
    opened = []
    view.openRequested.connect(lambda: opened.append(True))
    view.playbackStarted(player.currentTrack)
    assert opened == [True]
    view.close()
    restored = LyricView(Account(), Player(), tmp_path, FakeWorker())
    assert restored.options["external"] and restored.options["timestamps"] and restored.options["style"] == "word"
    assert [row["id"] for row in restored.providers] == ["better", "lrclib", "unison"]
    assert not restored.providers[-1]["enabled"]
    restored.close()


def test_word_style_uses_real_timestamps_and_escapes_provider_text(tmp_path):
    from youtube_music_native.lyric_formats import ttml
    app = QCoreApplication.instance() or QCoreApplication([])
    player, worker = Player(), FakeWorker()
    view = LyricView(Account(), player, tmp_path, worker)
    view.setActive(True)
    result = ttml('<tt><p begin="0" end="10"><span begin="0" end="3">&lt;First&gt;</span> <span begin="7" end="10">second</span></p></tt>')
    worker.succeeded.emit(1, {**result, "videoId": "abcdefghijk", "source": "Fixture"})
    view.setOption("style", "word")
    rendered = view.styledLine(0, "#FFFFFF", "#AAAAAA")
    assert '<font color="#FFFFFF">&lt;First&gt;</font>' in rendered
    assert '<font color="#AAAAAA">second</font>' in rendered
    revision = view.timingRevision
    player.seek(6.99)
    assert view.timingRevision == revision, "No supplied word boundary was crossed"
    player.seek(7.)
    assert view.timingRevision > revision and '<font color="#FFFFFF">second</font>' in view.styledLine(0, "#FFFFFF", "#AAAAAA")
    view.setOption("style", "syllable")
    assert view.styledLine(0, "#FFFFFF", "#AAAAAA") == "&lt;First&gt; second", "Word data must not manufacture syllable timing"
    view._data["lines"][0].pop("words")
    view.setOption("style", "word")
    assert view.styledLine(0, "#FFFFFF", "#AAAAAA") == "&lt;First&gt; second"
    view.close()


def test_key_operations_never_persist_secret_in_settings_and_refresh_after_save(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    worker = FakeWorker()
    view = LyricView(Account(), Player(), tmp_path, worker)
    view.setActive(True)
    worker.succeeded.emit(1, {"videoId": "abcdefghijk", "available": False, "timed": False, "lines": []})
    view.keyAction("save", "fixture-secret")
    assert view.keyBusy and worker.requests[-1] == ("lyrics_key", {"action": "save", "value": "fixture-secret"})
    worker.succeeded.emit(2, {"hasKey": True})
    assert view.hasKey and not view.keyBusy and worker.requests[-1][1]["refresh"]
    view._settings.sync()
    settings = tmp_path / "settings.ini"
    if settings.exists():
        assert "fixture-secret" not in settings.read_text()
    assert "fixture-secret" not in view.keyMessage
    view.close()


def test_session_reset_clears_pending_key_operation_and_ignores_late_result(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    worker, account = FakeWorker(), Account()
    view = LyricView(account, Player(), tmp_path, worker)
    notified = []
    view.keyChanged.connect(lambda: notified.append(True))
    view.keyAction("save", "fixture-secret")
    assert view.keyBusy
    account.sessionChanged.emit()
    assert not view.keyBusy and view.keyMessage == "" and worker.resets == 1
    assert len(notified) == 2
    worker.succeeded.emit(1, {"hasKey": True})
    worker.failed.emit(1, {"message": "Old failure"})
    assert not view.hasKey and view.keyMessage == "" and len(notified) == 2
    view.keyAction("status")
    assert view.keyBusy and worker.requests[-1] == ("lyrics_key", {"action": "status", "value": ""})
    worker.succeeded.emit(2, {"hasKey": True})
    assert view.hasKey and not view.keyBusy
    view.close()
