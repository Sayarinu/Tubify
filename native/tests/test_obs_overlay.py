import json
from pathlib import Path
import shutil
import subprocess
from urllib.parse import parse_qs, urlsplit

from PySide6.QtCore import QCoreApplication, QObject, Signal
import pytest

from youtube_music_native.obs_overlay import ObsOverlay, LAYOUTS


class Api(QObject):
    changed = Signal()
    active = True
    overlayUrl = "http://127.0.0.1:9864/overlay/"
    def __init__(self):
        super().__init__()
        self.clients, self.revoked = [], []
    def createClient(self, name, scope):
        self.clients.append((name, scope))
        return {"clientId": str(len(self.clients)), "token": "a" * 43, "scope": scope}
    def revokeClient(self, client):
        self.revoked.append(client)
        return True


def test_explicit_readonly_pairing_fragment_only_and_restart_revocation(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    api = Api()
    service = ObsOverlay(api, tmp_path / "settings.ini")
    assert not service.hasSource and not api.clients
    service.generate()
    assert api.clients == [("OBS now playing", "overlay")]
    parts = urlsplit(service.source_url())
    assert "token" not in parse_qs(parts.query)
    assert parse_qs(parts.fragment)["token"] == ["a" * 43]
    service.settings.sync()
    assert "a" * 43 not in (tmp_path / "settings.ini").read_text()
    restored = ObsOverlay(api, tmp_path / "settings.ini")
    assert not restored.hasSource and restored.hasClient
    restored.generate()
    assert api.revoked == ["1"]
    restored.revoke()
    assert api.revoked == ["1", "2"] and not restored.hasClient


def test_options_preview_defaults_and_inactive_api(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    api, opened = Api(), []
    service = ObsOverlay(api, tmp_path / "settings.ini", browser=lambda url: opened.append(url.toString()) or True)
    for layout in LAYOUTS:
        service.setOption("layout", layout)
        assert service.options["layout"] == layout and "×" in service.suggestedSize
    service.setOption("scale", 5)
    assert service.options["scale"] == 1
    service.setOption("scale", .25)
    service.setOption("art", False)
    service.setOption("paused", "hide")
    service.preview()
    assert "preview=1" in opened[0] and "token" not in opened[0] and not api.clients
    api.active = False
    service.generate()
    assert not api.clients and "Enable" in service.status
    assert service.source_url() == ""


def test_browser_client_layouts_auth_and_untrusted_metadata():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is needed for the standalone OBS browser-client check")
    script = Path(__file__).with_name("check_obs_client.cjs")
    subprocess.run([node, str(script)], check=True, timeout=15)


def test_failed_revocation_does_not_claim_success_or_create_another_client(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    api = Api()
    service = ObsOverlay(api, tmp_path / "settings.ini")
    service.generate()
    original = service.source_url()
    api.revokeClient = lambda identifier: False
    service.revoke()
    assert service.hasClient and service.hasSource and "could not" in service.status
    service.generate()
    assert len(api.clients) == 1 and service.source_url() == original
