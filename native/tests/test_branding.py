"""Display branding must not move existing accounts, package or integration identities."""
from pathlib import Path
import tomllib

import pytest

from youtube_music_native.account.credentials import SERVICE, USERNAME
from youtube_music_native.system.startup import APP_ID


NATIVE = Path(__file__).resolve().parents[1]


def test_tubify_display_name_preserves_package_desktop_and_credential_ids():
    package = tomllib.loads((NATIVE / "pyproject.toml").read_text())
    assert package["project"]["description"].startswith("Tubify")
    assert package["project"]["name"] == "youtube-music-native"
    # tubify is the command users see; the original names keep existing launchers working.
    assert package["project"]["scripts"] == {
        "tubify": "youtube_music_native.launcher:main",
        "tubify-check": "youtube_music_native.launcher:compat_main",
        "youtube-music-native": "youtube_music_native.launcher:main",
        "youtube-music-native-check": "youtube_music_native.launcher:compat_main",
    }
    desktop = dict(line.split("=", 1) for line in
        (NATIVE.parent / "packaging/linux/youtube-music-native.desktop").read_text().splitlines() if "=" in line)
    assert desktop["Name"] == "Tubify"
    assert desktop["Exec"] == "youtube-music-native -- %u"
    assert desktop["MimeType"] == "x-scheme-handler/ytmusic-native;"
    assert desktop["StartupWMClass"] == "youtube-music-native"
    assert desktop["Icon"] == "tubify"
    packaging = (NATIVE.parent / "packaging/linux/PKGBUILD").read_text()
    assert '$pkgdir/usr/share/icons/hicolor/scalable/apps/tubify.svg' in packaging
    assert APP_ID == "studio.nouvellelune.tubify"
    assert (SERVICE, USERNAME) == ("studio.nouvellelune.tubify", "session")


def test_the_old_personal_identifier_is_only_used_to_clean_up():
    # Old entries must be found to be removed, so the name stays in exactly these two modules.
    allowed = {"account/credentials.py", "system/startup.py"}
    package = NATIVE / "src/youtube_music_native"
    found = {str(path.relative_to(package)).replace("\\", "/") for path in package.rglob("*")
             if path.suffix in {".py", ".qml", ".js"} and "com.carter" in path.read_text(encoding="utf-8")}
    assert found == allowed
    for spec in ("macos", "windows"):
        assert "com.carter" not in (NATIVE.parent / "packaging" / spec / "Tubify.spec").read_text(encoding="utf-8")


def test_mpris_display_branding_keeps_desktop_and_bus_identifiers():
    pytest.importorskip("jeepney")
    from youtube_music_native.system.linux_media import ROOT, PATH, ROOT_VALUES
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
