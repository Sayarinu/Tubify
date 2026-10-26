"""Render every view, check accessible controls and stress virtualized lists."""

import argparse
import json
from pathlib import Path
import tempfile
import time
import traceback
import wave

from PySide6.QtCore import QObject, QMetaObject, QPointF, QTimer, Qt
from PySide6.QtGui import QAccessible, QColor, QGuiApplication, QImage
from PySide6.QtQml import QQmlProperty
from PySide6.QtTest import QTest

from youtube_music_native import app


def visual_items(item):
    yield item
    for child in item.childItems():
        yield from visual_items(child)


def fully_visible(item):
    if not item.isVisible():
        return False
    parent = item.parentItem()
    while parent:
        if parent.clip():
            position = item.mapToItem(parent, item.boundingRect().topLeft())
            if position.x() < 0 or position.y() < 0 or position.x() + item.width() > parent.width() or position.y() + item.height() > parent.height():
                return False
        parent = parent.parentItem()
    return True


def check_queue(window, shell, player, browse, downloads, output_dir, exercise):
    pane = window.findChild(QObject, "queuePane")
    listing = window.findChild(QObject, "queueUpcomingList")
    now = window.findChild(QObject, "queueNowPlayingPanel")
    sidebar = window.findChild(QObject, "queueSidebar")
    bar = window.findChild(QObject, "queueSidebarScrollbar")
    assert pane and listing and now and sidebar and sidebar.isVisible()
    assert listing.mapToScene(QPointF()).y() == now.mapToScene(QPointF()).y() + now.height()
    assert not window.findChild(QObject, "queueHistoryList")
    assert not window.findChild(QObject, "pinnedQueueNextList")
    assert not any(entry["group"] == "Previously played" for entry in player.entries)
    upcoming = [entry for entry in player.entries if not entry["current"]]
    source = [entry for entry in upcoming if entry["group"] != "Next in queue"]
    assert listing.property("count") == len(upcoming) + 3 + int(not source)
    assert bar.mapToScene(QPointF()).x() >= listing.mapToScene(QPointF()).x() + listing.width() - 1
    assert bar.mapToScene(QPointF()).x() + bar.width() <= sidebar.mapToScene(QPointF()).x() + sidebar.width()
    if not exercise:
        return

    snapshot = player.queue.snapshot(player.position)
    fixture = dict(player.currentTrack)
    tracks = [{**fixture, "title": "Queue fixture " + str(i)} for i in range(7)]

    def item(name):
        return next(child for child in visual_items(window.contentItem()) if child.objectName() == name and child.isVisible())

    def row(key):
        return item("queueSidebarSong-" + key)

    def settle():
        QTest.qWait(70)

    def save(name):
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            window.grabWindow().save(str(output_dir / (name + ".png")))

    def drag(key, target, handle=True):
        origin = item("queueSidebarDrag-" + key) if handle else row(key)
        point = origin.boundingRect().center() if handle else QPointF(20, origin.height() / 2)
        start = origin.mapToScene(point).toPoint()
        QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(window, start + QPointF(0, 12).toPoint(), delay=25)
        QTest.mouseMove(window, target, delay=25)
        settle()
        preview = item("queueDragPreview")
        assert preview.isVisible() and pane.property("draggingKey") == key
        assert pane.property("dropKey") or pane.property("dropToManual")
        QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=target)
        settle()
        assert not pane.property("draggingKey")

    player.clearManualQueue()
    player.playTracks(tracks, source_label="Fixture source")
    player.next()
    history_key = player.queue.history[0]["key"]
    player.enqueue([tracks[0], tracks[0]])
    settle()
    assert not any(child.objectName() == "queueSidebarSong-" + history_key for child in visual_items(pane))
    assert item("queueNextHeading").property("text") == "Next From Fixture source"
    save("queue-mixed")
    manual = [entry["key"] for entry in player.queue.manual]
    # Equal video IDs remain separate occurrences, with only the pinned row current.
    assert not row(manual[0]).property("currentSong")
    assert row(player.queue.current["key"]).property("currentSong")
    drag(manual[0], row(manual[1]).mapToScene(QPointF(20, 52)).toPoint())
    assert [entry["key"] for entry in player.queue.manual] == manual[::-1]
    source = [entry["key"] for entry in player.queue.remaining]
    drag(source[0], row(source[1]).mapToScene(QPointF(20, 52)).toPoint(), handle=False)
    assert [entry["key"] for entry in player.queue.remaining][:2] == source[1::-1]
    source_key = player.queue.remaining[0]["key"]
    drag(source_key, row(player.queue.manual[0]["key"]).mapToScene(QPointF(20, 2)).toPoint())
    assert player.queue.manual[0]["key"] == source_key
    player.clearManualQueue()
    settle()
    source_key = player.queue.remaining[0]["key"]
    target = item("queueSidebarAddToQueueDrop")
    assert target.height() == 48
    drag(source_key, target.mapToScene(target.boundingRect().center()).toPoint(), handle=False)
    assert player.manualCount == 1 and player.queue.manual[-1]["key"] == source_key
    another = player.queue.remaining[0]["key"]
    row(another).forceActiveFocus()
    QTest.keyClick(window, Qt.Key.Key_Right, Qt.KeyboardModifier.AltModifier)
    settle()
    assert [entry["key"] for entry in player.queue.manual] == [source_key, another]
    assert row(another).hasActiveFocus()
    QTest.keyClick(window, Qt.Key.Key_Up, Qt.KeyboardModifier.AltModifier)
    settle()
    assert [entry["key"] for entry in player.queue.manual] == [another, source_key]
    assert row(another).hasActiveFocus()
    QTest.keyClick(window, Qt.Key.Key_Delete)
    settle()
    assert [entry["key"] for entry in player.queue.manual] == [source_key]
    # The clear control must stay available while an asynchronous addition is pending.
    browse.additions.jobs.append({"media": {"kind": "playlist", "id": "PLfixture"}})
    browse.additions.changed.emit()
    settle()
    clear = item("queueClearButton")
    assert clear.isEnabled() and clear.property("text") == "Cancel"
    clear.clicked.emit()
    settle()
    assert not browse.queueBusy and not player.manualCount
    # Completed/progress indicators stay present without hovering, including narrow docks.
    saved_download_states = dict(downloads._track_states)
    saved_width = shell.queueWidth
    shell.setQueueWidth(280)
    downloads._track_states = {fixture["videoId"]: "ready"}
    downloads.changed.emit()
    settle()
    download = item("queueRowDownload-" + player.queue.current["key"])
    assert download.isVisible() and download.property("status") == "ready"
    metadata = item("queueRowMetadata-" + player.queue.current["key"])
    assert metadata.width() >= 100
    assert metadata.x() + metadata.width() <= download.x()
    save("queue-narrow-downloaded")
    downloads._track_states = {fixture["videoId"]: "downloading"}
    downloads.changed.emit()
    settle()
    assert download.isVisible() and download.property("status") == "downloading"
    downloads._track_states = saved_download_states
    downloads.changed.emit()
    shell.setQueueWidth(saved_width)
    settle()
    save("queue-source-only")

    player.playTracks([])
    settle()
    assert listing.property("count") == 4
    assert now.isVisible() and item("queueSidebarAddToQueueDrop").height() == 48
    save("queue-empty")
    player.playTracks([fixture], source_label="Fixture source")
    player.enqueue([fixture] * 10000)
    settle()
    assert listing.property("count") == 10004
    # Qt estimates total height while only visible delegates exist.
    assert listing.property("contentHeight") > 64 * 9000, listing.property("contentHeight")
    fixed_y = now.mapToScene(QPointF()).y()
    listing.positionViewAtEnd()
    settle()
    assert now.mapToScene(QPointF()).y() == fixed_y and now.isVisible()
    assert item("queueSidebarAddToQueueDrop").height() == 48
    count = sum(child.metaObject().className().startswith("SongRow_") for child in visual_items(pane))
    assert 0 < count < 50, count
    save("queue-long-manual-end")
    listing.positionViewAtBeginning()
    settle()
    save("queue-long-manual-top")
    first = player.queue.manual[0]["key"]
    row(first).forceActiveFocus()
    start = item("queueSidebarDrag-" + first).mapToScene(QPointF(14, 22)).toPoint()
    edge = listing.mapToScene(QPointF(listing.width() - 14, listing.height() - 12)).toPoint()
    before = listing.property("contentY")
    QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(window, start + QPointF(0, 12).toPoint(), delay=25)
    QTest.mouseMove(window, edge, delay=25)
    QTest.qWait(250)
    assert pane.property("draggingKey") == first
    assert listing.property("contentY") > before
    QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=edge)
    settle()
    assert player.queue.manual[0]["key"] != first and player.manualCount == 10000
    player.clearManualQueue()
    player._position = player.queue.restore(snapshot)
    player.changed.emit()
    settle()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--native-gpu", action="store_true")
    parser.add_argument("--soak-seconds", type=int, default=0)
    args = parser.parse_args()
    original = app.load_window
    passed, results = [], []
    if args.native_gpu:
        from PySide6.QtQuick import QQuickWindow, QSGRendererInterface
        QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.OpenGL)
        engine_type = app.QQmlApplicationEngine
        class Engine(engine_type):
            def __init__(self):
                super().__init__()
                self.setInitialProperties({"flags": Qt.WindowType.Window | Qt.WindowType.WindowDoesNotAcceptFocus | Qt.WindowType.WindowStaysOnBottomHint})
        app.QQmlApplicationEngine = Engine
    with tempfile.TemporaryDirectory(prefix="youtube-music-visual-") as folder:
        root = Path(folder)
        art = QImage(160, 160, QImage.Format.Format_RGB32)
        art.fill(QColor("#d04060"))
        for x in range(80, 160):
            for y in range(160):
                art.setPixelColor(x, y, QColor("#4060d0"))
        art.save(str(root / "art.png"))
        if args.soak_seconds:
            from youtube_music_native.media import MediaFiles
            media = MediaFiles(root / "media")
            audio = media.root / "fixture.wav"
            with wave.open(str(audio), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(16000)
                handle.writeframes(b"\0\0" * 16000 * 60)
            media.publish("fixture0001", audio)
            media.close()

        def load(*values, **kwargs):
            engine = original(*values, **kwargs)
            window = engine.rootObjects()[0]
            shell, account, player, view, browse, downloads, search, library, theme_state = values[0], values[1], values[2], values[3], values[5], values[6], values[7], values[9], values[11]
            uri = (root / "art.png").as_uri()
            for section in shell._fixture["shelves"]:
                for track in section["items"]:
                    track.update(thumbnail=uri, videoId="fixture0001", duration=60)
            for entry in player.queue.entries:
                entry["track"].update(thumbnail=uri, videoId="fixture0001", duration=60)
            account._profile["avatar"] = uri
            account.changed.emit()
            if args.soak_seconds:
                from youtube_music_native.audio import Audio
                from youtube_music_native.jobs import Worker
                player._fixture = False
                player.worker = Worker(player, idle_ms=15000)
                player.worker.succeeded.connect(player._resolved)
                player.worker.failed.connect(player._failed)
                player.audio_factory = lambda **options: Audio(output="null", **options)
                player.save_timer.start()
                player.playTracks([entry["track"] for entry in player.queue.entries])
                player.setRepeat("all")
            player.queue.source_label = "Evening sessions"
            player.enqueue([dict(entry["track"]) for entry in player.queue.entries[1:3]])
            player.changed.emit()
            scenarios = [
                ("home", lambda: shell.navigate("Home")),
                ("explore", lambda: shell.navigate("Explore")),
                ("search", lambda: shell.search("fixture music")),
                ("library", lambda: shell.navigate("Library")),
                ("artists", lambda: library.select("Artists")),
                ("queueSidebar", lambda: (shell.navigate("Home"), shell.toggleQueue())),
                ("album", lambda: browse.open({"kind": "album", "id": "MPREfixture", "title": "Fixture album"})),
                ("playlist", lambda: browse.open({"kind": "playlist", "id": "PLfixture", "title": "Fixture playlist"})),
                ("artist", lambda: (browse.open({"kind": "artist", "id": "UCfixture", "title": "Fixture artist"}), view.patch({"hero": uri}))),
                ("queue", lambda: (shell.setLyricsOpen(False), shell.setQueueOpen(True), shell.setExpanded(True))),
                ("lyrics", lambda: (shell.setQueueOpen(False), shell.setLyricsOpen(True), shell.setExpanded(True))),
                ("downloads", lambda: shell.navigate("Downloads")),
            ]
            state = {"index": 0, "done": False, "started": time.monotonic(), "audio_position": 0., "rounded_artwork": 0, "queue_drag_checked": False}

            def finish(success):
                if state["done"]:
                    return
                state["done"] = True
                if success:
                    passed.append(True)
                if args.output_dir:
                    args.output_dir.mkdir(parents=True, exist_ok=True)
                    (args.output_dir / "report.json").write_text(json.dumps({"views": results, "passed": bool(passed), "soak_seconds": round(time.monotonic() - state["started"], 1), "renderer": str(window.rendererInterface().graphicsApi()), "rounded_artwork_checks": state["rounded_artwork"]}))
                window.close()
                QGuiApplication.instance().exit(0 if success else 1)

            def check():
                # Snapshot a completed scene; slow CI hosts can still be incubating delegates after 80 ms.
                incubation = engine.incubationController()
                deadline = time.monotonic() + 2
                while incubation and incubation.incubatingObjectCount() and time.monotonic() < deadline:
                    incubation.incubateFor(5)
                    QTest.qWait(10)
                assert not incubation or not incubation.incubatingObjectCount(), "View did not finish creating its visible delegates"
                assert not engine.property("qmlWarnings"), engine.property("qmlWarnings")
                player_bar = window.findChild(QObject, "playerBar")
                content = window.findChild(QObject, "pageContent")
                assert player_bar.x() == 12 and player_bar.width() == window.width() - 24
                assert player_bar.height() == 92 and player_bar.y() + 104 == window.height()
                like = window.findChild(QObject, "playerLike")
                dislike = window.findChild(QObject, "playerDislike")
                seek = window.findChild(QObject, "playbackSeek")
                elapsed = window.findChild(QObject, "playbackElapsed")
                duration = window.findChild(QObject, "playbackDuration")
                transport = window.findChild(QObject, "playerTransport")
                assert like and dislike and like.x() < dislike.x()
                assert elapsed and duration and seek and transport
                assert abs(elapsed.x() - seek.x() - seek.property("leftPadding")) < 0.1
                assert abs(duration.x() + duration.width() - seek.x() - seek.width() + seek.property("rightPadding")) < 0.1
                assert transport.y() + transport.height() <= seek.y()
                assert content.y() + content.height() + 12 == player_bar.y()
                for label in ("Home", "Explore", "Library", "Downloads"):
                    button = next(item for item in visual_items(window.contentItem()) if item.objectName() == "navigationButton-" + label)
                    background = button.findChild(QObject, "navigationBackground-" + label)
                    marker = button.findChild(QObject, "navigationMarker-" + label)
                    assert button and background and marker
                    assert background.mapToScene(QPointF()) == button.mapToScene(QPointF())
                    assert (background.width(), background.height()) == (button.width(), button.height())
                    assert marker.isVisible() == (not shell.expanded and shell.page == label)
                    if not button.isVisible():
                        assert shell.expanded
                        continue
                    assert marker.x() >= 0 and marker.x() + marker.width() <= background.width()
                    assert marker.y() + marker.height() / 2 == background.height() / 2
                    if button.property("selected"):
                        assert background.property("color").name().upper() == theme_state.selected
                image = window.grabWindow()
                assert not image.isNull()
                scale = image.width() / window.width()
                for item in visual_items(window.contentItem()):
                    if item.property("mediaKey") is not None and item.property("ready") and item.width() > 80 and fully_visible(item):
                        # Probe beyond 100 px as well as the center: SVG percentage masks can clip larger covers.
                        for fraction in (.2, .5, .8):
                            point = item.mapToScene(item.boundingRect().topLeft())
                            px, py = round((point.x() + item.width() * fraction) * scale), round((point.y() + item.height() / 2) * scale)
                            if 0 <= px < image.width() and 0 <= py < image.height():
                                pixel = image.pixelColor(px, py)
                                # Image.Ready can precede the first GPU mask/effect frame.
                                deadline = time.monotonic() + 2
                                while pixel.red() + pixel.blue() <= 240 and time.monotonic() < deadline:
                                    QTest.qWait(30)
                                    image = window.grabWindow()
                                    pixel = image.pixelColor(px, py)
                                assert pixel.red() + pixel.blue() > 240, (item.width(), fraction, pixel.name())
                    if args.native_gpu and item.property("mediaKey") is not None and item.property("ready") and item.width() > 80 and abs(item.property("radius") - item.width() / 2) < 1 and fully_visible(item):
                        position = item.mapToScene(item.boundingRect().topLeft())
                        x, y = round(position.x() * scale), round(position.y() * scale)
                        center = item.mapToScene(item.boundingRect().center())
                        cx, cy = round(center.x() * scale), round(center.y() * scale)
                        if 0 <= x < image.width() and 0 <= y < image.height() and 0 <= cx < image.width() and 0 <= cy < image.height():
                            corner, middle = image.pixelColor(x + 1, y + 1), image.pixelColor(cx, cy)
                            assert max(corner.red(), corner.blue()) < 160, (str(window.rendererInterface().graphicsApi()), corner.name(), x, y, item.width(), item.property("radius"))
                            assert middle.red() + middle.blue() > 240
                            state["rounded_artwork"] += 1
                    tip = item.property("tip")
                    if not tip or not item.isVisible() or not item.isEnabled():
                        continue
                    position = item.mapToScene(item.boundingRect().center())
                    x, y = round(position.x() * scale), round(position.y() * scale)
                    if not (14 * scale < x < image.width() - 14 * scale and 14 * scale < y < image.height() - 14 * scale):
                        continue
                    interface = QAccessible.queryAccessibleInterface(item)
                    assert interface and interface.text(QAccessible.Text.Name) == tip
                    # A rendered icon must survive layout and state changes in software too.
                    pixels = sum(max(image.pixelColor(px, py).red(), image.pixelColor(px, py).green(), image.pixelColor(px, py).blue()) > 80 for px in range(x - 10, x + 10) for py in range(y - 10, y + 10))
                    parent, transport = item.parentItem(), False
                    while parent:
                        transport = transport or parent.objectName() == "playerBar"
                        parent = parent.parentItem()
                    if transport:
                        if pixels <= 4:
                            # A source change may fall between grabWindow's frame and the property snapshot.
                            QTest.qWait(35)
                            image = window.grabWindow()
                            pixels = sum(max(image.pixelColor(px, py).red(), image.pixelColor(px, py).green(), image.pixelColor(px, py).blue()) > 80 for px in range(x - 10, x + 10) for py in range(y - 10, y + 10))
                        if pixels <= 4 and args.output_dir:
                            image.save(str(args.output_dir / "failed-control.png"))
                        assert pixels > 4, tip
                return image

            def initial():
                try:
                    if args.native_gpu and QGuiApplication.platformName() != "offscreen":
                        assert not window.isActive(), "The verification window must not take focus"
                    rail = window.findChild(QObject, "navigationRail")
                    profile = window.findChild(QObject, "profileButton")
                    account_dialog = window.findChild(QObject, "accountDialog")
                    account_menu = window.findChild(QObject, "accountMenu")
                    assert profile and account_dialog and account_menu
                    profile.clicked.emit()
                    QTest.qWait(30)
                    assert account_dialog.property("opened")
                    account_dialog.close()
                    account._connected = True
                    account.connectedChanged.emit()
                    profile.clicked.emit()
                    QTest.qWait(30)
                    assert account_menu.property("opened")
                    account_menu.close()
                    account._connected = False
                    account.connectedChanged.emit()
                    theme_dialog = window.findChild(QObject, "appearanceSettingsDialog")
                    assert theme_dialog
                    QMetaObject.invokeMethod(theme_dialog, "open")
                    QTest.qWait(60)
                    assert theme_dialog.property("opened")
                    if args.output_dir:
                        args.output_dir.mkdir(parents=True, exist_ok=True)
                        window.grabWindow().save(str(args.output_dir / "appearance-themes.png"))
                    dark_grid = window.findChild(QObject, "darkThemeGrid")
                    light_grid = window.findChild(QObject, "lightThemeGrid")
                    color_grid = window.findChild(QObject, "colorRoles")
                    add_theme = window.findChild(QObject, "addThemeButton")
                    home_backdrop = window.findChild(QObject, "homeBackdrop")
                    rename_button = window.findChild(QObject, "themeRenameButton")
                    delete_button = window.findChild(QObject, "themeDeleteButton")
                    export_button = window.findChild(QObject, "themeExportButton")
                    assert dark_grid and light_grid and color_grid and add_theme and home_backdrop
                    assert rename_button and delete_button and export_button
                    assert dark_grid.property("count") == 9
                    assert light_grid.property("count") == 3
                    assert color_grid.property("count") == 11
                    assert not rename_button.property("enabled")
                    assert not delete_button.property("enabled")
                    assert not export_button.property("enabled")
                    rename_hover = rename_button.findChild(QObject, "disabledActionHover")
                    assert rename_hover and "custom theme" in rename_button.property("disabledReason")
                    hover_point = rename_button.mapToScene(QPointF(rename_button.width() / 2, rename_button.height() / 2)).toPoint()
                    QTest.mouseMove(window, hover_point, delay=500)
                    QTest.qWait(500)
                    assert rename_hover.property("hovered")
                    for theme in theme_state.themes:
                        theme_state.selectTheme(theme["id"])
                        QTest.qWait(15)
                        assert window.property("color").name().upper() == theme["colors"]["background"]
                        assert home_backdrop.property("heroVisible")
                        assert home_backdrop.property("themeTint").name().upper() != theme["colors"]["background"]
                        assert home_backdrop.property("themeTint").name().upper() == theme_state.heroTint
                        sliders = [item for item in visual_items(window.contentItem()) if item.property("trackColor") is not None]
                        assert len(sliders) >= 2  # Seek and volume share the derived track token.
                        assert all(item.property("trackColor").name().upper() == theme_state.progressTrack for item in sliders)
                    theme_state.selectTheme("classic-dark")
                    for width, height in ((1280, 820), (920, 620)):
                        window.resize(width, height)
                        QTest.qWait(30)
                        assert theme_dialog.property("width") <= width - 48
                        assert theme_dialog.property("height") <= height - 48
                        if args.output_dir and width == 920:
                            window.grabWindow().save(str(args.output_dir / "appearance-themes-920x620.png"))
                    assert theme_state.createCustomTheme("Smoke Custom")
                    QTest.qWait(30)
                    assert rename_button.property("enabled")
                    assert delete_button.property("enabled")
                    assert export_button.property("enabled")
                    theme_dialog.setProperty("editingColors", True)
                    QTest.qWait(30)
                    assert color_grid.property("count") == 11
                    for width, height in ((1280, 820), (920, 620), (1280, 820)):
                        window.resize(width, height)
                        QTest.qWait(30)
                        assert theme_dialog.property("width") <= width - 48
                        assert theme_dialog.property("height") <= height - 48
                    theme_state.deleteCustomTheme(theme_state.activeThemeId)
                    theme_dialog.setProperty("editingColors", False)
                    QMetaObject.invokeMethod(theme_dialog, "close")
                    QTest.qWait(30)
                    for width in (1280, 920, 1280):
                        window.resize(width, 820)
                        QTest.qWait(30)
                        assert rail.width() == shell.sidebarWidth
                    assert window.findChild(QObject, "sidebarToggleButton") is None
                    resize_handle = window.findChild(QObject, "sidebarResizeHandle")
                    assert resize_handle and resize_handle.isVisible()
                    start = resize_handle.mapToScene(QPointF(resize_handle.width() / 2, 400)).toPoint()
                    initial_sidebar_width = rail.width()
                    QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=start)
                    for delta in (6, 12, 18, 24, 30, 36):
                        point = start + QPointF(delta, 0).toPoint()
                        QTest.mouseMove(window, point, delay=35)
                        QTest.qWait(15)
                        assert abs(rail.width() - initial_sidebar_width - delta) <= 1
                    QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=point)
                    QTest.qWait(40)
                    assert rail.width() == shell.sidebarWidth and shell.sidebarWidth >= 276
                    shell.toggleQueue()
                    QTest.qWait(60)
                    queue = window.findChild(QObject, "queueSidebar")
                    queue_handle = window.findChild(QObject, "queueResizeHandle")
                    assert queue and queue.isVisible() and queue_handle
                    start = queue_handle.mapToScene(QPointF(queue_handle.width() / 2, 400)).toPoint()
                    initial_queue_width = queue.width()
                    QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=start)
                    for delta in (-6, -12, -18, -24, -30, -36):
                        point = start + QPointF(delta, 0).toPoint()
                        QTest.mouseMove(window, point, delay=35)
                        QTest.qWait(15)
                        assert abs(queue.width() - initial_queue_width + delta) <= 1
                    QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=point)
                    QTest.qWait(40)
                    assert queue.width() > initial_queue_width
                    shell.setSidebarWidth(240)
                    shell.setQueueWidth(360)
                    shell.saveSidebarWidths()
                    shell.toggleQueue()
                    QTest.mouseMove(window, QPointF(800, 700).toPoint(), delay=20)
                    for size in ((1600, 900), (1280, 820), (920, 620)):
                        print(f"Checking visual matrix at {size[0]}×{size[1]}", flush=True)
                        window.resize(*size)
                        shell.navigate("Home")
                        QTest.qWait(30)
                        home = next(item for item in visual_items(window.contentItem()) if item.objectName() == "navigationButton-Home")
                        library_button = next(item for item in visual_items(window.contentItem()) if item.objectName() == "navigationButton-Library")
                        library_background = library_button.findChild(QObject, "navigationBackground-Library")
                        hover_point = library_button.mapToScene(library_button.boundingRect().center()).toPoint()
                        QTest.mouseMove(window, hover_point, delay=20)
                        QTest.qWait(20)
                        assert library_button.property("hovered") and not library_button.property("selected"), (size, hover_point, library_button.property("hovered"), library_button.property("selected"), shell.page)
                        assert home.property("selected") and view.route == "home"
                        assert library_background.property("color").name().upper() == theme_state.hover
                        # Immersive return may already have restored mouse focus to Library.
                        home.forceActiveFocus()
                        library_button.forceActiveFocus(Qt.FocusReason.TabFocusReason)
                        assert library_button.property("visualFocus")
                        assert QQmlProperty(library_background, "border.width").read() == 2
                        check()
                        QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=hover_point)
                        QTest.qWait(30)
                        assert shell.page == "Library" and view.route.startswith("library_")
                        assert library_button.property("selected") and not home.property("selected")
                        browse.open({"kind": "album", "id": "MPREfixture", "title": "Fixture album"})
                        QTest.qWait(80)
                        browse.back()
                        QTest.qWait(80)
                        assert shell.page == "Library" and view.route.startswith("library_")
                        assert library_button.property("selected")
                        QTest.mouseMove(window, QPointF(800, 500).toPoint(), delay=20)
                        for _ in range(12):
                            shell.navigate("Library")
                            shell.navigate("Home")
                        QTest.qWait(80)
                        assert window.findChild(QObject, "browsePane")
                        assert not engine.property("qmlWarnings"), engine.property("qmlWarnings")
                        for name, action in scenarios:
                            action()
                            QTest.qWait(80)
                            image = check()
                            if name in {"album", "playlist"}:
                                collection = window.findChild(QObject, "collectionPane")
                                rows = [item for item in visual_items(window.contentItem()) if item.property("tableLayout")]
                                assert rows
                                assert all(row.x() == collection.property("margin") for row in rows)
                                assert all(row.property("showAlbum") == (name == "playlist" and not collection.property("compact")) for row in rows)
                            if name == "artist":
                                hero = window.findChild(QObject, "artistHero")
                                assert hero.isVisible()
                                point = hero.mapToScene(hero.boundingRect().topLeft())
                                scale = image.width() / window.width()
                                px, py = round((point.x() + hero.width() / 2) * scale), round((point.y() + 30) * scale)
                                pixel = image.pixelColor(px, py)
                                deadline = time.monotonic() + 3
                                while max(pixel.red(), pixel.blue()) <= 40 and time.monotonic() < deadline:
                                    QTest.qWait(30)
                                    image = window.grabWindow()
                                    pixel = image.pixelColor(px, py)
                                assert max(pixel.red(), pixel.blue()) > 40, pixel.name()
                            if name == "queueSidebar":
                                check_queue(window, shell, player, browse, downloads, args.output_dir, not state["queue_drag_checked"])
                                state["queue_drag_checked"] = True
                                image = check()
                            if args.output_dir:
                                args.output_dir.mkdir(parents=True, exist_ok=True)
                                assert image.save(str(args.output_dir / (name + "-" + str(size[0]) + ".png")))
                            results.append({"view": name, "width": size[0], "height": size[1]})
                            if name == "queueSidebar":
                                shell.toggleQueue()
                                QTest.qWait(80)
                    if args.native_gpu:
                        assert state["rounded_artwork"] > 0
                    browse.open({"kind": "artist", "id": "UCfixture"})
                    QTest.qWait(80)
                    for name in ("artistShuffle", "artistMix", "artistSubscribe"):
                        button = window.findChild(QObject, name)
                        button.forceActiveFocus(Qt.FocusReason.TabFocusReason)
                        QTest.qWait(20)
                        assert button.property("visualFocus")
                        assert QQmlProperty(button.property("background"), "border.width").read() == 2
                    browse.open({"kind": "playlist", "id": "PLfixture"})
                    view.patch({"subtitle": "First line\nSecond line\nThird line"})
                    QTest.qWait(80)
                    toggle = window.findChild(QObject, "descriptionToggle")
                    assert toggle.isVisible()
                    toggle.clicked.emit()
                    QTest.qWait(30)
                    assert toggle.isVisible() and toggle.property("text") == "Less"
                    assert not window.findChild(QObject, "collectionDescription").property("truncated")
                    downloads._initialized = False
                    downloads.changed.emit()
                    view.patch({"thumbnail": "file:///unavailable-synthetic-art.png"})
                    QTest.qWait(30)
                    backdrop = window.findChild(QObject, "backdropImage")
                    assert backdrop.property("source").isEmpty()
                    downloads._artwork["playlist:PLfixture"] = uri
                    downloads._initialized = True
                    downloads.changed.emit()
                    QTest.qWait(80)
                    assert backdrop.property("source").toString() == uri
                    view._error = "The provider is unavailable. Downloaded music remains available. " * 3
                    view.changed.emit()
                    QTest.qWait(80)
                    check()
                    account.requireReconnect("Reconnect to browse online music.")
                    QTest.qWait(80)
                    check()
                    account._reconnect = False
                    account.changed.emit()
                    shell.navigate("Library")
                    library.select("Songs")
                    tracks = [{"kind": "song", "videoId": "fixture0001", "title": "Long list fixture " + str(index), "thumbnail": uri} for index in range(10000)]
                    view.showLocal("library_songs", {"items": tracks, "cursor": None})
                    QTest.qWait(120)
                    listing = window.findChild(QObject, "librarySongs")
                    assert listing.property("count") == 10000
                    listing.setProperty("contentY", listing.property("contentHeight") - listing.property("height"))
                    QTest.qWait(100)
                    count = sum(item.metaObject().className().startswith("SongRow_") for item in visual_items(window.contentItem()))
                    assert 0 < count < 60, count
                    check()
                    if args.soak_seconds:
                        timer.start()
                    else:
                        finish(True)
                except Exception:
                    if args.output_dir:
                        args.output_dir.mkdir(parents=True, exist_ok=True)
                        window.grabWindow().save(str(args.output_dir / "failed-view.png"))
                    traceback.print_exc()
                    finish(False)

            def tick():
                try:
                    name, action = scenarios[state["index"] % len(scenarios)]
                    action()
                    QTest.qWait(50)
                    check()
                    state["index"] += 1
                    state["audio_position"] = max(state["audio_position"], player.position)
                    if time.monotonic() - state["started"] >= args.soak_seconds:
                        assert player.sourceKind == "local" and state["audio_position"] > 2
                        timer.stop()
                        finish(True)
                except Exception:
                    traceback.print_exc()
                    timer.stop()
                    finish(False)
            timer = QTimer(shell)
            timer.setInterval(1000)
            timer.timeout.connect(tick)
            QTimer.singleShot(250, initial)
            QTimer.singleShot(max(60000, (args.soak_seconds + 60) * 1000), lambda: finish(False))
            return engine

        app.load_window = load
        result = app.main(["--fixture", "--data-dir", str(root)])
        app.load_window = original
        assert result == 0 and passed
    print("All views at three sizes, accessible controls and a 10,000-song list passed.")


if __name__ == "__main__":
    main()
