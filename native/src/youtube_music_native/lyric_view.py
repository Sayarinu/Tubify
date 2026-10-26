"""On-demand lyrics state, with an isolated worker and lightweight timing updates."""

from bisect import bisect_right
import html
import json
from pathlib import Path
import re

from PySide6.QtCore import QObject, Property, QSettings, QTimer, Signal, Slot

from .jobs import Worker
from .lyric_options import clean_options, PROVIDERS


class LyricView(QObject):
    changed = Signal()
    currentLineChanged = Signal()
    optionsChanged = Signal()
    timingChanged = Signal()
    keyChanged = Signal()
    openRequested = Signal()

    def __init__(self, account, player, data_dir, worker=None, fixture=False, parent=None, settings_path=None):
        super().__init__(parent)
        self.account, self.player, self.data_dir, self.fixture = account, player, str(data_dir), fixture
        self.worker = None if fixture else worker if worker is not None else Worker(self, idle_ms=15000)
        self._active, self._loaded, self._busy, self._closed = False, False, False, False
        self._video, self._error, self._request = "", "", None
        self._data, self._starts, self._current = {}, [], -1
        self._settings = QSettings(str(settings_path or Path(data_dir) / "settings.ini"), QSettings.Format.IniFormat)
        try:
            self._options = clean_options(json.loads(self._settings.value("lyrics/options", "{}")))
        except (ValueError, TypeError):
            self._options = clean_options({})
        self._timing_revision, self._word_state = 0, ()
        self._key_request, self._has_key, self._key_message, self._key_action = None, False, "", ""
        player.changed.connect(self._track_changed)
        player.positionChanged.connect(self._position_changed)
        account.sessionChanged.connect(self._reset_session)
        if self.worker:
            self.worker.succeeded.connect(self._succeeded)
            self.worker.failed.connect(self._failed)
        self._track_changed()

    @Property("QVariantMap", notify=changed)
    def data(self):
        return self._data

    @Property(bool, notify=changed)
    def busy(self):
        return self._busy

    @Property(str, notify=changed)
    def error(self):
        return self._error

    @Property(int, notify=currentLineChanged)
    def currentLine(self):
        return self._current

    @Property("QVariantMap", notify=optionsChanged)
    def options(self):
        return self._options

    @Property("QVariantList", notify=optionsChanged)
    def providers(self):
        return [{**row, "name": PROVIDERS[row["id"]]} for row in self._options["providers"]]

    @Property(int, notify=timingChanged)
    def timingRevision(self):
        return self._timing_revision

    @Property(bool, notify=keyChanged)
    def hasKey(self):
        return self._has_key

    @Property(bool, notify=keyChanged)
    def keyBusy(self):
        return self._key_request is not None

    @Property(str, notify=keyChanged)
    def keyMessage(self):
        return self._key_message

    def _save_options(self, value):
        value = clean_options(value)
        if value == self._options:
            return
        lookup_changed = any(value[key] != self._options[key] for key in ("external", "captions", "approximate", "providers"))
        self._options = value
        self._settings.setValue("lyrics/options", json.dumps(value))
        self.optionsChanged.emit()
        self._position_changed()
        if lookup_changed:
            self._invalidate()

    @Slot(str, "QVariant")
    def setOption(self, key, value):
        if key in self._options and key != "providers":
            self._save_options({**self._options, key: value})

    @Slot(str, bool)
    def setProviderEnabled(self, provider, enabled):
        self._save_options({**self._options, "providers": [{**row, "enabled": enabled if row["id"] == provider else row["enabled"]} for row in self._options["providers"]]})

    @Slot(str, int)
    def moveProvider(self, provider, direction):
        rows = [dict(row) for row in self._options["providers"]]
        index = next((i for i, row in enumerate(rows) if row["id"] == provider), -1)
        target = index + direction
        if index >= 0 and direction in (-1, 1) and 0 <= target < len(rows):
            rows[index], rows[target] = rows[target], rows[index]
            self._save_options({**self._options, "providers": rows})

    def _invalidate(self, refresh=False):
        request, self._request = self._request, None
        if self.worker and request is not None:
            self.worker.cancel(request)
        self._loaded, self._busy = False, False
        self._data, self._starts, self._current = {}, [], -1
        self.changed.emit()
        self.currentLineChanged.emit()
        if self._active and self._video:
            self._fetch(refresh)

    @Slot("QVariantMap")
    def playbackStarted(self, track):
        if self._options["autoOpen"]:
            self.openRequested.emit()

    @Slot(str, str)
    def keyAction(self, action, value=""):
        if action not in {"status", "save", "clear"} or self.keyBusy:
            return
        if self.fixture:
            self._key_message = "API key storage is unavailable in the visual fixture."
        else:
            self._key_message, self._key_action = "", action
            self._key_request = self.worker.request("lyrics_key", {"action": action, "value": value})
        self.keyChanged.emit()

    @Slot(int, str, str, result=str)
    def styledLine(self, index, foreground, secondary):
        lines = self._data.get("lines", [])
        if not 0 <= index < len(lines):
            return ""
        row = lines[index]
        def escaped(text):
            return html.escape(text).replace("\n", "<br/>")
        style, sync = self._options["style"], self._data.get("syncLevel")
        if index != self._current or style == "line" or style == "syllable" and sync != "syllable" or not row.get("words"):
            return escaped(row["text"])
        if not all(re.fullmatch(r"#[0-9a-fA-F]{6}", color) for color in (foreground, secondary)):
            return escaped(row["text"])
        result, cursor = [], 0
        for word in row["words"]:
            offset = word["offset"]
            if offset < cursor:
                continue
            result.append(escaped(row["text"][cursor:offset]))
            color = foreground if word["start"] <= self.player.position else secondary
            result.append('<font color="' + color + '">' + escaped(word["text"]) + '</font>')
            cursor = offset + len(word["text"])
        result.append(escaped(row["text"][cursor:]))
        return "".join(result)

    @Slot(bool)
    def setActive(self, value):
        self._active = value
        if value and not self._loaded and not self._busy and self._video and not self._closed:
            self._fetch()

    def _track_changed(self):
        video = self.player.currentTrack.get("videoId") or self.player.currentTrack.get("id", "")
        if video == self._video:
            return
        if self.worker and self._request is not None:
            self.worker.cancelQueued(self._request)
        self._video, self._request, self._busy, self._loaded = video, None, False, False
        self._data, self._starts, self._error, self._current = {}, [], "", -1
        self.changed.emit()
        self.currentLineChanged.emit()
        if self._active and video:
            self._fetch()

    @Slot()
    def refresh(self):
        if self._video and not self._closed:
            self._fetch(refresh=True)

    def _fetch(self, refresh=False):
        if self._closed:
            return
        if self.fixture:
            self._data = {"videoId": self._video, "available": True, "timed": True, "source": "Original visual fixture", "lines": [{"text": text, "start": index * 5., "end": (index + 1) * 5.} for index, text in enumerate(("A familiar tune", "A quiet moment in the evening", "The music carries on"))]}
            self._accept()
            return
        if self._request is not None:
            self.worker.cancelQueued(self._request)
        self._busy, self._error = True, ""
        self._request = self.worker.request("lyrics", {"data_dir": self.data_dir, "videoId": self._video, "refresh": refresh, "track": self.player.currentTrack, "options": self._options})
        self.changed.emit()

    def _succeeded(self, identifier, result):
        if identifier == self._key_request:
            self._key_request, self._has_key, self._key_message = None, bool(result.get("hasKey")), "Key saved in the system keyring." if result.get("hasKey") else "No Better Lyrics key is saved."
            self.keyChanged.emit()
            if self._key_action != "status":
                self._invalidate(refresh=True)
            return
        if identifier != self._request or result.get("videoId") != self._video:
            return
        self._data, self._request, self._busy = result, None, False
        self._accept()

    def _accept(self):
        self._loaded, self._error = True, ""
        self._starts = [row["start"] for row in self._data.get("lines", [])] if self._data.get("timed") else []
        self.changed.emit()
        self._position_changed()

    def _failed(self, identifier, error):
        if identifier == self._key_request:
            self._key_request, self._key_message = None, error.get("message", "The secure keyring is unavailable.")
            self.keyChanged.emit()
            return
        if identifier == self._request:
            self._request, self._busy = None, False
            self._error = error.get("message", "Lyrics could not be loaded. Retry when connected.")
            self.changed.emit()

    def _position_changed(self):
        current = bisect_right(self._starts, self.player.position) - 1 if self._starts else -1
        if current >= 0 and self.player.position >= self._data["lines"][current]["end"]:
            current = -1
        if current != self._current:
            self._current = current
            self.currentLineChanged.emit()
        words = self._data.get("lines", [])[current].get("words", []) if current >= 0 else []
        state = (current, self._options["style"], tuple(word["start"] <= self.player.position for word in words))
        if state != self._word_state:
            self._word_state = state
            self._timing_revision += 1
            self.timingChanged.emit()

    @Slot(int)
    def seekLine(self, index):
        if self._data.get("timed") and 0 <= index < len(self._starts):
            self.player.seek(self._starts[index])

    def _reset_session(self):
        if self.worker:
            self._request, self._busy = None, False
            self._key_request, self._key_action, self._key_message = None, "", ""
            self.keyChanged.emit()
            self.worker.reset()
            if self._active and self._video:
                QTimer.singleShot(0, self._fetch)

    def close(self):
        self._closed = True
        if self.worker:
            self.worker.close()
