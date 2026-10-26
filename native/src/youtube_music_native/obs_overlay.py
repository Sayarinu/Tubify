"""Read-only OBS URL creation and layout preferences; secrets remain in memory."""
import re
from urllib.parse import urlencode

from PySide6.QtCore import QObject, Property, QSettings, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QGuiApplication

LAYOUTS = ("full", "compact", "text", "badge", "poster", "ticker", "display")
FLAGS = ("art", "title", "artist", "progress", "transparent")


class ObsOverlay(QObject):
    changed = Signal()

    def __init__(self, api, settings_path, parent=None, browser=QDesktopServices.openUrl):
        super().__init__(parent)
        self.api, self.browser = api, browser
        self.settings = QSettings(str(settings_path), QSettings.Format.IniFormat)
        self._client = str(self.settings.value("obs/clientId", ""))
        self._token, self._status = "", ""
        layout = self.settings.value("obs/layout", "full")
        self._options = {"layout": layout if layout in LAYOUTS else "full", **{key: self.settings.value("obs/" + key, True, type=bool) for key in FLAGS}, "scale": max(.25, min(4, self.settings.value("obs/scale", 1., type=float))), "paused": self.settings.value("obs/paused", "show")}
        if self._options["paused"] not in ("show", "hide"):
            self._options["paused"] = "show"
        self.api.changed.connect(self.changed)

    @Property("QVariantMap", notify=changed)
    def options(self):
        return dict(self._options)

    @Property(bool, notify=changed)
    def hasSource(self):
        return bool(self._token)

    @Property(bool, notify=changed)
    def hasClient(self):
        return bool(self._client)

    @Property(str, notify=changed)
    def status(self):
        return self._status

    @Property(str, notify=changed)
    def suggestedSize(self):
        return {"full": "480 × 160", "compact": "360 × 100", "text": "480 × 100", "badge": "320 × 80", "poster": "320 × 420", "ticker": "800 × 64", "display": "1280 × 720"}[self._options["layout"]]

    @Slot(str, "QVariant")
    def setOption(self, key, value):
        if key == "layout" and value in LAYOUTS or key == "paused" and value in ("show", "hide"):
            pass
        elif key in FLAGS and isinstance(value, bool):
            pass
        elif key == "scale" and isinstance(value, (int, float)) and .25 <= value <= 4:
            value = round(value, 2)
        else:
            return
        self._options[key] = value
        self.settings.setValue("obs/" + key, value)
        self.changed.emit()

    def source_url(self, preview=False):
        params = {key: int(value) if isinstance(value, bool) else value for key, value in self._options.items()}
        if preview:
            params["preview"] = 1
        base = self.api.overlayUrl
        if not base or not self.api.active:
            return ""
        return base + "?" + urlencode(params) + ("" if preview else "#" + urlencode({"token": self._token}))

    @Slot()
    def generate(self):
        if not self.api.active:
            self._status = "Enable the local API before creating an OBS source."
        else:
            if self._client and not self.api.revokeClient(self._client):
                self._status = "The previous OBS source could not be revoked. Check local API settings and retry."
                self.changed.emit()
                return
            self._client, self._token = "", ""
            self.settings.remove("obs/clientId")
            client = self.api.createClient("OBS Now Playing", "overlay")
            if not client or client.get("scope") != "overlay" or not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", str(client.get("token", ""))):
                self._status = "The OBS source could not be paired. Review local API settings and retry."
            else:
                self._client, self._token = client["clientId"], client["token"]
                self.settings.setValue("obs/clientId", self._client)
                self._status = "Read-only OBS source ready. Copy its URL into an OBS Browser Source."
        self.changed.emit()

    @Slot()
    def copySource(self):
        url = self.source_url()
        if url and self._token:
            QGuiApplication.clipboard().setText(url)
            self._status = "OBS source URL copied. Keep it private; it grants read-only now-playing access."
            self.changed.emit()

    @Slot()
    def preview(self):
        url = self.source_url(preview=True)
        if not url:
            self._status = "Enable the local API to open the synthetic overlay preview."
        elif not self.browser(QUrl(url)):
            self._status = "The browser could not open. Check your default browser and retry."
        else:
            self._status = "Synthetic preview opened. It contains no listening data."
        self.changed.emit()

    @Slot()
    def revoke(self):
        if self._client and not self.api.revokeClient(self._client):
            self._status = "OBS access could not be revoked. Check local API storage permissions and retry."
            self.changed.emit()
            return
        self._client, self._token = "", ""
        self.settings.remove("obs/clientId")
        self._status = "OBS access revoked. Existing sources will stop receiving music information."
        self.changed.emit()
