import json

import pytest

from youtube_music_native.credentials import CHUNK_SIZE, Credentials, CredentialError, SERVICE, USERNAME, default_chunk_size, secure_backend
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
    credentials = Credentials(backend, chunk_size=CHUNK_SIZE)
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
    credentials = Credentials(backend, chunk_size=CHUNK_SIZE)
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


def test_entry_another_app_build_cannot_read_is_replaced_by_a_new_sign_in():
    backend = Vault()
    credentials = Credentials(backend)
    credentials.save(session("old"), {"name": "Listener"})
    read = backend.get_password

    def denied(service, username):
        # macOS refuses reads from a differently signed build but still allows replacement.
        if service == SERVICE:
            raise RuntimeError("private keychain denial")
        return read(service, username)

    backend.get_password = denied
    with pytest.raises(CredentialError):
        credentials.load()
    credentials.save(session("new"), {"name": "Listener"})
    backend.get_password = read
    assert "new" in credentials.load().session.headers["cookie"]


def test_session_is_one_record_outside_windows():
    assert default_chunk_size("win32") == CHUNK_SIZE
    backend = Vault()
    backend.set_password = lambda service, username, value: backend.values.__setitem__((service, username), value)
    credentials = Credentials(backend, chunk_size=default_chunk_size("darwin"))
    credentials.save(session(size=12000), {"name": "Listener"})
    assert len(backend.values) == 2
    assert "x" * 100 in credentials.load().session.headers["cookie"]
