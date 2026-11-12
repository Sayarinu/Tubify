from http.cookiejar import CookieJar
from pathlib import Path
from types import SimpleNamespace

import pytest
from tubify.playback import sources
from tubify.account.auth import AuthService
from tubify.playback.media import MediaFiles
from tubify.playback.sources import Sources


def test_complete_local_audio_wins_even_with_expired_credentials_or_force(tmp_path, monkeypatch):
    audio = tmp_path / "song.opus"
    audio.write_bytes(b"fixture audio")
    media = MediaFiles(tmp_path)
    media.db.execute("INSERT INTO audio VALUES (?, ?, ?, 'ready')", ("abcdefghijk", "song.opus", audio.stat().st_size))
    media.db.commit()

    def forbidden(*args):
        raise AssertionError("Local playback must not access auth or extract a stream")

    monkeypatch.setattr("tubify.account.auth.Credentials", forbidden)
    auth = AuthService()
    service = Sources(auth, media, extractor_factory=forbidden)
    assert service.resolve("abcdefghijk", force=True, available=False)["source"] == str(audio)
    assert auth._credentials is None
    audio.unlink()
    assert media.ready("abcdefghijk") is None
    assert media.db.execute("SELECT state FROM audio").fetchone()[0] == "damaged"


def test_prepared_source_survives_worker_restart_but_local_audio_wins(tmp_path):
    def forbidden(*args):
        raise AssertionError("A valid prepared source does not require extraction or authentication")

    media = MediaFiles(tmp_path)
    service = Sources(SimpleNamespace(session=None, restore=forbidden), media, forbidden)
    prepared = {"kind": "remote", "videoId": "abcdefghijk", "source": "https://media.invalid/prepared", "headers": [], "expires": 4102444800}
    assert service.resolve("abcdefghijk", prepared=prepared) == prepared
    audio = tmp_path / "local.opus"
    audio.write_bytes(b"complete")
    media.db.execute("INSERT INTO audio VALUES (?, ?, ?, 'ready')", ("abcdefghijk", "local.opus", 8))
    media.db.commit()
    assert service.resolve("abcdefghijk", prepared=prepared)["kind"] == "local"
    audio.unlink()
    expired = {**prepared, "expires": 1}
    with pytest.raises(AssertionError):
        service.resolve("abcdefghijk", prepared=expired)


def test_remote_url_cache_expires_and_local_file_still_takes_precedence(tmp_path, monkeypatch):
    monkeypatch.setattr(sources, "extractor_options", lambda root: {})
    calls = []

    class Extractor:
        cookiejar = CookieJar()

        def __init__(self, options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def extract_info(self, url, download):
            calls.append(url)
            return {"url": "https://media.invalid/audio?expire=4102444800", "vcodec": "none", "http_headers": {"User-Agent": "fixture"}}

    auth = SimpleNamespace(session=SimpleNamespace(cookie_jar=CookieJar))
    media = MediaFiles(tmp_path)
    service = Sources(auth, media, Extractor)
    assert service.resolve("abcdefghijk")["kind"] == "remote"
    service.resolve("abcdefghijk")
    assert len(calls) == 1
    service.resolve("abcdefghijk", force=True)
    assert len(calls) == 2
    audio = tmp_path / "complete.opus"
    audio.write_bytes(b"complete")
    media.db.execute("INSERT INTO audio VALUES (?, ?, ?, 'ready')", ("abcdefghijk", "complete.opus", 8))
    media.db.commit()
    assert service.resolve("abcdefghijk")["kind"] == "local" and len(calls) == 2


def test_invalid_index_paths_cannot_escape_the_media_directory(tmp_path):
    media = MediaFiles(tmp_path / "media")
    outside = tmp_path / "outside.opus"
    outside.write_bytes(b"outside")
    media.db.execute("INSERT INTO audio VALUES (?, ?, ?, 'ready')", ("abcdefghijk", "../outside.opus", 7))
    media.db.commit()
    assert media.ready("abcdefghijk") is None


def test_one_extractor_serves_every_song_with_only_current_cookies(tmp_path, monkeypatch):
    from http.cookiejar import Cookie

    monkeypatch.setattr(sources, "extractor_options", lambda root: {})
    created, seen = [], []

    def cookie(name):
        return Cookie(0, name, "value", None, False, ".youtube.com", True, True, "/", True, True, None, False, None, None, {})

    class Extractor:
        def __init__(self, options):
            created.append(options)
            self.cookiejar = CookieJar()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def extract_info(self, url, download):
            seen.append(sorted(item.name for item in self.cookiejar))
            self.cookiejar.set_cookie(cookie("FROM_RESPONSE"))
            if url.endswith("brokenvideo"):
                raise RuntimeError("extractor failure")
            return {"url": "https://media.invalid/audio?expire=4102444800", "vcodec": "none"}

    def jar():
        value = CookieJar()
        value.set_cookie(cookie("SID"))
        return value

    auth = SimpleNamespace(session=SimpleNamespace(cookie_jar=jar), restore=lambda: None)
    service = Sources(auth, MediaFiles(tmp_path), Extractor)
    assert service.warm() == {"ready": True} and len(created) == 1
    service.resolve("abcdefghijk")
    service.resolve("lmnopqrstuv")
    assert len(created) == 1 and seen == [["SID"], ["SID"]]
    with pytest.raises(sources.SourceError):
        service.resolve("brokenvideo")
    service.resolve("wxyzabcdefg")
    assert len(created) == 2  # A failed extractor is replaced, not reused.


def test_warm_without_a_session_reports_not_ready(tmp_path):
    def forbidden(*args):
        raise AssertionError("No extractor is built without a session")

    auth = SimpleNamespace(session=None, restore=lambda: None)
    assert Sources(auth, MediaFiles(tmp_path), forbidden).warm() == {"ready": False}


def test_audio_resolves_skip_hls_and_retry_once_with_every_format(tmp_path, monkeypatch):
    monkeypatch.setattr(sources, "extractor_options", lambda root: {"format": "bestaudio"})
    created, calls = [], []
    audio = {"url": "https://media.invalid/audio?expire=4102444800", "vcodec": "none"}

    class Extractor:
        def __init__(self, options):
            self.options = options
            created.append(options)
            self.cookiejar = CookieJar()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def extract_info(self, url, download):
            video_id = url[-11:]
            skipping = "extractor_args" in self.options
            calls.append((video_id, skipping))
            if skipping and video_id == "hlsonlysong":
                raise RuntimeError("ERROR: [youtube] hlsonlysong: Requested format is not available")
            if skipping and video_id == "videoformat":
                return {"url": "https://media.invalid/muxed", "vcodec": "avc1"}
            if video_id == "unreachable":
                raise RuntimeError("network down")
            return audio

    auth = SimpleNamespace(session=SimpleNamespace(cookie_jar=CookieJar), restore=lambda: None)
    service = Sources(auth, MediaFiles(tmp_path), Extractor)
    assert service.resolve("abcdefghijk")["source"] == audio["url"]
    assert created == [{"format": "bestaudio", "skip_download": True, "noplaylist": True,
                        "extractor_args": {"youtube": {"skip": ["hls"]}}}]
    assert service.resolve("hlsonlysong")["source"] == audio["url"]
    assert service.resolve("videoformat")["source"] == audio["url"]
    assert calls[1:] == [("hlsonlysong", True), ("hlsonlysong", False), ("videoformat", True), ("videoformat", False)]
    assert len([options for options in created if "extractor_args" not in options]) == 1  # The fallback is reused.
    # Other failures are not retried.
    with pytest.raises(sources.SourceError):
        service.resolve("unreachable")
    assert calls[-1] == ("unreachable", True)
    # Video extraction keeps every format.
    service._extractor("video", {"format": "best"})
    assert "extractor_args" not in created[-1]


def test_macos_workers_leave_the_keychain_alone_until_a_song_needs_it():
    class Auth:
        session, restored = None, 0

        def restore(self):
            self.restored += 1

    resolver = Sources.__new__(Sources)
    resolver.auth = Auth()
    resolver.warm(platform="darwin")
    assert resolver.auth.restored == 0
    resolver.warm(platform="linux")
    assert resolver.auth.restored == 1


def _signed_in_extractor(clears_login):
    class Extractor:
        def __init__(self, options):
            self.cookiejar = CookieJar()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def extract_info(self, url, download):
            if clears_login:
                # YouTube's Set-Cookie for a rotated-out session removes LOGIN_INFO.
                self.cookiejar.clear(".youtube.com", "/", "LOGIN_INFO")
            return {"url": "https://media.invalid/audio?expire=4102444800", "vcodec": "none"}

    return Extractor


def test_a_session_youtube_signed_out_reports_session_expired(tmp_path, monkeypatch):
    from tubify.account.session import Session, make_cookie
    from tubify.util import needs_reconnect
    from tubify.worker import safe_error

    monkeypatch.setattr(sources, "extractor_options", lambda root: {})
    session = Session({}, [make_cookie("LOGIN_INFO", "x"), make_cookie("__Secure-3PAPISID", "y")])
    auth = SimpleNamespace(session=session)
    assert Sources(auth, MediaFiles(tmp_path / "a"), _signed_in_extractor(False)).resolve("abcdefghijk")["kind"] == "remote"
    with pytest.raises(sources.SessionExpired) as raised:
        Sources(auth, MediaFiles(tmp_path / "b"), _signed_in_extractor(True)).resolve("abcdefghijk")
    assert needs_reconnect(safe_error(raised.value))
