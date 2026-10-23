"""Optional Qt system tray adapter; transport remains owned by Playback."""

from PySide6.QtCore import QObject, Property, QSettings, Signal, Slot
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon


def clamped_position(x, y, width, height, screens):
    """Choose the nearest connected work area, including negative monitor coordinates."""
    if not screens:
        return x, y
    def distance(rect):
        return max(rect.left() - x, 0, x - rect.right()) ** 2 + max(rect.top() - y, 0, y - rect.bottom()) ** 2
    area = min(screens, key=distance)
    return max(area.left(), min(x, area.right() + 1 - width)), max(area.top(), min(y, area.bottom() + 1 - height))


class TrayPlayer(QObject):
    changed = Signal()

    def __init__(self, shell, player, path, icon_path, parent=None, tray_factory=QSystemTrayIcon, menu_factory=QMenu):
        super().__init__(parent)
        self.shell, self.player = shell, player
        self.settings = QSettings(str(path), QSettings.Format.IniFormat)
        self.icon_path, self.tray_factory, self.menu_factory = str(icon_path), tray_factory, menu_factory
        self.window, self.popup, self.tray, self.menu = None, None, None, None
        self._enabled, self._error = False, ""
        self._pinned = self.settings.value("trayPinned", False, type=bool)
        self._queue = self.settings.value("trayQueue", False, type=bool)
        self._closed = False
        self._requested = self.settings.value("trayEnabled", False, type=bool)

    def start(self, window):
        self.window = window
        if self._requested:
            self.setEnabled(True)

    @Property(bool, notify=changed)
    def enabled(self):
        return self._enabled

    @Property(bool, notify=changed)
    def available(self):
        return bool(self.tray_factory.isSystemTrayAvailable())

    @Property(bool, notify=changed)
    def active(self):
        return bool(self._enabled and self.tray and self.tray.isVisible() and self.available)

    @Property(bool, notify=changed)
    def popupActive(self):
        return bool(self.popup and self.popup.isActive())

    @Property(str, notify=changed)
    def error(self):
        return self._error

    @Property(bool, notify=changed)
    def pinned(self):
        return self._pinned

    @Property(bool, notify=changed)
    def queueOpen(self):
        return self._queue

    @Slot(bool)
    def setEnabled(self, value):
        if self._closed:
            return
        value = bool(value)
        if value and not self.available:
            self._error = "The system tray is unavailable. Enable a desktop tray and try again."
            self.changed.emit()
            return
        self._error = ""
        if value and not self.tray:
            self.tray = self.tray_factory(self)
            self.tray.setIcon(QIcon(self.icon_path))
            self.tray.setToolTip("Tubify")
            self.menu = self.menu_factory()
            for title, callback in (("Open tray player", self.showPlayer), ("Open Tubify", self.showMain),
                                    ("Play / Pause", self.player.togglePlayback), ("Previous", self.player.previous), ("Next", self.player.next)):
                self.menu.addAction(title, callback)
            self.menu.addSeparator()
            self.menu.addAction("Quit", lambda: QGuiApplication.instance().quit())
            self.tray.setContextMenu(self.menu)
            self.tray.activated.connect(self._activated)
        self._enabled = value
        if self.tray:
            self.tray.setVisible(value)
        if not value and self.popup:
            self.popup.hide()
        self.settings.setValue("trayEnabled", value)
        self.settings.sync()
        self.changed.emit()

    def _activated(self, reason):
        if reason in {QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick}:
            self.showPlayer()
        elif reason == QSystemTrayIcon.ActivationReason.MiddleClick:
            self.player.togglePlayback()

    @Slot(bool)
    def setPinned(self, value):
        self._pinned = bool(value)
        self.settings.setValue("trayPinned", self._pinned)
        self.settings.sync()
        self.changed.emit()

    @Slot(bool)
    def setQueueOpen(self, value):
        self._queue = bool(value)
        self.settings.setValue("trayQueue", self._queue)
        self.settings.sync()
        self.changed.emit()

    @Slot(QObject)
    def attachPopup(self, window):
        self.popup = window
        window.activeChanged.connect(self.changed.emit)

    @Slot()
    def detachPopup(self):
        self.popup = None

    @Slot()
    def showMain(self):
        if self.window:
            self.window.showNormal()
            self.window.raise_()
            self.window.requestActivate()

    @Slot()
    def showPlayer(self):
        if not self.active:
            self.showMain()
            return
        if self.popup:
            self.positionPopup()
            self.popup.show()
            self.popup.raise_()
            self.popup.requestActivate()

    @Slot()
    def positionPopup(self):
        if not self.popup:
            return
        area = QGuiApplication.primaryScreen().availableGeometry()
        try:
            if self.popup.isVisible():
                x, y = self.popup.x(), self.popup.y()
            else:
                x, y = int(self.settings.value("trayX", area.right() - self.popup.width())), int(self.settings.value("trayY", area.bottom() - self.popup.height()))
        except (TypeError, ValueError):
            x, y = area.right() - self.popup.width(), area.bottom() - self.popup.height()
        x, y = clamped_position(x, y, self.popup.width(), self.popup.height(), [screen.availableGeometry() for screen in QGuiApplication.screens()])
        self.popup.setPosition(x, y)

    @Slot()
    def savePosition(self):
        if self.popup and self.popup.isVisible():
            self.settings.setValue("trayX", self.popup.x())
            self.settings.setValue("trayY", self.popup.y())
            self.settings.sync()

    def close(self):
        self._closed = True
        self.savePosition()
        if self.tray:
            self.tray.hide()
        if self.popup:
            self.popup.hide()
        if self.menu:
            self.menu.deleteLater()
