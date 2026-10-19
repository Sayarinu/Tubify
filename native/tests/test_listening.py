from types import SimpleNamespace

from PySide6.QtCore import QCoreApplication, QObject, Signal

from youtube_music_native.listening import Listening


class Player(QObject):
    trackStarted = Signal(dict)
    positionChanged = Signal()
    currentTrack = {"videoId": "abcdefghijk"}
    playing, duration, position = True, 180, 0


class Worker(QObject):
    failed = Signal(int, dict)
    succeeded = Signal(int, dict)

    def __init__(self):
        super().__init__()
        self.requests, self.cancelled = [], []

    def request(self, operation, payload):
        self.requests.append((operation, payload))
        return len(self.requests)

    def cancelQueued(self, identifier):
        self.cancelled.append(identifier)


class Account(QObject):
    sessionChanged = Signal()
    connected, busy = True, False


def test_history_records_after_progress_once_and_does_not_queue_while_disconnected(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    account, player, worker = Account(), Player(), Worker()
    account.worker = worker
    listening = Listening(account, player, tmp_path / "cache.sqlite3")
    player.position = 2
    player.positionChanged.emit()
    assert not worker.requests
    player.position = 5
    player.positionChanged.emit()
    player.positionChanged.emit()
    assert len(worker.requests) == 1 and worker.requests[0][0] == "account_history"
    account.sessionChanged.emit()
    assert worker.cancelled == [1]
    player.trackStarted.emit(player.currentTrack)
    account.connected = False
    player.positionChanged.emit()
    account.connected, account.busy = True, True
    player.positionChanged.emit()
    assert len(worker.requests) == 1
