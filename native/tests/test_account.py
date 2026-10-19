from PySide6.QtCore import QCoreApplication, QEventLoop, QObject, QTimer, Signal

from youtube_music_native.account import Account
from youtube_music_native.jobs import Worker


class FakeWorker(QObject):
    succeeded = Signal(int, dict)
    failed = Signal(int, dict)

    def __init__(self):
        super().__init__()
        self.requests = []

    def request(self, operation, payload=None):
        self.requests.append((operation, payload))
        return len(self.requests)


def test_restore_and_failed_reconnect_keep_cached_identity(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    worker = FakeWorker()
    account = Account(tmp_path / "settings.ini", worker=worker)
    app.processEvents()
    assert worker.requests == [("restore", None)]
    worker.succeeded.emit(1, {"connected": True, "profile": {"name": "Listener"}})
    account.requireReconnect("Session expired")
    assert not account.connected and account.reconnect
    account.importTauri()
    worker.failed.emit(2, {"code": "offline", "message": "Offline"})
    assert account.profile["name"] == "Listener"
    assert account.reconnect and not account.busy
    account.importTauri()
    worker.succeeded.emit(3, {"connected": True, "profile": {"name": "Listener"}})
    assert account.connected and not account.reconnect
    account.signOut()
    worker.succeeded.emit(4, {"connected": False, "profile": {}})
    assert not account.connected and account.profile == {}


def test_provider_requests_are_asynchronous_and_errors_are_sanitized():
    app = QCoreApplication.instance() or QCoreApplication([])
    worker = Worker()
    loop = QEventLoop()
    results = []
    ticks = []
    timer = QTimer()
    timer.timeout.connect(lambda: ticks.append(True))
    timer.start(1)

    def failed(identifier, error):
        results.append((identifier, error))
        if len(results) == 2:
            loop.quit()

    worker.failed.connect(failed)
    worker.request("unknown", {"private": "never echo this"})
    cancelled = worker.request("unknown")
    worker.cancelQueued(cancelled)
    worker.request("unknown")
    QTimer.singleShot(10000, loop.quit)
    loop.exec()
    timer.stop()
    worker.close()
    assert [identifier for identifier, _ in results] == [1, 3]
    assert ticks
    assert "never echo" not in str(results)
    # Headless CI may have no unlocked OS vault; neither error exposes payloads.
    assert all(error["code"] in {"AuthError", "CredentialError"} for _, error in results)
