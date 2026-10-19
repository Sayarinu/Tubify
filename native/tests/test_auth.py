import json

import pytest

from youtube_music_native.auth import AuthService
from youtube_music_native.credentials import Credentials
from youtube_music_native.worker import safe_error


class MemoryVault:
    def __init__(self):
        self.values = {}

    def get_password(self, service, username):
        return self.values.get((service, username))

    def set_password(self, service, username, value):
        self.values[service, username] = value

    def delete_password(self, service, username):
        self.values.pop((service, username), None)


class Catalog:
    base_headers = {"X-Goog-Visitor-Id": "fixture-visitor"}

    def get_account_info(self):
        return {"accountName": "Listener", "channelHandle": "@listener", "accountPhotoUrl": "https://example.test/photo"}


def test_validated_import_restores_without_network_and_sign_out_clears_only_session(tmp_path):
    path = tmp_path / "browser.json"
    path.write_text(json.dumps({"cookie": "__Secure-3PAPISID=private-cookie"}))
    credentials = Credentials(MemoryVault())
    service = AuthService(credentials, lambda session: Catalog())
    result = service.import_session(path)
    assert result["connected"]
    assert "private-cookie" not in json.dumps(result)

    def no_network(*args):
        pytest.fail("Restoring a saved account must not require network access")

    restored = AuthService(credentials, no_network)
    assert restored.restore()["profile"]["name"] == "Listener"
    assert restored.sign_out() == {"connected": False, "profile": {}}
    assert credentials.load() is None


def test_expired_replacement_cannot_overwrite_existing_session(tmp_path):
    path = tmp_path / "browser.json"
    path.write_text(json.dumps({"cookie": "__Secure-3PAPISID=private-cookie"}))
    credentials = Credentials(MemoryVault())
    service = AuthService(credentials, lambda session: Catalog())
    service.import_session(path)
    previous = credentials.load().session.headers["cookie"]

    def expired(session):
        raise RuntimeError("provider exception with private-cookie")

    service.catalog_factory = expired
    with pytest.raises(RuntimeError) as error:
        service.import_session(path)
    assert "private-cookie" not in json.dumps(safe_error(error.value))
    assert credentials.load().session.headers["cookie"] == previous
