import hashlib
import io
import json
import sqlite3
from urllib.error import HTTPError
from urllib.parse import parse_qs

import pytest
from PySide6.QtCore import QCoreApplication, QObject, Signal

from youtube_music_native.lastfm import LastFm
from youtube_music_native.lastfm_service import LastFmError, LastFmService, VAULT, metadata, request
from youtube_music_native.worker import safe_error


class Vault:
    def __init__(self):
        self.value = None
    def get_password(self, *_):
        return self.value
    def set_password(self, *args):
        self.value = args[-1]
    def delete_password(self, *_):
        self.value = None


class Api:
    def __init__(self):
        self.calls, self.error = [], None
        self.user = "fixture-user"
    def __call__(self, credentials, method, values=None):
        self.calls.append((method, dict(values or {})))
        if self.error:
            raise self.error
        if method == "auth.getToken":
            return {"token": "t" * 32}
        if method == "auth.getSession":
            return {"session": {"key": "s" * 32, "name": self.user}}
        if method == "track.scrobble":
            return {"scrobbles": {"@attr": {"accepted": "1", "ignored": "0"}}}
        return {"nowplaying": {}}


TRACK = {"videoId": "fixture0001", "title": "Original song", "artists": [{"name": "Fixture artist"}], "album": {"name": "Fixture album"}, "duration": 180, "signedUrl": "private"}


def service(tmp_path):
    vault, api = Vault(), Api()
    backend = LastFmService(tmp_path, vault, api, clock=lambda: 2000000000)
    backend.perform("configure", {"api_key": "a" * 32, "secret": "b" * 32})
    return backend, vault, api


def connect(backend):
    result = backend.perform("authorize", {})
    assert result["authUrl"].startswith("https://www.last.fm/api/auth/?")
    return backend.perform("complete", {})


def listen(identifier="1" * 32, timestamp=1900000000):
    return {"id": identifier, "timestamp": timestamp, "track": TRACK}


def test_desktop_auth_keyring_only_and_logout(tmp_path):
    backend, vault, api = service(tmp_path)
    result = connect(backend)
    assert result["connected"] and result["username"] == "fixture-user"
    assert not any(key in result for key in ("api_key", "secret", "session", "token"))
    assert json.loads(vault.value)["session"] == "s" * 32
    assert "token" not in json.loads(vault.value)
    backend.perform("now_playing", {"track": TRACK})
    assert api.calls[-1] == ("track.updateNowPlaying", {"artist": "Fixture artist", "track": "Original song", "album": "Fixture album", "duration": 180})
    assert not backend.perform("logout", {})["configured"] and vault.value is None


def test_signature_form_post_and_redacted_errors():
    received = []
    def opener(req, timeout):
        received.append((req, timeout))
        return io.BytesIO(b'{"nowplaying": {}}')
    credentials = {"api_key": "key", "secret": "secret", "session": "session"}
    request(credentials, "track.updateNowPlaying", {"track": "A & B", "artist": "Artíst"}, opener)
    req, timeout = received[0]
    assert req.get_method() == "POST" and req.full_url == "https://ws.audioscrobbler.com/2.0/" and timeout == 10
    values = {key: rows[0] for key, rows in parse_qs(req.data.decode()).items()}
    signature = values.pop("api_sig")
    assert values.pop("format") == "json"
    expected = "".join(k + values[k] for k in sorted(values)) + "secret"
    assert signature == hashlib.md5(expected.encode(), usedforsecurity=False).hexdigest()
    def fail(*args, **kwargs):
        raise RuntimeError("private session token")
    with pytest.raises(LastFmError) as error:
        request(credentials, "auth.getToken", opener=fail)
    assert "private" not in str(error.value)
    assert safe_error(error.value)["code"] == "lastfm_offline"


@pytest.mark.parametrize("code,category,retry", [(9, "auth", False), (10, "setup", False), (11, "offline", True), (16, "offline", True), (29, "offline", True), (14, "approval", False), (15, "approval", False), (6, "rejected", False)])
def test_http_protocol_errors_even_non_200(code, category, retry):
    def fail(req, timeout):
        raise HTTPError(req.full_url, 400, "Bad Request", {}, io.BytesIO(json.dumps({"error": code, "message": "private details"}).encode()))
    with pytest.raises(LastFmError) as error:
        request({"api_key": "key", "secret": "secret"}, "auth.getToken", opener=fail)
    assert (error.value.code, error.value.retry) == (category, retry)
    assert "private" not in str(error.value)


def test_persistent_offline_queue_order_and_dedup(tmp_path):
    backend, vault, api = service(tmp_path)
    connect(backend)
    api.error = LastFmError("offline", "Retry", True)
    assert backend.perform("listen", listen())["pendingCount"] == 1
    assert backend.perform("listen", listen())["pendingCount"] == 1
    assert backend.perform("listen", listen("2" * 32, 1900000020))["pendingCount"] == 2
    backend = LastFmService(tmp_path, vault, api, clock=lambda: 2000000000)
    api.error = None
    assert backend.perform("flush", {})["pendingCount"] == 1
    assert api.calls[-1][1]["timestamp"] == 1900000000
    assert backend.perform("flush", {})["pendingCount"] == 0
    assert api.calls[-1][1]["timestamp"] == 1900000020
    count = len(api.calls)
    backend.perform("listen", listen())
    assert len(api.calls) == count, "Acknowledged listens must never resubmit"
    with sqlite3.connect(tmp_path / "lastfm.sqlite3") as db:
        assert all(row[0] == '{}' for row in db.execute("SELECT body FROM listens")), "Completed metadata should be removed"


def test_auth_expiry_preserves_queue_and_same_user_reauth(tmp_path):
    backend, vault, api = service(tmp_path)
    connect(backend)
    api.error = LastFmError("auth", "Sign in again")
    result = backend.perform("listen", listen())
    assert result["reconnect"] and result["pendingCount"] == 1 and not result["connected"]
    api.error = None
    assert connect(backend)["pendingCount"] == 1
    assert backend.perform("flush", {})["pendingCount"] == 0


def test_switch_user_clears_previous_user_pending_and_bad_metadata_rejects(tmp_path):
    backend, vault, api = service(tmp_path)
    connect(backend)
    api.error = LastFmError("offline", "Retry", True)
    backend.perform("listen", listen())
    api.error, api.user = None, "other-user"
    assert connect(backend)["pendingCount"] == 0
    with pytest.raises(LastFmError):
        backend.perform("listen", {**listen(), "track": {"title": "No artist"}})
    with pytest.raises(LastFmError):
        backend.perform("configure", {"api_key": "not a key", "secret": ""})


def test_queue_bound_and_filtered_listen_does_not_retry(tmp_path, monkeypatch):
    import youtube_music_native.lastfm_service as module
    monkeypatch.setattr(module, "MAX_PENDING", 3)
    backend, vault, api = service(tmp_path)
    connect(backend)
    api.error = LastFmError("offline", "Retry", True)
    for index in range(5):
        result = backend.perform("listen", listen(f"{index:032x}", 1900000000 + index))
    assert result["pendingCount"] == 3
    api.error = LastFmError("rejected", "Invalid track")
    assert backend.perform("flush", {})["pendingCount"] == 2
    assert metadata({"title": "Song", "artist": "Artist", "albumName": "Album"}) == {"track": "Song", "artist": "Artist", "album": "Album"}


class Player(QObject):
    trackStarted = Signal(dict)
    changed = Signal()
    seeked = Signal(float)
    def __init__(self):
        super().__init__()
        self.currentTrack, self.playing, self.busy = dict(TRACK), True, False
        self.position, self.duration = 0., 180.


class Worker(QObject):
    succeeded = Signal(int, dict)
    failed = Signal(int, dict)
    def __init__(self, *args, **kwargs):
        super().__init__()
        self.requests, self.closed = [], False
    def request(self, action, payload):
        self.requests.append((action, payload))
        return len(self.requests)
    def close(self):
        self.closed = True


def frontend(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    player, workers, now = Player(), [], [1000.]
    def factory(*args, **kwargs):
        workers.append(Worker())
        return workers[-1]
    view = LastFm(player, tmp_path / "settings.ini", tmp_path, worker_factory=factory, clock=lambda: now[0], wall_clock=lambda: 1900000000 + now[0], browser=lambda url: True)
    view._test_app = app
    return view, player, workers, now


def enable(view):
    view._status = {"configured": True, "connected": True, "username": "fixture-user"}
    view.setEnabled(True)


def progress(view, player, clock, seconds):
    for _ in range(seconds):
        clock[0] += 1
        player.position += 1
        view._tick()


def actions(workers, name):
    return [body for worker in workers for _, body in worker.requests if body["action"] == name]


def test_disabled_is_idle_then_actual_time_counts_once(tmp_path):
    view, player, workers, now = frontend(tmp_path)
    player.trackStarted.emit(player.currentTrack)
    progress(view, player, now, 100)
    assert not workers and not view.timer.isActive()
    enable(view)
    progress(view, player, now, 89)
    assert len(actions(workers, "now_playing")) == 1 and not actions(workers, "listen")
    progress(view, player, now, 1)
    assert len(actions(workers, "listen")) == 1
    progress(view, player, now, 20)
    assert len(actions(workers, "listen")) == 1
    view.setEnabled(False)
    assert workers[-1].closed and not view.timer.isActive() and not view.retry_timer.isActive()
    view.close()


def test_seek_pause_buffer_and_suspend_do_not_count(tmp_path):
    view, player, workers, now = frontend(tmp_path)
    enable(view)
    progress(view, player, now, 20)
    player.position = 170
    player.seeked.emit(170)
    now[0] += 60
    view._tick()
    player.playing = False
    player.changed.emit()
    now[0] += 1000
    player.playing = True
    player.changed.emit()
    player.busy = True
    player.changed.emit()
    progress(view, player, now, 100)
    player.busy = False
    player.changed.emit()
    progress(view, player, now, 69)
    assert not actions(workers, "listen")
    progress(view, player, now, 1)
    assert len(actions(workers, "listen")) == 1
    view.close()


def test_repeat_is_new_listen_but_recovery_preserves_elapsed(tmp_path):
    view, player, workers, now = frontend(tmp_path)
    enable(view)
    progress(view, player, now, 50)
    player.trackStarted.emit(player.currentTrack)
    progress(view, player, now, 40)
    first = actions(workers, "listen")[0]
    player.position = 0
    player.trackStarted.emit(player.currentTrack)
    progress(view, player, now, 90)
    second = actions(workers, "listen")[1]
    assert second["id"] != first["id"] and second["timestamp"] > first["timestamp"]
    view.close()


@pytest.mark.parametrize("duration,threshold,seconds,expected", [(30,50,30,0), (180,75,134,0), (180,75,135,1), (1000,100,240,1)])
def test_short_tracks_and_configurable_threshold(tmp_path, duration, threshold, seconds, expected):
    view, player, workers, now = frontend(tmp_path)
    player.duration = duration
    view.setThresholdPercent(threshold)
    enable(view)
    progress(view, player, now, seconds)
    assert len(actions(workers, "listen")) == expected
    view.close()


def test_failed_write_retries_same_id_without_blocking_player(tmp_path):
    view, player, workers, now = frontend(tmp_path)
    enable(view)
    worker = workers[0]
    worker.succeeded.emit(1, {"connected": True, "pendingCount": 0})
    progress(view, player, now, 90)
    for index, (_, body) in enumerate(worker.requests, 1):
        if body["action"] == "now_playing":
            worker.succeeded.emit(index, {})
        if body["action"] == "listen":
            original = body
            worker.failed.emit(index, {"code": "timeout", "message": "Retry"})
    assert player.playing and view.pendingCount == 1
    view.retry()
    assert worker.requests[-1][1]["id"] == original["id"]
    worker.succeeded.emit(len(worker.requests), {"pendingCount": 0})
    assert view.pendingCount == 0
    view.close()


def test_long_pause_refreshes_now_playing_without_second_scrobble(tmp_path):
    view, player, workers, now = frontend(tmp_path)
    enable(view)
    progress(view, player, now, 90)
    player.playing = False
    player.changed.emit()
    now[0] += 600
    player.playing = True
    player.changed.emit()
    progress(view, player, now, 1)
    assert len(actions(workers, "now_playing")) == 2
    assert len(actions(workers, "listen")) == 1
    view.close()


def test_corrupt_credentials_can_be_replaced_or_cleared(tmp_path):
    backend, vault, api = service(tmp_path)
    vault.value = "broken"
    with pytest.raises(LastFmError):
        backend.perform("status", {})
    assert backend.perform("configure", {"api_key": "a" * 32, "secret": "b" * 32})["configured"]
    vault.value = "broken"
    assert not backend.perform("logout", {})["configured"]


def test_disabled_service_does_not_start_process_on_real_worker(tmp_path):
    view, player, _, now = frontend(tmp_path)
    assert view._worker is None
    view.close()


def test_reauth_other_user_discards_unacknowledged_listens(tmp_path):
    view, player, workers, now = frontend(tmp_path)
    enable(view)
    view._unsaved["1" * 32] = listen()
    view._status["awaitingApproval"] = True
    workers[0].succeeded.emit(1, {"connected": True, "pendingCount": 0})
    view.complete()
    identifier = len(workers[0].requests)
    workers[0].succeeded.emit(identifier, {"connected": True, "username": "other-user", "pendingCount": 0})
    assert not view._unsaved and view._listen["elapsed"] == 0
    view.close()


def test_threshold_then_immediate_close_persists_unacknowledged_listen(tmp_path):
    view, player, workers, now = frontend(tmp_path)
    enable(view)
    progress(view, player, now, 90)
    first = actions(workers, "listen")[0]
    view.close()
    spool = json.loads((tmp_path / "lastfm-pending.json").read_text())
    assert spool["listens"][0]["id"] == first["id"]
    assert "signedUrl" not in json.dumps(spool) and "videoId" not in json.dumps(spool)
    restored, player, workers, now = frontend(tmp_path)
    assert restored.enabled
    workers[0].succeeded.emit(1, {"connected": True, "username": "fixture-user", "pendingCount": 0})
    restored.retry()
    retry = actions(workers, "listen")[0]
    assert retry["id"] == first["id"] and retry["timestamp"] == first["timestamp"]
    workers[0].succeeded.emit(len(workers[0].requests), {"pendingCount": 0})
    restored.close()
    assert not json.loads((tmp_path / "lastfm-pending.json").read_text())["listens"]


def test_permanent_rejection_removes_spooled_retry(tmp_path):
    view, player, workers, now = frontend(tmp_path)
    enable(view)
    progress(view, player, now, 90)
    worker = workers[0]
    identifier = next(index for index, (_, body) in enumerate(worker.requests, 1) if body["action"] == "listen")
    worker.failed.emit(identifier, {"code": "lastfm_metadata", "message": "Incomplete metadata"})
    assert not view._unsaved
    view.close()
    assert not json.loads((tmp_path / "lastfm-pending.json").read_text())["listens"]


def test_missing_artist_never_enqueues_or_breaks_playback(tmp_path):
    view, player, workers, now = frontend(tmp_path)
    player.currentTrack = {"title": "Missing artist", "duration": 180}
    enable(view)
    progress(view, player, now, 180)
    assert not actions(workers, "listen") and player.playing and not view._unsaved
    view.close()
