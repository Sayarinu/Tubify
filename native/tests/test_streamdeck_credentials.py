import io
import json
import subprocess
import sys

import pytest

from youtube_music_native import streamdeck_credentials as bridge

VALUE = {"port": 9864, "clientId": "a" * 32, "token": "s" * 43, "scope": "control"}


class Vault:
    def __init__(self):
        self.value, self.calls = None, []
    def get_password(self, service, account):
        self.calls.append((service, account))
        return self.value
    def set_password(self, service, account, value):
        self.calls.append((service, account))
        self.value = value
    def delete_password(self, service, account):
        self.calls.append((service, account))
        self.value = None


def test_fixed_vault_round_trip_and_idempotent_forget():
    vault = Vault()
    assert bridge.execute({"action": "read"}, vault)["credential"] is None
    bridge.execute({"action": "write", "credential": VALUE}, vault)
    assert bridge.execute({"action": "read"}, vault)["credential"] == VALUE
    bridge.execute({"action": "delete"}, vault)
    bridge.execute({"action": "delete"}, vault)
    assert vault.value is None
    assert set(vault.calls) == {(bridge.VAULT, bridge.ACCOUNT)}


@pytest.mark.parametrize("payload", [{"action": "shell"}, {"action": "read", "service": "other"}, {"action": "write", "credential": {**VALUE, "scope": "overlay"}}, {"action": "write", "credential": {**VALUE, "port": True}}, {"action": "write", "credential": {**VALUE, "token": "short"}}, {"action": "write", "credential": {**VALUE, "clientId": "../other"}}, {"action": "write", "credential": {**VALUE, "secret": "extra"}}])
def test_invalid_requests_cannot_access_other_vault_entries(payload):
    vault = Vault()
    with pytest.raises(ValueError):
        bridge.execute(payload, vault)
    assert not vault.calls


def test_input_is_bounded_and_keyring_failures_are_redacted(monkeypatch):
    def fail():
        raise RuntimeError("private-token-content")
    monkeypatch.setattr(bridge, "secure_backend", fail)
    for raw in ('x' * (bridge.MAX_INPUT + 10), json.dumps({"action": "read"})):
        output = io.StringIO()
        assert bridge.main(io.StringIO(raw), output) == 1
        result = output.getvalue()
        assert 'private-token-content' not in result and not json.loads(result)["ok"]


def test_launcher_credential_mode_does_not_initialize_qt_player_or_account():
    code = '''
import io, json, sys
from youtube_music_native import launcher, streamdeck_credentials
streamdeck_credentials.execute = lambda request: {"ok": True, "credential": None}
sys.stdin = io.StringIO('{"action":"read"}')
assert launcher.main(["--streamdeck-credentials"]) == 0
assert not any(name.startswith("PySide6") for name in sys.modules)
assert "youtube_music_native.app" not in sys.modules
assert "youtube_music_native.account" not in sys.modules
assert "youtube_music_native.worker" not in sys.modules
'''
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert json.loads(result.stdout) == {"ok": True, "credential": None}
    assert not result.stderr
