"""Native Qt entry point, shared by Linux, Windows and macOS."""

import argparse
import json
from pathlib import Path
import sys
import tempfile

from PySide6.QtCore import QStandardPaths, QTimer, QUrl
from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

from .shell import ShellController
from .account import Account
from .artwork import ArtworkCache
from .catalog_view import CatalogView
from .jobs import Worker
from .playback import Playback
from .browse import Browse


PACKAGE = Path(__file__).resolve().parent


def load_window(controller, account, player, catalog=None, artwork_path=None, browse=None):
    engine = QQmlApplicationEngine()
    engine.setProperty("qmlWarnings", [])
    engine.warnings.connect(lambda warnings: engine.setProperty("qmlWarnings", engine.property("qmlWarnings") + [str(w) for w in warnings]))
    engine.rootContext().setContextProperty("appState", controller)
    engine.rootContext().setContextProperty("accountState", account)
    engine.rootContext().setContextProperty("playerState", player)
    if catalog:
        engine.rootContext().setContextProperty("catalogState", catalog)
    if browse:
        engine.rootContext().setContextProperty("browseState", browse)
    if artwork_path:
        # QQmlEngine does not take ownership of this factory.
        engine.artworkFactory = ArtworkCache(artwork_path)
        engine.setNetworkAccessManagerFactory(engine.artworkFactory)
    engine.load(QUrl.fromLocalFile(str(PACKAGE / "qml" / "Main.qml")))
    return engine


def main(argv=None):
    parser = argparse.ArgumentParser(description="YouTube Music native Qt client")
    parser.add_argument("--fixture", action="store_true", help="Render synthetic data for visual verification")
    parser.add_argument("--smoke-test", action="store_true", help="Verify window creation and exit")
    parser.add_argument("--screenshot", type=Path, help="Save a visual-verification screenshot and exit")
    parser.add_argument("--data-dir", type=Path, help="Override application data for isolated development/tests")
    args = parser.parse_args(argv)
    QGuiApplication.setOrganizationName("YouTubeMusicNative")
    QGuiApplication.setOrganizationDomain("com.carter")
    QGuiApplication.setApplicationName("youtube-music-native")
    QGuiApplication.setApplicationDisplayName("YouTube Music")
    QQuickStyle.setStyle("Basic")
    app = QGuiApplication([sys.argv[0]])
    app.setWindowIcon(QIcon(str(PACKAGE / "assets" / "music.svg")))
    for font in (PACKAGE / "assets").glob("*.ttf"):
        QFontDatabase.addApplicationFont(str(font))
    default_font = QFont("Roboto")
    default_font.setPixelSize(14)
    app.setFont(default_font)
    if args.data_dir:
        data = args.data_dir
    elif args.smoke_test or args.screenshot:
        data = Path(tempfile.mkdtemp(prefix="youtube-music-native-ui-"))
    else:
        data = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation))
    data.mkdir(parents=True, exist_ok=True, mode=0o700)
    if args.data_dir or args.smoke_test or args.screenshot:
        cache = data / "cache"
    else:
        cache = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation))
    cache.mkdir(parents=True, exist_ok=True, mode=0o700)
    fixture = json.loads((PACKAGE / "assets" / "visual-fixture.json").read_text()) if args.fixture else None
    controller = ShellController(data / "settings.ini", fixture)
    account = Account(data / "settings.ini", fixture=args.fixture, parent=controller)
    catalog = CatalogView(account.worker, cache / "metadata.sqlite3", account, parent=controller)
    media_data = data if args.data_dir or args.smoke_test or args.screenshot else Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))
    media_data.mkdir(parents=True, exist_ok=True, mode=0o700)
    source_worker = None if args.fixture else Worker(controller, idle_ms=15000)
    player = Playback(media_data, source_worker, account.worker, cache / "metadata.sqlite3", fixture=fixture, parent=controller)
    browse = Browse(controller, account, catalog, player, cache / "metadata.sqlite3", fixture=fixture, parent=controller)
    player.setVolume(controller.volume)
    controller.volumeChanged.connect(lambda: player.setVolume(controller.volume))
    controller.actionRequested.connect(player.handleAction)
    app.aboutToQuit.connect(account.close)
    app.aboutToQuit.connect(player.close)
    engine = load_window(controller, account, player, catalog, cache / "artwork", browse)
    if not engine.rootObjects():
        return 1
    window = engine.rootObjects()[0]

    def finish():
        failed = bool(engine.property("qmlWarnings"))
        if args.screenshot:
            args.screenshot.parent.mkdir(parents=True, exist_ok=True)
            image = window.grabWindow()
            failed = failed or image.isNull() or not image.save(str(args.screenshot))
        window.close()
        app.exit(1 if failed else 0)

    if args.smoke_test and args.fixture:
        QTimer.singleShot(200, lambda: controller.navigate("Explore"))
        QTimer.singleShot(400, lambda: browse.shortcut("releases"))
        QTimer.singleShot(600, lambda: browse.open({"kind": "album", "title": "Fixture album"}))
        QTimer.singleShot(800, lambda: browse.shortcut("moods"))
        QTimer.singleShot(1000, lambda: (window.resize(920, 620), controller.navigate("Home")))
        QTimer.singleShot(1300, finish)
    elif args.smoke_test or args.screenshot:
        QTimer.singleShot(700, finish)
    result = app.exec()
    # Destroy QML bindings before their Python context disappears.
    engine.deleteLater()
    app.processEvents()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
