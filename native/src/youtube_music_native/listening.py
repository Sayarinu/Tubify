"""Record actual online listening without blocking playback or local queue changes."""

import re

from PySide6.QtCore import QObject


class Listening(QObject):
    def __init__(self, account, player, cache_path, parent=None):
        super().__init__(parent)
        self.account, self.player, self.worker = account, player, account.worker
        self.cache_path, self._recorded = str(cache_path), False
        self._pending = set()
        player.trackStarted.connect(self._started)
        player.positionChanged.connect(self._progress)
        account.sessionChanged.connect(self._clear)
        if self.worker:
            self.worker.failed.connect(self._failed)
            self.worker.succeeded.connect(lambda identifier, result: self._pending.discard(identifier))

    def _started(self, track):
        self._recorded = False

    def _progress(self):
        video = self.player.currentTrack.get("videoId", "")
        threshold = min(5, self.player.duration / 2) if self.player.duration > 0 else 5
        if self._recorded or not self.worker or not self.account.connected or self.account.busy or not self.player.playing or self.player.position < threshold or not re.fullmatch(r"[A-Za-z0-9_-]{11}", video):
            return
        self._recorded = True
        self._pending.add(self.worker.request("account_history", {"videoId": video, "cache_path": self.cache_path}))

    def _clear(self):
        if self.worker:
            for identifier in self._pending:
                self.worker.cancelQueued(identifier)
        self._pending.clear()
        self._recorded = True

    def _failed(self, identifier, error):
        if identifier in self._pending:
            self._pending.discard(identifier)
            if error.get("code") in {"reconnect", "AuthError"}:
                self.account.requireReconnect("Reconnect YouTube Music to update listening history.")
