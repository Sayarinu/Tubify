"""Opt-in listening preferences and a pause-only wall-clock sleep timer."""

import math
import time

from PySide6.QtCore import QObject, Property, QSettings, QTimer, Signal, Slot


class PlaybackOptions(QObject):
    changed = Signal()
    timerChanged = Signal()
    PRESETS = (5, 10, 15, 30, 45, 60)

    def __init__(self, path, player, parent=None, clock=time.time):
        super().__init__(parent)
        self.settings = QSettings(str(path), QSettings.Format.IniFormat)
        self.player, self.clock = player, clock
        self._nonlinear = self.settings.value("nonlinearVolume", False, type=bool)
        self._skip = self.settings.value("skipDisliked", False, type=bool)
        self._deadline, self._remaining, self._status = None, 0, ""
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.tick)
        player.setNonlinearVolume(self._nonlinear)
        player.setSkipDisliked(self._skip)

    @Property(bool, notify=changed)
    def nonlinearVolume(self):
        return self._nonlinear

    @Property(bool, notify=changed)
    def skipDisliked(self):
        return self._skip

    @Slot(bool)
    def setNonlinearVolume(self, value):
        self._nonlinear = bool(value)
        self.settings.setValue("nonlinearVolume", self._nonlinear)
        self.settings.sync()
        self.player.setNonlinearVolume(self._nonlinear)
        self.changed.emit()

    @Slot(bool)
    def setSkipDisliked(self, value):
        self._skip = bool(value)
        self.settings.setValue("skipDisliked", self._skip)
        self.settings.sync()
        self.player.setSkipDisliked(self._skip)
        self.changed.emit()

    @Property(int, notify=timerChanged)
    def sleepRemaining(self):
        return self._remaining

    @Property(str, notify=timerChanged)
    def sleepStatus(self):
        return self._status

    @Slot(int)
    def startSleep(self, minutes):
        if minutes not in self.PRESETS:
            return
        self._deadline = self.clock() + minutes * 60
        self._status = ""
        self.tick()
        self.timer.start()

    @Slot()
    def cancelSleep(self):
        self.timer.stop()
        self._deadline, self._remaining, self._status = None, 0, ""
        self.timerChanged.emit()

    @Slot()
    def tick(self):
        if self._deadline is None:
            return
        self._remaining = max(0, math.ceil(self._deadline - self.clock()))
        if not self._remaining:
            self.timer.stop()
            self._deadline = None
            self.player.pause()
            self._status = "Sleep timer finished. Playback paused."
        self.timerChanged.emit()

    def close(self):
        self.timer.stop()
