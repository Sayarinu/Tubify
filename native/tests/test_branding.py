"""Tubify names the package, commands and integrations; credential and login ids stay put."""
from pathlib import Path
import tomllib

import pytest

from tubify.account.credentials import SERVICE, USERNAME
from tubify.system.startup import APP_ID


NATIVE = Path(__file__).resolve().parents[1]


def test_tubify_names_package_desktop_and_keeps_credential_ids():
    package = tomllib.loads((NATIVE / "pyproject.toml").read_text())
    assert package["project"]["description"].startswith("Tubify")
    assert package["project"]["name"] == "tubify"
    assert package["project"]["scripts"] == {
        "tubify": "tubify.launcher:main",
        "tubify-check": "tubify.launcher:compat_main",
    }
    desktop = dict(line.split("=", 1) for line in
        (NATIVE.parent / "packaging/linux/tubify.desktop").read_text().splitlines() if "=" in line)
    assert desktop["Name"] == "Tubify"
    assert desktop["Exec"] == "tubify -- %u"
    assert desktop["MimeType"] == "x-scheme-handler/ytmusic-native;"
    assert desktop["StartupWMClass"] == "tubify"
    assert desktop["Icon"] == "tubify"
    packaging = (NATIVE.parent / "packaging/linux/PKGBUILD").read_text()
    assert '$pkgdir/usr/share/icons/hicolor/scalable/apps/tubify.svg' in packaging
    assert APP_ID == "studio.nouvellelune.tubify"
    assert (SERVICE, USERNAME) == ("studio.nouvellelune.tubify", "session")


def test_the_old_personal_identifier_is_only_used_to_clean_up():
    # Old entries must be found to be removed, so the name stays in exactly these two modules.
    allowed = {"account/credentials.py", "system/startup.py"}
    package = NATIVE / "src/tubify"
    found = {str(path.relative_to(package)).replace("\\", "/") for path in package.rglob("*")
             if path.suffix in {".py", ".qml", ".js"} and "com.carter" in path.read_text(encoding="utf-8")}
    assert found == allowed
    # The Linux source package doesn't include the other platforms' packaging.
    for spec in (NATIVE.parent / "packaging").glob("*/Tubify.spec"):
        assert "com.carter" not in spec.read_text(encoding="utf-8")


def test_mpris_display_branding_keeps_desktop_and_bus_identifiers():
    pytest.importorskip("jeepney")
    from tubify.system.linux_media import ROOT, PATH, ROOT_VALUES
    assert ROOT_VALUES["Identity"] == ("s", "Tubify")
    assert ROOT_VALUES["DesktopEntry"] == ("s", "tubify")
    assert ROOT == "org.mpris.MediaPlayer2" and PATH == "/org/mpris/MediaPlayer2"


def test_tubify_icon_renders_at_small_launcher_and_tray_sizes():
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer
    renderer = QSvgRenderer(str(NATIVE / "src/tubify/assets/music.svg"))
    assert renderer.isValid()
    for size in (16, 24, 32):
        image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        renderer.render(painter)
        painter.end()
        assert sum(image.pixelColor(x, y).alpha() > 0 for x in range(size) for y in range(size)) > size
