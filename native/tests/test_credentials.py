import json

import pytest

from youtube_music_native.credentials import Credentials, CredentialError, SERVICE, USERNAME, secure_backend
from youtube_music_native.session import from_headers


class Vault:
    def __init__(self):
        self.values = {}
        self.writes = 0
        self.fail_at = None

    def get_password(self, service, username):
        return self.values.get((service, username))

    def set_password(self, service, username, value):
        self.writes += 1
        if self.fail_at == self.writes:
            raise RuntimeError("private underlying vault error")
        assert len(value.encode("utf-16-le")) <= 2560
        self.values[service, username] = value

    def delete_password(self, service, username):
        self.values.pop((service, username), None)


def session(marker="private", size=100):
    return from_headers({"cookie": "__Secure-3PAPISID=" + marker + "; SID=" + "x" * size})


def test_large_unicode_account_round_trips_with_windows_sized_secret_records():
    backend = Vault()
    credentials = Credentials(backend)
    original = session(size=12000)
    profile = {"name": "音楽", "handle": "@listener", "avatar": ""}
    credentials.save(original, profile)
    stored = credentials.load()
    assert stored.session.headers["cookie"] == original.headers["cookie"]
    assert stored.profile == profile
    assert "private" not in repr(stored)
    assert len(backend.values) > 2


def test_failed_replacement_preserves_previous_session_and_removes_uncommitted_chunks():
    backend = Vault()
    credentials = Credentials(backend)
    original = session("previous")
    credentials.save(original, {"name": "Previous"})
    count = len(backend.values)
    backend.fail_at = backend.writes + 2
    with pytest.raises(CredentialError) as error:
        credentials.save(session("replacement", size=4000), {"name": "Replacement"})
    assert "private" not in str(error.value)
    assert credentials.load().session.headers["cookie"] == original.headers["cookie"]
    assert len(backend.values) == count


def test_corrupt_manifest_can_be_reconnected_or_signed_out():
    backend = Vault()
    credentials = Credentials(backend)
    backend.values[SERVICE, USERNAME] = "malformed private manifest"
    with pytest.raises(CredentialError):
        credentials.load()
    credentials.save(session(), {"name": "Recovered"})
    assert credentials.load().profile["name"] == "Recovered"
    backend.values[SERVICE, USERNAME] = "malformed again"
    credentials.clear()
    assert credentials.load() is None


def test_missing_chunk_requires_reconnection_and_sign_out_leaves_other_apps_alone():
    backend = Vault()
    credentials = Credentials(backend)
    credentials.save(session(size=2000), {"name": "Listener"})
    manifest = json.loads(backend.values[SERVICE, USERNAME])
    backend.values.pop((credentials._chunk_service(manifest, 0), USERNAME))
    with pytest.raises(CredentialError):
        credentials.load()
    backend.values["another-app", "session"] = "unchanged"
    credentials.clear()
    assert credentials.load() is None
    assert backend.values["another-app", "session"] == "unchanged"


def test_plaintext_keyring_backend_is_rejected(monkeypatch):
    import keyring

    class Plaintext:
        priority = 5

    Plaintext.__module__ = "keyrings.alt.file"
    monkeypatch.setattr(keyring, "get_keyring", lambda: Plaintext())
    with pytest.raises(CredentialError):
        secure_backend()
