from PySide6.QtCore import QCoreApplication

from youtube_music_native.shell import ShellController


def test_preferences_survive_restart_and_invalid_geometry_is_bounded(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    controller = ShellController(tmp_path / "settings.ini")
    assert controller.sidebarExpanded is False
    controller.toggleSidebar()
    controller.setSidebarWidth(310)
    controller.setQueueWidth(430)
    controller.setVolume(800)
    controller.saveWindow(100, 99999)
    restored = ShellController(tmp_path / "settings.ini")
    assert restored.sidebarExpanded is True
    assert restored.sidebarWidth == 310
    assert restored.queueWidth == 430
    assert restored.volume == 100
    assert restored.initialWidth == 920
    assert restored.initialHeight == 4320


def test_search_trims_input_and_unknown_navigation_cannot_change_route(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    controller = ShellController(tmp_path / "settings.ini")
    requested = []
    controller.searchRequested.connect(requested.append)
    controller.navigate("unrecognized")
    assert controller.page == "Home"
    controller.search("  a song  ")
    assert controller.page == "Search"
    assert controller.query == "a song"
    assert requested == ["a song"]
    controller.search("   ")
    assert requested == ["a song"]


def test_mute_restores_previous_volume_across_restart(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    controller = ShellController(tmp_path / "settings.ini")
    controller.setVolume(32)
    controller.toggleMute()
    controller.saveWindow(1280, 820)
    restored = ShellController(tmp_path / "settings.ini")
    assert restored.volume == 0
    restored.toggleMute()
    assert restored.volume == 32


def test_malformed_preferences_do_not_prevent_startup(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    path = tmp_path / "settings.ini"
    path.write_text("[General]\nwidth=invalid\nheight=invalid\nvolume=invalid\nsidebarWidth=invalid\nqueueWidth=invalid\n")
    controller = ShellController(path)
    assert controller.initialWidth == 1280
    assert controller.initialHeight == 820
    assert controller.volume == 70
    assert controller.sidebarWidth == 240
    assert controller.queueWidth == 360


def test_sidebar_widths_are_bounded(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    controller = ShellController(tmp_path / "settings.ini")
    controller.setSidebarWidth(900)
    controller.setQueueWidth(100)
    assert controller.sidebarWidth == 420
    assert controller.queueWidth == 280


def test_independent_docks_remember_intent_width_and_last_opened(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    path = tmp_path / "settings.ini"
    shell = ShellController(path)
    assert not shell.lyricsOpen and not shell.queueOpen
    shell.toggleLyrics()
    assert shell.lyricsOpen and not shell.queueOpen and shell.activeDock == "Lyrics"
    shell.toggleQueue()
    assert shell.lyricsOpen and shell.queueOpen and shell.activeDock == "Queue"
    shell.setActiveDock("Lyrics")
    shell.setLyricsWidth(412)
    shell.setQueueWidth(468)
    shell.saveSidebarWidths()
    restored = ShellController(path)
    assert restored.lyricsOpen and restored.queueOpen and restored.activeDock == "Lyrics"
    assert (restored.lyricsWidth, restored.queueWidth) == (412, 468)
    restored.setLyricsOpen(False)
    assert restored.queueOpen and restored.activeDock == "Queue"
    restored.setActiveDock("Lyrics")
    assert restored.activeDock == "Queue"
    restored.setQueueOpen(False)
    assert not restored.lyricsOpen and not restored.queueOpen


def test_invalid_dock_preferences_use_safe_defaults(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    path = tmp_path / "settings.ini"
    path.write_text("[General]\nlyricsOpen=true\nqueueOpen=false\nactiveDock=invalid\nlyricsWidth=invalid\n")
    shell = ShellController(path)
    assert shell.activeDock == "Lyrics" and shell.lyricsWidth == 360
    shell.setLyricsWidth(999)
    assert shell.lyricsWidth == 520
    shell.setLyricsWidth(1)
    assert shell.lyricsWidth == 280


def test_immersive_transition_can_snapshot_browsing_before_geometry_changes(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    shell = ShellController(tmp_path / "settings.ini")
    events = []
    shell.playerViewChanging.connect(lambda entering: events.append(("before", entering, shell.expanded)))
    shell.playerViewChanged.connect(lambda: events.append(("after", shell.expanded)))
    shell.setExpanded(True)
    shell.setExpanded(True)
    shell.setExpanded(False)
    assert events == [("before", True, False), ("after", True), ("before", False, True), ("after", False)]

def test_appearance_preferences_are_independent_bounded_and_persisted(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    path = tmp_path / "settings.ini"
    shell = ShellController(path)
    assert (shell.uiScale, shell.uiScaleFactor, shell.reducedMotion, shell.artworkBackground, shell.artworkBlur) == (100, 1, False, True, True)
    shell.setUiScale(138)
    assert shell.uiScale == 140
    shell.setUiScale(999)
    assert shell.uiScale == 150
    shell.setUiScale(1)
    assert shell.uiScale == 80
    shell.setReducedMotion(True)
    shell.setArtworkBackground(False)
    shell.setArtworkBlur(False)
    shell.setSidebarWidth(300)
    shell.saveSidebarWidths()
    restored = ShellController(path)
    assert (restored.uiScale, restored.uiScaleFactor, restored.reducedMotion, restored.artworkBackground, restored.artworkBlur) == (80, 0.8, True, False, False)
    assert restored.sidebarWidth == 300
    restored.setUiScale(100)
    assert restored.sidebarWidth == 300
    path.write_text("[General]\nuiScale=invalid\n")
    assert ShellController(path).uiScale == 100
    path.write_text("[General]\nuiScale=" + "9" * 400 + "\n")
    assert ShellController(path).uiScale == 150


def test_window_geometry_stays_on_connected_display(tmp_path):
    from PySide6.QtCore import QRect
    from youtube_music_native.shell import fit_window_geometry

    left = QRect(-1920, 0, 1920, 1040)
    main = QRect(0, 40, 1920, 1040)
    saved = QRect(-1800, 100, 1280, 820)
    assert fit_window_geometry(saved, [left, main]) == saved
    assert fit_window_geometry(saved, [main]) == QRect(0, 100, 1280, 820)
    assert fit_window_geometry(QRect(4000, 1800, 9000, 5000), [main]) == main
    assert fit_window_geometry(QRect(-800, -500, 1280, 820), [left, main]) == QRect(-1280, 0, 1280, 820)
    assert fit_window_geometry(saved, []) == saved
    shell = ShellController(tmp_path / "settings.ini")
    shell.saveWindowGeometry(-1800, 100, 1280, 820)
    restored = ShellController(tmp_path / "settings.ini")
    assert restored.settings.value("windowX", type=int) == -1800
    assert restored.settings.value("windowY", type=int) == 100
