"""Render every view, check accessible controls and stress virtualized lists."""

import argparse
import json
from pathlib import Path
import tempfile
import time
import traceback
import wave

from PySide6.QtCore import QObject, QPointF, QTimer, Qt
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
                ("queue", lambda: (shell.setPlayerTab("Up next"), shell.setExpanded(True))),
                ("lyrics", lambda: (shell.setPlayerTab("Lyrics"), shell.setExpanded(True))),
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
                    assert marker.isVisible() == (shell.page == label)
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
                    theme_dialog.setProperty("visible", True)
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
                    theme_dialog.setProperty("visible", False)
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
                                queue_pane = window.findChild(QObject, "queuePane")
                                queue_list = window.findChild(QObject, "pinnedQueueList")
                                next_list = window.findChild(QObject, "pinnedQueueNextList")
                                queue_history = window.findChild(QObject, "queueHistoryList")
                                assert queue_pane and queue_list and next_list and queue_history
                                assert queue_list.property("count") == player.manualCount
                                assert next_list.property("count") == sum(entry["group"] not in {"Now playing", "Previously played", "Next in queue"} for entry in player.entries)
                                assert queue_history.property("count") == sum(entry["group"] == "Previously played" for entry in player.entries)
                                sidebar = window.findChild(QObject, "queueSidebar")
                                content = window.findChild(QObject, "pageContent")
                                header = window.findChild(QObject, "mainHeader")
                                profile = window.findChild(QObject, "profileButton")
                                clear_queue = window.findChild(QObject, "queueClearButton")
                                browse_pane = window.findChild(QObject, "browsePane")
                                sections = window.findChild(QObject, "browseSections")
                                scrollbar = window.findChild(QObject, "browseSectionsScrollbar")
                                queue_scrollbar = window.findChild(QObject, "queueSidebarScrollbar")
                                assert sidebar and sidebar.isVisible()
                                assert sidebar.y() == 0
                                assert header and profile and profile.x() + profile.width() <= sidebar.x()
                                assert content.width() < window.width() - sidebar.width()
                                assert clear_queue and clear_queue.isVisible() == (player.manualCount > 0)
                                assert browse_pane and sections and scrollbar
                                bar_x = scrollbar.mapToScene(QPointF(0, 0)).x()
                                list_right = sections.mapToScene(QPointF(0, 0)).x() + sections.width()
                                queue_left = sidebar.mapToScene(QPointF(0, 0)).x()
                                assert bar_x >= list_right - 1 and bar_x + scrollbar.width() <= queue_left
                                queue_bar_x = queue_scrollbar.mapToScene(QPointF(0, 0)).x()
                                queue_list_right = queue_list.mapToScene(QPointF(0, 0)).x() + queue_list.width()
                                queue_panel_right = sidebar.mapToScene(QPointF(0, 0)).x() + sidebar.width()
                                assert queue_bar_x >= queue_list_right - 1 and queue_bar_x + queue_scrollbar.width() <= queue_panel_right, (queue_bar_x, queue_scrollbar.width(), queue_list_right, queue_panel_right)
                                assert window.findChild(QObject, "expandedPlayer") is None
                                if not state["queue_drag_checked"]:
                                    def drag_first_in_group(group, from_handle=True):
                                        entries = [entry for entry in player.entries if entry["group"] == group and entry["movable"]]
                                        assert len(entries) >= 2, group
                                        if group.startswith("Next from "):
                                            queue_rows = [entry for entry in player.entries if entry["group"] not in {"Now playing", "Previously played", "Next in queue"}]
                                            next_list.positionViewAtIndex(next(i for i, entry in enumerate(queue_rows) if entry["group"] == group), 0)
                                            QTest.qWait(50)
                                        moving, following = entries[0]["key"], entries[1]["key"]
                                        row = next(item for item in visual_items(window.contentItem()) if item.objectName() == "queueSidebarSong-" + moving)
                                        row_highlight = next(item for item in visual_items(window.contentItem()) if item.objectName() == "queueSidebarRowHighlight-" + moving)
                                        handle = next(item for item in visual_items(window.contentItem()) if item.objectName() == "queueSidebarDrag-" + moving)
                                        more_button = next(item for item in visual_items(row) if item.objectName().startswith("queueRowMore-"))
                                        hover_point = handle.mapToScene(handle.boundingRect().center()).toPoint()
                                        QTest.mouseMove(window, hover_point, delay=30)
                                        QTest.qWait(30)
                                        assert row.parentItem().property("rowHovered")
                                        assert row_highlight and row_highlight.width() == row.parentItem().width()
                                        assert QQmlProperty(row_highlight, "border.width").read() == 1
                                        more_point = more_button.mapToScene(more_button.boundingRect().center()).toPoint()
                                        QTest.mouseMove(window, more_point, delay=30)
                                        QTest.qWait(30)
                                        assert row.parentItem().property("rowHovered")
                                        more_color = QQmlProperty(more_button.property("background"), "color").read()
                                        assert more_color.alpha() == 0
                                        source = next(item for item in visual_items(window.contentItem()) if item.objectName() == "queueSidebarDrag-" + moving) if from_handle else row
                                        local_start = QPointF(source.width() / 2, source.height() / 2) if from_handle else QPointF(min(60, source.width() - 120), source.height() / 2)
                                        start = source.mapToScene(local_start).toPoint()
                                        end = start + QPointF(0, 64).toPoint()
                                        QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=start)
                                        QTest.mouseMove(window, start + QPointF(0, 20).toPoint(), delay=30)
                                        QTest.mouseMove(window, end, delay=30)
                                        QTest.qWait(50)
                                        preview = window.findChild(QObject, "queueDragPreview")
                                        indicators = [item for item in visual_items(window.contentItem()) if item.objectName().startswith("queueSidebarDrop")]
                                        assert preview and preview.isVisible()
                                        preview_point = preview.mapToScene(preview.boundingRect().topLeft())
                                        assert 0 <= preview_point.x() and preview_point.x() + preview.width() <= window.width()
                                        assert 0 <= preview_point.y() and preview_point.y() + preview.height() <= window.height()
                                        if from_handle:
                                            assert preview_point.x() < end.x()
                                        assert any(item.isVisible() for item in indicators), (queue_pane.property("dropIndex"), queue_pane.property("dropKey"), queue_pane.property("dropToManual"), end)
                                        QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=end)
                                        QTest.qWait(50)
                                        reordered = [entry["key"] for entry in player.entries if entry["group"] == group]
                                        assert reordered.index(following) < reordered.index(moving), group

                                    drag_first_in_group("Next in queue")
                                    source_group = next(entry["group"] for entry in player.entries if entry["group"].startswith("Next from "))
                                    drag_first_in_group(source_group, from_handle=False)

                                    def drag_source_into_queue(drop_on_header):
                                        source = next(entry for entry in player.entries if entry["group"] == source_group)
                                        source_index = next(index for index, entry in enumerate(entry for entry in player.entries if entry["group"] not in {"Now playing", "Previously played", "Next in queue"}) if entry["key"] == source["key"])
                                        next_list.positionViewAtIndex(source_index, 0)
                                        QTest.qWait(50)
                                        source_row = next(item for item in visual_items(window.contentItem()) if item.objectName() == "queueSidebarSong-" + source["key"])
                                        start = source_row.mapToScene(QPointF(min(60, source_row.width() - 120), source_row.height() / 2)).toPoint()
                                        target = next(entry for entry in player.entries if entry["group"] == "Next in queue")
                                        target_row = next(item for item in visual_items(window.contentItem()) if item.objectName() == "queueSidebarSong-" + target["key"])
                                        end = target_row.mapToScene(QPointF(target_row.width() / 2, 2)).toPoint()
                                        QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=start)
                                        QTest.mouseMove(window, start + QPointF(0, 20).toPoint(), delay=30)
                                        QTest.mouseMove(window, end, delay=40)
                                        QTest.qWait(50)
                                        assert queue_pane.property("dropTargetList") == "queue", (end, queue_pane.property("draggingKey"), queue_pane.property("dropIndex"), queue_pane.property("dropKey"))
                                        preview = window.findChild(QObject, "queueDragPreview")
                                        preview_point = preview.mapToScene(preview.boundingRect().topLeft())
                                        assert 0 <= preview_point.x() and preview_point.x() + preview.width() <= window.width()
                                        QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=end)
                                        QTest.qWait(50)
                                        current = next(entry for entry in player.entries if entry["key"] == source["key"])
                                        assert current["group"] == "Next in queue", (player.manualCount, current["group"])
                                        if drop_on_header:
                                            assert player.entries.index(current) == next(i for i, entry in enumerate(player.entries) if entry["group"] == "Next in queue")

                                    drag_source_into_queue(False)
                                    drag_source_into_queue(True)
                                    player.clearManualQueue()
                                    source = next(entry for entry in player.entries if entry["group"] == source_group)
                                    source_row = next(item for item in visual_items(window.contentItem()) if item.objectName() == "queueSidebarSong-" + source["key"])
                                    section = window.findChild(QObject, "queueSidebarAddToQueueDrop")
                                    start = source_row.mapToScene(QPointF(min(60, source_row.width() - 120), source_row.height() / 2)).toPoint()
                                    end = section.mapToScene(section.boundingRect().center()).toPoint()
                                    QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=start)
                                    QTest.mouseMove(window, end, delay=40)
                                    QTest.qWait(50)
                                    QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=end)
                                    QTest.qWait(50)
                                    assert player.manualCount == 1
                                    assert next(entry for entry in player.entries if entry["key"] == source["key"])["group"] == "Next in queue"
                                    state["queue_drag_checked"] = True
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
