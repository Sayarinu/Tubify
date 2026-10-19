from PySide6.QtCore import QCoreApplication

from youtube_music_native.shell import ShellController


def test_preferences_survive_restart_and_invalid_geometry_is_bounded(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    controller = ShellController(tmp_path / "settings.ini")
    assert controller.sidebarExpanded is False
    controller.toggleSidebar()
    controller.setVolume(800)
    controller.saveWindow(100, 99999)
    restored = ShellController(tmp_path / "settings.ini")
    assert restored.sidebarExpanded is True
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
    path.write_text("[General]\nwidth=invalid\nheight=invalid\nvolume=invalid\n")
    controller = ShellController(path)
    assert controller.initialWidth == 1280
    assert controller.initialHeight == 820
    assert controller.volume == 70
