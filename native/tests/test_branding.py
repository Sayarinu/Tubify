"""Display branding must not move existing accounts, package or integration identities."""
import json
from pathlib import Path
import tomllib

import pytest

from youtube_music_native.credentials import SERVICE, USERNAME
from youtube_music_native.startup import APP_ID


NATIVE = Path(__file__).resolve().parents[1]


def test_tubify_display_name_preserves_package_desktop_and_credential_ids():
    package = tomllib.loads((NATIVE / "pyproject.toml").read_text())
    assert package["project"]["description"].startswith("Tubify")
    assert package["project"]["name"] == "youtube-music-native"
    assert package["project"]["scripts"] == {
        "youtube-music-native": "youtube_music_native.launcher:main",
        "youtube-music-native-check": "youtube_music_native.launcher:compat_main",
    }
    desktop = dict(line.split("=", 1) for line in
        (NATIVE.parent / "packaging/arch-native/youtube-music-native.desktop").read_text().splitlines() if "=" in line)
    assert desktop["Name"] == "Tubify"
    assert desktop["Exec"] == "youtube-music-native -- %u"
    assert desktop["MimeType"] == "x-scheme-handler/ytmusic-native;"
    assert desktop["StartupWMClass"] == "youtube-music-native"
    assert desktop["Icon"] == "tubify"
    packaging = (NATIVE.parent / "packaging/arch-native/PKGBUILD").read_text()
    assert '$pkgdir/usr/share/icons/hicolor/scalable/apps/tubify.svg' in packaging
    assert APP_ID == "com.carter.youtube-music-native"
    assert (SERVICE, USERNAME) == ("com.carter.youtube-music.native", "session")


def test_tubify_integration_labels_preserve_existing_plugin_and_userscript_ids():
    manifest = json.loads((NATIVE / "integrations/streamdeck/com.carter.youtube-music.sdPlugin/manifest.json").read_text())
    assert manifest["Name"] == manifest["Category"] == "Tubify"
    assert manifest["UUID"] == "com.carter.youtube-music"
    actions = {"toggle", "play", "pause", "previous", "next", "stop", "like", "dislike", "shuffle", "repeat", "volume-up", "volume-down", "volume", "track"}
    assert {action["UUID"] for action in manifest["Actions"]} == {"com.carter.youtube-music." + name for name in actions}
    userscript = (NATIVE / "integrations/browser-handoff.user.js").read_text()
    assert "// @name         YouTube Music Native handoff" in userscript
    assert "// @namespace    com.carter.youtube-music.native" in userscript
    assert "Open in Tubify" in userscript and "ytmusic-native://" in userscript


def test_mpris_display_branding_keeps_desktop_and_bus_identifiers():
    pytest.importorskip("jeepney")
    from youtube_music_native.linux_media import ROOT, PATH, ROOT_VALUES
    assert ROOT_VALUES["Identity"] == ("s", "Tubify")
    assert ROOT_VALUES["DesktopEntry"] == ("s", "youtube-music-native")
    assert ROOT == "org.mpris.MediaPlayer2" and PATH == "/org/mpris/MediaPlayer2"


def test_tubify_icon_renders_at_small_launcher_and_tray_sizes():
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer
    renderer = QSvgRenderer(str(NATIVE / "src/youtube_music_native/assets/music.svg"))
    assert renderer.isValid()
    for size in (16, 24, 32):
        image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        renderer.render(painter)
        painter.end()
        assert sum(image.pixelColor(x, y).alpha() > 0 for x in range(size) for y in range(size)) > size
