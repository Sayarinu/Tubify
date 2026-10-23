from PySide6.QtCore import QCoreApplication, QEvent, QObject, Signal

from youtube_music_native.lifecycle import Lifecycle
from youtube_music_native.startup import StartupError
from test_playback_options import player_at, track


class Window(QObject):
    visibleChanged = Signal(bool)

    def __init__(self):
        super().__init__()
        self.visible, self.minimized = False, False

    def isVisible(self):
        return self.visible

    def show(self):
        self.visible = True
        self.visibleChanged.emit(True)

    def showMinimized(self):
        self.show()
        self.minimized = True

    def hide(self):
        self.visible = False
        self.visibleChanged.emit(False)


class Tray(QObject):
    changed = Signal()
    active, messages_supported = False, True

    def __init__(self, window):
        super().__init__()
        self.window, self.messages = window, []
        self.tray_factory = self.tray = self

    def showMain(self):
        self.window.minimized = False
        self.window.show()

    def supportsMessages(self):
        return self.messages_supported

    def showMessage(self, *args):
        self.messages.append(args)


class Startup:
    supported, disabled_reason, enabled, fail = True, "", False, False

    def is_enabled(self):
        return self.enabled

    def set_enabled(self, enabled):
        if self.fail:
            raise StartupError("Synthetic registration error")
        self.enabled = enabled


def service(tmp_path):
    player = player_at(tmp_path)
    window = Window()
    tray, startup = Tray(window), Startup()
    lifecycle = Lifecycle(tmp_path / "settings.ini", player, tray, startup=startup)
    lifecycle.start(window)
    return lifecycle, player, tray, window, startup


def test_defaults_are_visible_idle_and_normal_close(tmp_path):
    life, player, tray, window, _ = service(tmp_path)
    assert window.visible and not window.minimized
    assert not any((life.autostart, life.startMinimized, life.closeToTray, life.trackNotifications))
    assert not life.hidden_watch.isActive() and not life.status_timer.isActive()
    assert not life.hideOnClose()
    player.playTracks([track("a"), track("b")])
    player.next()
    assert not tray.messages
    life.close()
    player.close()


def test_preferences_persist_and_start_minimized_stays_reachable(tmp_path):
    life, player, tray, window, _ = service(tmp_path)
    life.setStartMinimized(True)
    life.setCloseToTray(True)
    life.setTrackNotifications(True)
    assert window.visible and not window.minimized
    life.close()
    restored = Lifecycle(tmp_path / "settings.ini", player, tray, startup=Startup())
    restored.start(window)
    assert restored.startMinimized and restored.closeToTray and restored.trackNotifications
    assert window.visible and window.minimized
    assert not restored.hideOnClose()  # No available tray: closing exits.
    restored.close()
    player.close()


def test_hidden_window_restores_when_tray_is_disabled_or_lost(tmp_path):
    life, player, tray, window, _ = service(tmp_path)
    life.setCloseToTray(True)
    tray.active = True
    assert life.hideOnClose() and not window.visible and life.hidden_watch.isActive()
    tray.active = False
    tray.changed.emit()
    assert window.visible and not life.hidden_watch.isActive() and "restored" in life.error
    tray.active = True
    tray.changed.emit()
    assert not life.error
    assert life.hideOnClose()
    life.setCloseToTray(False)
    assert window.visible and not life.hidden_watch.isActive()
    life.setCloseToTray(True)
    assert life.hideOnClose()
    tray.active = False
    life._check_hidden()  # Periodic capability check covers tray host disappearance.
    assert window.visible
    life.close()
    player.close()


def test_quit_bypasses_close_to_tray(tmp_path):
    life, player, tray, window, _ = service(tmp_path)
    life.setCloseToTray(True)
    tray.active = True
    assert not life.eventFilter(QCoreApplication.instance(), QEvent(QEvent.Type.Quit))
    assert not life.hideOnClose() and window.visible
    life.close()
    player.close()


def test_autostart_failure_retains_setting_and_can_retry(tmp_path):
    life, player, _, _, startup = service(tmp_path)
    startup.fail = True
    life.setAutostart(True)
    assert not life.autostart and life.startupError and "Synthetic" in life.error
    assert not life.status and not life.status_timer.isActive()
    startup.fail = False
    life.retryAutostart()
    assert life.autostart and startup.enabled and not life.error and life.status
    life._clear_status()
    assert not life.status
    startup.fail = True
    life.setAutostart(False)
    assert life.autostart and life.startupError
    startup.fail = False
    life.retryAutostart()
    assert not life.autostart and not startup.enabled and not life.error
    life.close()
    player.close()


def test_stale_login_registration_is_reported_without_rewriting(tmp_path):
    life, player, tray, window, startup = service(tmp_path)
    life.setAutostart(True)
    life.close()
    startup.enabled = False
    restored = Lifecycle(tmp_path / "settings.ini", player, tray, startup=startup)
    restored.start(window)
    assert restored.autostart and restored.startupError and not startup.enabled
    restored.retryAutostart()
    assert startup.enabled and not restored.error
    restored.close()
    player.close()


def test_notifications_are_opt_in_deduplicated_and_only_for_playing_transitions(tmp_path):
    life, player, tray, _, _ = service(tmp_path)
    tray.active = True
    life.setTrackNotifications(True)
    player.playTracks([track("a"), {**track("b"), "artists": [{"name": "Synthetic artist"}]}])
    assert len(tray.messages) == 1
    player.changed.emit()
    player.pause()
    player.togglePlayback()
    assert len(tray.messages) == 1
    player.next()
    assert len(tray.messages) == 2 and tray.messages[-1][:2] == ("b", "Synthetic artist")
    tray.messages_supported = False
    player.playTracks([track("c")])
    assert len(tray.messages) == 2 and "not support" in life.capability
    life.setTrackNotifications(False)
    tray.messages_supported = True
    player.playTracks([track("d")])
    assert len(tray.messages) == 2
    life.close()
    player.close()
