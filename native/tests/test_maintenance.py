import io
import json
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QObject, QUrl, Signal
import pytest

from youtube_music_native.maintenance import Maintenance, lookup_release, perform, public_diagnostics


class Worker(QObject):
    succeeded = Signal(int, dict)
    failed = Signal(int, dict)
    def __init__(self, parent, idle_ms):
        super().__init__(parent)
        self.requests, self.closed = [], False
    def request(self, operation, payload):
        self.requests.append((operation, payload))
        return len(self.requests)
    def close(self):
        self.closed = True


def opener(rows):
    return lambda *args, **kwargs: io.BytesIO(json.dumps(rows).encode())


def test_release_filters_wrapper_drafts_and_prerelease():
    rows = [{"tag_name": "v9.0.0"}, {"tag_name": "native-v0.1.1"}, {"tag_name": "native-v0.2.0"}, {"tag_name": "native-v8.0.0", "draft": True}, {"tag_name": "native-v7.0.0", "prerelease": True}, {"tag_name": "native-v0.3.0-beta"}]
    assert lookup_release(opener(rows))["tag"] == "native-v0.2.0"


def test_pagination_and_limit():
    calls = []
    def fetch(request, **kwargs):
        calls.append(request.full_url)
        return io.BytesIO(json.dumps([{"tag_name": "v1.0.0"}] * 100 if len(calls) == 1 else [{"tag_name": "native-v0.1.1"}]).encode())
    assert lookup_release(fetch)["tag"] == "native-v0.1.1"
    assert len(calls) == 2 and calls[1].endswith("page=2")
    with pytest.raises(ValueError):
        lookup_release(opener([{}] * 100))
    with pytest.raises(ValueError):
        lookup_release(lambda *a, **k: io.BytesIO(b" " * (2 * 1024 * 1024 + 1)))


def test_offline_cache_is_labeled_and_corruption_is_safe(tmp_path):
    path = tmp_path / "release.json"
    payload = {"action": "release", "cache_path": str(path)}
    fresh = perform(payload, opener([{"tag_name": "native-v0.1.1"}]))
    def offline(*args, **kwargs):
        raise OSError("private path or signed URL")
    cached = perform(payload, offline)
    assert cached["stale"] and cached["tag"] == fresh["tag"]
    path.write_text('{"tag":"../../private","checkedAt":"not a date"}')
    result = perform(payload, offline)
    assert "error" in result and "private" not in json.dumps(result)


def test_allowlist_removes_all_sensitive_inputs_and_nonfinite_numbers(tmp_path):
    snapshot = {"session": "SECRET", "signedUrl": "SECRET", "path": "SECRET", "track": {"title": "SECRET"}, "logs": "SECRET", "renderer": "OpenGL", "windowSystem": "wayland", "width": 920, "height": 620, "devicePixelRatio": 1.5, "uiScale": 150, "reducedMotion": True, "softwareRequested": False, "fixture": True}
    result = public_diagnostics(snapshot)
    assert "SECRET" not in json.dumps(result)
    assert result["renderer"] == "OpenGL" and result["uiScale"] == 150
    assert "width" not in public_diagnostics({"width": float("nan")})
    assert public_diagnostics({"renderer": "private GPU serial/path"})["renderer"] == "Unknown"
    path = tmp_path / "report.json"
    assert perform({"action": "export", "path": str(path), "snapshot": snapshot}) == {"exported": True}
    assert "SECRET" not in path.read_text()
    assert set(json.loads(path.read_text())) == set(result)
    assert "error" in perform({"action": "export", "path": str(tmp_path), "snapshot": {}})


def test_idle_controller_starts_no_worker_and_errors_are_retryable(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    service = Maintenance(tmp_path / "cache.json", object(), worker_factory=Worker)
    assert service._worker is None and service.status == "Not checked" and not service.busy
    service.checkRelease()
    worker = service._worker
    assert service.busy and len(worker.requests) == 1
    service.checkRelease()
    assert len(worker.requests) == 1
    worker.failed.emit(1, {"message": "SECRET"})
    assert not service.busy and "SECRET" not in service.status
    service.checkRelease()
    worker.succeeded.emit(2, {"tag": "native-v9.0.0", "checkedAt": "2026-10-23T00:00:00+00:00", "stale": True})
    assert "Last known" in service.status and "Retry" in service.status
    assert service.releaseUrl.endswith("/native-v9.0.0")
    service.exportDiagnostics(QUrl("https://private.invalid/report"))
    assert len(worker.requests) == 2
    service.close()
    assert worker.closed


def test_worker_account_actions_keep_their_existing_dispatch(tmp_path):
    from types import SimpleNamespace
    from youtube_music_native.worker import handle
    calls = []
    client = SimpleNamespace(rate_song=lambda identifier, rating: calls.append((identifier, rating.value)))
    result = handle(SimpleNamespace(catalog=lambda: client), {
        "operation": "account_action", "payload": {
            "action": "song_rating", "id": "abcdefghijk", "value": "LIKE",
            "cache_path": str(tmp_path / "metadata.sqlite3")}})
    assert calls == [("abcdefghijk", "LIKE")]
    assert result["value"] == "LIKE"
