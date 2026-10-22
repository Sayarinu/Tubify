from PySide6.QtCore import QCoreApplication, QObject, QRect, Signal
from PySide6.QtWidgets import QSystemTrayIcon

from youtube_music_native.tray import TrayPlayer, clamped_position
from test_playback_options import player_at
from youtube_music_native.shell import ShellController


class FakeTray(QObject):
    activated = Signal(object)
    supported = True
    created = 0

    @classmethod
    def isSystemTrayAvailable(cls):
        return cls.supported

    def __init__(self, parent):
        super().__init__(parent)
        type(self).created += 1
        self.visible = False

    def setIcon(self, icon):
        pass

    def setToolTip(self, text):
        pass

    def setContextMenu(self, menu):
        self.menu = menu

    def setVisible(self, value):
        self.visible = value

    def isVisible(self):
        return self.visible

    def hide(self):
        self.visible = False


class FakeMenu:
    def __init__(self):
        self.actions = {}

    def addAction(self, title, callback):
        self.actions[title] = callback

    def addSeparator(self):
        pass

    def deleteLater(self):
        pass


class FakeWindow:
    def __init__(self):
        self.shown = 0

    def showNormal(self):
        self.shown += 1

    def raise_(self):
        pass

    def requestActivate(self):
        pass


def service(tmp_path):
    player = player_at(tmp_path)
    shell = ShellController(tmp_path / "settings.ini")
    return TrayPlayer(shell, player, tmp_path / "settings.ini", "", tray_factory=FakeTray, menu_factory=FakeMenu), player


def test_disabled_tray_creates_no_resources_and_commands_share_player(tmp_path):
    FakeTray.created, FakeTray.supported = 0, True
    tray, player = service(tmp_path)
    window = FakeWindow()
    tray.start(window)
    assert not tray.enabled and not tray.active and FakeTray.created == 0
    tray.setEnabled(True)
    assert tray.active and FakeTray.created == 1
    tray.menu.actions["Play / Pause"]()
    assert not player.playing
    tray._activated(QSystemTrayIcon.ActivationReason.MiddleClick)
    assert player.playing
    tray.menu.actions["Open YouTube Music"]()
    assert window.shown == 1
    tray.setPinned(True)
    tray.setQueueOpen(True)
    tray.setEnabled(False)
    assert not tray.active and not tray.tray.isVisible()
    tray.close()
    player.close()


def test_unavailable_or_lost_tray_never_hides_main_window(tmp_path):
    FakeTray.supported = False
    tray, player = service(tmp_path)
    window = FakeWindow()
    tray.start(window)
    tray.setEnabled(True)
    assert not tray.enabled and not tray.active and "unavailable" in tray.error
    tray.showPlayer()
    assert window.shown == 1
    FakeTray.supported = True
    tray.setEnabled(True)
    assert tray.active and not tray.error
    FakeTray.supported = False
    tray.showPlayer()
    assert window.shown == 2 and not tray.active
    tray.close()
    player.close()
    FakeTray.supported = True


def test_popup_position_clamps_to_connected_work_areas():
    screens = [QRect(-1920, 0, 1920, 1080), QRect(0, 0, 1920, 1040)]
    assert clamped_position(5000, 4000, 360, 700, screens) == (1560, 340)
    assert clamped_position(-3000, -400, 360, 700, screens) == (-1920, 0)
    assert clamped_position(-1200, 200, 360, 700, screens) == (-1200, 200)
