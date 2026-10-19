from http.cookiejar import CookieJar
from pathlib import Path
from types import SimpleNamespace

import pytest
from youtube_music_native import sources
from youtube_music_native.auth import AuthService
from youtube_music_native.media import MediaFiles
from youtube_music_native.sources import Sources


def test_complete_local_audio_wins_even_with_expired_credentials_or_force(tmp_path, monkeypatch):
    audio = tmp_path / "song.opus"
    audio.write_bytes(b"fixture audio")
    media = MediaFiles(tmp_path)
    media.db.execute("INSERT INTO audio VALUES (?, ?, ?, 'ready')", ("abcdefghijk", "song.opus", audio.stat().st_size))
    media.db.commit()

    def forbidden(*args):
        raise AssertionError("Local playback must not access auth or extract a stream")

    monkeypatch.setattr("youtube_music_native.auth.Credentials", forbidden)
    auth = AuthService()
    service = Sources(auth, media, extractor_factory=forbidden)
    assert service.resolve("abcdefghijk", force=True)["source"] == str(audio)
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
