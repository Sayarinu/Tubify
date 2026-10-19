import json
import sys
from types import ModuleType, SimpleNamespace

import pytest

from youtube_music_native.session import SessionError, from_headers, read_browser_session, read_tauri_session


def test_import_keeps_credentials_out_of_representation_and_restricts_origin(tmp_path):
    path = tmp_path / "browser.json"
    path.write_text(json.dumps({
        "Cookie": "__Secure-3PAPISID=private-session; SID=another-secret",
        "Origin": "https://untrusted.example",
        "Host": "untrusted.example",
        "X-Goog-AuthUser": "1",
    }))
    session = read_browser_session(path)
    assert "private-session" not in repr(session)
    assert session.headers["origin"] == "https://music.youtube.com"
    assert session.headers["x-goog-authuser"] == "1"
    assert "host" not in session.headers
    jar = session.cookie_jar()
    assert {cookie.name for cookie in jar} == {"SID", "__Secure-3PAPISID"}
    next(iter(jar)).value = "changed"
    assert next(iter(session.cookie_jar())).value != "changed"


@pytest.mark.parametrize("value", [[], {"cookie": "SID=private"}, {"cookie": "__Secure-3PAPISID=private\r\nHost: evil"}])
def test_invalid_session_errors_do_not_expose_credentials(value):
    with pytest.raises(SessionError) as error:
        from_headers(value)
    assert "private" not in str(error.value)


def test_malformed_export_is_reported_without_its_contents(tmp_path):
    path = tmp_path / "browser.json"
    path.write_text("private malformed input")
    with pytest.raises(SessionError) as error:
        read_browser_session(path)
    assert "private" not in str(error.value)


def test_tauri_migration_is_read_only_and_excludes_other_domains_and_expired_cookies(monkeypatch, tmp_path):
    profile = tmp_path / "cookies"
    profile.write_text("unchanged profile")
    calls = []

    def cookie(name, domain, expires=None):
        return SimpleNamespace(
            get_name=lambda: name, get_value=lambda: "private",
            get_domain=lambda: domain, get_path=lambda: "/",
            get_secure=lambda: True,
            get_expires=lambda: SimpleNamespace(to_unix=lambda: expires) if expires else None,
        )

    def new(path, read_only):
        calls.append((path, read_only))
        return SimpleNamespace(all_cookies=lambda: [
            cookie("__Secure-3PAPISID", ".youtube.com"),
            cookie("music", "music.youtube.com"),
            cookie("expired", ".youtube.com", 1),
            cookie("unrelated", ".google.com"),
        ])

    gi = ModuleType("gi")
    gi.require_version = lambda *args: None
    repository = ModuleType("gi.repository")
    repository.Soup = SimpleNamespace(CookieJarText=SimpleNamespace(new=new))
    monkeypatch.setitem(sys.modules, "gi", gi)
    monkeypatch.setitem(sys.modules, "gi.repository", repository)
    session = read_tauri_session(profile)
    assert calls == [(str(profile), True)]
    assert {c.name for c in session.cookie_jar()} == {"__Secure-3PAPISID", "music"}
    assert {c.domain for c in session.cookie_jar()} == {".youtube.com", "music.youtube.com"}
    assert profile.read_text() == "unchanged profile"
