"""Tubify entry point, shared by Linux, Windows and macOS."""

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

from PySide6.QtCore import QEvent, QStandardPaths, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QIcon, QPalette, QWindow
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication

from .shell import ShellController
from .account.account import Account
from .artwork.artwork import ArtworkCache
from .catalog.catalog_view import CatalogView
from .jobs import Worker
from .playback.playback import Playback
from .playback.playback_options import PlaybackOptions
from .catalog.browse import Browse
from .downloads.download_view import DownloadView
from .catalog.actions import Actions
from .catalog.search import Search
from .catalog.library import Library
from .playback.listening import Listening
from .integrations.lastfm import LastFm
from .integrations.deep_links import DeepLinks, LinkError
from .integrations.link_instance import LinkInstance
from .lyrics.lyric_view import LyricView
from .system.desktop import Desktop
from .catalog.artist_preview import ArtistPreview
from .integrations.cast_receiver import CastReceiver
from .integrations.discord_presence import DiscordPresence
from .integrations.handoff import Handoff
from .system.tray import TrayPlayer
from .system.lifecycle import Lifecycle
from .system.startup import StartupRegistration
from .system.macos import trusts_certificates
from .theme import ThemeState
from .system.color_picker import ColorSampler
from .updates.maintenance import Maintenance


PACKAGE = Path(__file__).resolve().parent


def load_window(controller, account, player, catalog=None, artwork_path=None, browse=None, downloads=None, search=None, actions=None, library=None, lyrics=None, theme=None, color_sampler=None):
    from PySide6.QtQml import qmlRegisterType
    from .playback.video import VideoSurface

    qmlRegisterType(VideoSurface, "Tubify.Video", 1, 0, "VideoSurface")
    engine = QQmlApplicationEngine()
    engine.setProperty("qmlWarnings", [])
    engine.warnings.connect(lambda warnings: engine.setProperty("qmlWarnings", engine.property("qmlWarnings") + [str(w) for w in warnings]))
    engine.rootContext().setContextProperty("appState", controller)
    engine.rootContext().setContextProperty("accountState", account)
    engine.rootContext().setContextProperty("playerState", player)
    if hasattr(controller, "maintenanceState"):
        engine.rootContext().setContextProperty("maintenanceState", controller.maintenanceState)
    if hasattr(controller, "discordState"):
        engine.rootContext().setContextProperty("discordState", controller.discordState)
    if hasattr(controller, "artistPreview"):
        engine.rootContext().setContextProperty("artistPreview", controller.artistPreview)
    if hasattr(controller, "castState"):
        engine.rootContext().setContextProperty("castState", controller.castState)
    if hasattr(controller, "trayState"):
        engine.rootContext().setContextProperty("trayState", controller.trayState)
    if hasattr(controller, "lifecycleState"):
        engine.rootContext().setContextProperty("lifecycleState", controller.lifecycleState)
    if hasattr(controller, "playbackOptions"):
        engine.rootContext().setContextProperty("playbackOptions", controller.playbackOptions)
    if hasattr(controller, "linkState"):
        engine.rootContext().setContextProperty("linkState", controller.linkState)
    if hasattr(controller, "lastFm"):
        engine.rootContext().setContextProperty("lastFmState", controller.lastFm)
    if hasattr(controller, "handoffState"):
        engine.rootContext().setContextProperty("handoffState", controller.handoffState)
    if theme:
        engine.rootContext().setContextProperty("themeState", theme)
    if color_sampler:
        engine.rootContext().setContextProperty("colorSampler", color_sampler)
    if catalog:
        engine.rootContext().setContextProperty("catalogState", catalog)
    if browse:
        engine.rootContext().setContextProperty("browseState", browse)
    if downloads:
        engine.rootContext().setContextProperty("downloadsState", downloads)
    if search:
        engine.rootContext().setContextProperty("searchState", search)
    if actions:
        engine.rootContext().setContextProperty("actionsState", actions)
    if library:
        engine.rootContext().setContextProperty("libraryState", library)
    if lyrics:
        engine.rootContext().setContextProperty("lyricState", lyrics)
    if artwork_path:
        # QQmlEngine does not take ownership of this factory.
        engine.artworkFactory = ArtworkCache(artwork_path)
        engine.setNetworkAccessManagerFactory(engine.artworkFactory)
    engine.load(QUrl.fromLocalFile(str(PACKAGE / "qml" / "Main.qml")))
    return engine


# The prefetch worker starts a little after the click worker so the two do not compete
# for imports and the keyring read at launch.
PREFETCH_PRESTART_MS = 3000


def start_resolvers(app, player, source_worker, prefetch_worker):
    """Warm both resolve workers and libmpv before the first click needs them."""
    QTimer.singleShot(0, source_worker.prestart)
    QTimer.singleShot(0, player.prepareAudio)
    # The prefetch worker also serves hover warms and clicks made while the click
    # worker is still busy, so it should be warm too.
    QTimer.singleShot(PREFETCH_PRESTART_MS, prefetch_worker.prestart)
    # Coming back to the window means a click may follow.
    app.applicationStateChanged.connect(
        lambda state: player.keepWarm() if state == Qt.ApplicationState.ApplicationActive else None)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Tubify, a desktop app for YouTube Music")
    parser.add_argument("--fixture", action="store_true", help="Render synthetic data for visual verification")
    parser.add_argument("--smoke-test", action="store_true", help="Verify window creation and exit")
    parser.add_argument("--screenshot", type=Path, help="Save a visual-verification screenshot and exit")
    parser.add_argument("--data-dir", type=Path, help="Override application data for isolated development/tests")
    parser.add_argument("links", nargs="*", help="YouTube Music URLs or Tubify links")
    parser.add_argument("--software-rendering", action="store_true", help="Use software drawing for this launch when troubleshooting graphics")
    args = parser.parse_args(argv)
    if args.software_rendering:
        os.environ["QT_QUICK_BACKEND"] = "software"
    if len(args.links) > 1:
        parser.error("Open one music link at a time.")
    QGuiApplication.setOrganizationName("YouTubeMusicNative")
    QGuiApplication.setOrganizationDomain("com.carter")
    QGuiApplication.setApplicationName("youtube-music-native")
    QGuiApplication.setApplicationDisplayName("Tubify")
    QQuickStyle.setStyle("Basic")
    app = QApplication([sys.argv[0]])
    cleanup = []
    def on_quit(callback):
        called = False
        def once():
            nonlocal called
            if not called:
                called = True
                callback()
        cleanup.append(once)
        app.aboutToQuit.connect(once)

    app.setDesktopFileName("youtube-music-native")
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
    instance = None
    if not (args.fixture or args.smoke_test or args.screenshot):
        instance = LinkInstance(data, app)
        try:
            if not instance.claim_or_forward(args.links):
                return 0
        except LinkError as error:
            print(str(error), file=sys.stderr)
            instance.close()
            return 1
        app.installEventFilter(instance)
    if args.data_dir or args.smoke_test or args.screenshot:
        cache = data / "cache"
    else:
        cache = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation))
    cache.mkdir(parents=True, exist_ok=True, mode=0o700)
    fixture = json.loads((PACKAGE / "assets" / "visual-fixture.json").read_text()) if args.fixture else None
    controller = ShellController(data / "settings.ini", fixture)
    controller.maintenanceState = Maintenance(cache / "native-release.json", controller, parent=controller, fixture=args.fixture, software=args.software_rendering)
    theme = ThemeState(data / "theme.ini")
    color_sampler = ColorSampler()

    def apply_theme_palette():
        palette = QPalette()
        for role, color in (
            (QPalette.ColorRole.Window, theme.background),
            (QPalette.ColorRole.WindowText, theme.foreground),
            (QPalette.ColorRole.Base, theme.background),
            (QPalette.ColorRole.AlternateBase, theme.surface),
            (QPalette.ColorRole.Text, theme.foreground),
            (QPalette.ColorRole.Button, theme.surface),
            (QPalette.ColorRole.ButtonText, theme.foreground),
            (QPalette.ColorRole.Highlight, theme.accent),
            (QPalette.ColorRole.HighlightedText, theme.onAccent),
        ):
            palette.setColor(role, QColor(color))
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(theme.muted))
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(theme.muted))
        QGuiApplication.setPalette(palette)

    apply_theme_palette()
    theme.paletteChanged.connect(apply_theme_palette)
    media_data = data if args.data_dir or args.smoke_test or args.screenshot else Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))
    media_data.mkdir(parents=True, exist_ok=True, mode=0o700)
    account = Account(data / "settings.ini", fixture=args.fixture, parent=controller)
    catalog = CatalogView(account.worker, cache / "metadata.sqlite3", account, parent=controller)
    # Clicks and prefetches resolve in separate warm workers so a click never waits
    # behind, or kills, a prefetch. Both restart warm after an account change.
    warmup = ("warmup", {"data_dir": str(media_data)})
    source_worker = None if args.fixture else Worker(controller, idle_ms=10 * 60 * 1000, warmup=warmup)
    prefetch_worker = None if args.fixture else Worker(controller, idle_ms=5 * 60 * 1000, warmup=warmup)
    player = Playback(media_data, source_worker, account.worker, cache / "metadata.sqlite3", fixture=fixture, parent=controller, prefetch_worker=prefetch_worker)
    if source_worker and not (args.smoke_test or args.screenshot):
        start_resolvers(app, player, source_worker, prefetch_worker)
    controller.discordState = DiscordPresence(player, data / "settings.ini", parent=controller, fixture=args.fixture)
    on_quit(controller.discordState.close)
    controller.playbackOptions = PlaybackOptions(data / "settings.ini", player, parent=controller)
    controller.trayState = TrayPlayer(controller, player, data / "settings.ini", PACKAGE / "assets" / "music.svg", parent=controller)
    controller.lifecycleState = Lifecycle(data / "settings.ini", player, controller.trayState, parent=controller,
                                          startup=StartupRegistration(disabled_reason="Login startup is unavailable in visual fixtures." if args.fixture else ""))
    downloads = DownloadView(media_data, fixture=args.fixture, parent=controller)
    player.trackStarted.connect(lambda track: downloads.refresh())
    account.connectedChanged.connect(lambda: downloads.setAccountAvailable(account.connected))
    account.sessionChanged.connect(downloads.resetSession)
    # Kept for a few minutes so playing several long playlists in a row stays warm.
    pages = None if args.fixture else Worker(controller, idle_ms=3 * 60 * 1000)
    if pages:
        on_quit(pages.close)
    browse = Browse(controller, account, catalog, player, cache / "metadata.sqlite3", fixture=fixture, parent=controller, downloads=downloads, pages=pages)
    controller.linkState = DeepLinks(browse, account, downloads, cache / "metadata.sqlite3", parent=controller, fixture=args.fixture)
    on_quit(controller.linkState.close)
    controller.handoffState = Handoff(player, parent=controller)
    controller.artistPreview = ArtistPreview(player, controller, account.worker, cache / "metadata.sqlite3", parent=controller, fixture=args.fixture)
    controller.castState = CastReceiver(player, controller, data / "settings.ini", account.worker, cache / "metadata.sqlite3", parent=controller, fixture=args.fixture)
    on_quit(controller.castState.close)
    search = Search(controller, account, catalog, cache / "metadata.sqlite3", fixture=fixture, parent=controller)
    actions = Actions(account, cache / "metadata.sqlite3", fixture=args.fixture, parent=controller)
    actions.applied.connect(browse.applyAction)
    library = Library(controller, account, catalog, player, browse, actions, cache / "metadata.sqlite3", fixture=fixture, parent=controller)
    controller.lastFm = LastFm(player, data / "settings.ini", media_data, parent=controller, fixture=args.fixture)
    Listening(account, player, cache / "metadata.sqlite3", parent=controller)  # kept alive by its Qt parent
    lyrics = LyricView(account, player, media_data, fixture=args.fixture, parent=controller, settings_path=data / "settings.ini")
    lyrics.openRequested.connect(lambda: controller.setLyricsOpen(True))
    player.trackStarted.connect(lyrics.playbackStarted)
    player.setVolume(controller.volume)
    controller.volumeChanged.connect(lambda: player.setVolume(controller.volume))
    controller.actionRequested.connect(player.handleAction)
    on_quit(controller.lastFm.close)
    on_quit(account.close)
    on_quit(player.close)
    on_quit(controller.maintenanceState.close)
    on_quit(controller.playbackOptions.close)
    on_quit(controller.lifecycleState.close)
    on_quit(controller.trayState.close)
    on_quit(downloads.close)
    on_quit(lyrics.close)
    engine = load_window(controller, account, player, catalog, cache / "artwork", browse, downloads, search, actions, library, lyrics, theme, color_sampler)
    if not engine.rootObjects():
        return 1
    window = engine.rootObjects()[0]
    if args.smoke_test and getattr(sys, "frozen", False):
        if controller.maintenanceState.currentVersion == "unknown":
            raise RuntimeError("Packaged version metadata is missing")
        if sys.platform == "darwin":
            from .system.macos_updates import MacUpdater
            controller.maintenanceState._mac = MacUpdater(lambda: None)
        if sys.platform == "win32":
            # Media keys need every WinRT projection the controls touch to be bundled.
            from .system.windows_media import require_projections
            require_projections()
    controller.maintenanceState.window = window
    controller.maintenanceState.prepare_restart = lambda: [callback() for callback in cleanup]
    if not (args.fixture or args.smoke_test or args.screenshot):
        controller.maintenanceState.start()
    if not args.fixture:
        controller.restoreWindow(window, [screen.availableGeometry() for screen in app.screens()])
    controller.trayState.start(window)
    controller.lifecycleState.start(window)
    def show_for_link():
        window.showNormal() if window.visibility() == QWindow.Visibility.Minimized else window.show()
        window.raise_()
        window.requestActivate()

    def receive_links(links):
        show_for_link()
        if links:
            controller.linkState.receive(links[0])

    controller.linkState.activateRequested.connect(show_for_link)
    if instance:
        instance.linksReceived.connect(receive_links)
        instance.linkRejected.connect(controller.linkState.reportError)
        QTimer.singleShot(0, instance.ready)
    elif args.links:
        QTimer.singleShot(0, lambda: receive_links(args.links))
    desktop = None if args.fixture else Desktop(controller, player, window, downloads, parent=controller)
    if desktop:
        on_quit(desktop.close)

    if instance:
        on_quit(instance.close)

    def finish():
        warnings = engine.property("qmlWarnings")
        failed = bool(warnings)
        if warnings:
            print("Qt Quick reported QML warnings:", file=sys.stderr)
            for warning in warnings:
                print(warning, file=sys.stderr)
        if args.screenshot:
            args.screenshot.parent.mkdir(parents=True, exist_ok=True)
            image = window.grabWindow()
            failed = failed or image.isNull() or not image.save(str(args.screenshot))
        if not trusts_certificates():
            print("HTTPS has no trusted certificates.", file=sys.stderr)
            failed = True
        window.close()
        app.exit(1 if failed else 0)

    if args.smoke_test and args.fixture:
        QTimer.singleShot(200, lambda: controller.navigate("Explore"))
        QTimer.singleShot(400, lambda: browse.shortcut("releases"))
        QTimer.singleShot(600, lambda: browse.open({"kind": "album", "title": "Fixture album"}))
        QTimer.singleShot(800, lambda: browse.open({"kind": "artist", "id": "UCfixture", "title": "Fixture artist"}))
        QTimer.singleShot(1000, lambda: controller.search("fixture music"))
        QTimer.singleShot(1200, lambda: browse.shortcut("moods"))
        QTimer.singleShot(1400, lambda: (window.resize(920, 620), controller.navigate("Home")))
        QTimer.singleShot(1700, finish)
    elif args.smoke_test or args.screenshot:
        QTimer.singleShot(700, finish)
    result = app.exec()
    # Destroy QML bindings before their Python context disappears.
    engine.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
