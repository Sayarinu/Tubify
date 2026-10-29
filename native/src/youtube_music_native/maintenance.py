"""Explicit release lookup and allowlisted local diagnostics; no telemetry."""

from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
import json
import math
import os
import time
from pathlib import Path
import platform
import re
import sys
import tomllib
from urllib.request import Request, urlopen

from PySide6.QtCore import QObject, Property, QUrl, QSettings, QTimer, Signal, Slot, qVersion
from PySide6.QtGui import QGuiApplication

from . import updates
from .jobs import Worker
from .playback import write_state

REPOSITORY = "https://github.com/Sayarinu/YouTube-Music-App"
RELEASE_API = "https://api.github.com/repos/Sayarinu/YouTube-Music-App/releases"
VERSION = re.compile(r"(?:native-v)?(\d+)\.(\d+)\.(\d+)$")


def installed_version():
    source = Path(__file__).resolve().parents[2] / "pyproject.toml"
    try:
        return tomllib.loads(source.read_text(encoding="utf-8"))["project"]["version"]
    except (OSError, KeyError, ValueError):
        try:
            return version("youtube-music-native")
        except PackageNotFoundError:
            return "unknown"


def release_version(value):
    match = VERSION.fullmatch(value) if isinstance(value, str) else None
    return tuple(map(int, match.groups())) if match else None


def lookup_release(opener=urlopen):
    """Bound listing size and reject partial scans instead of claiming up-to-date."""
    candidates = []
    for page in range(1, 6):
        request = Request(f"{RELEASE_API}?per_page=100&page={page}", headers={"Accept": "application/vnd.github+json", "User-Agent": "youtube-music-native-release-check", "X-GitHub-Api-Version": "2022-11-28"})
        with opener(request, timeout=8) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError("Release response is too large")
        rows = json.loads(raw)
        if not isinstance(rows, list):
            raise ValueError("Invalid release list")
        for row in rows:
            if not isinstance(row, dict) or row.get("draft") or row.get("prerelease"):
                continue
            tag = row.get("tag_name", "")
            number = release_version(tag)
            if number and tag.startswith("native-v"):
                candidates.append((number, tag))
        if len(rows) < 100:
            if not candidates:
                raise ValueError("No stable native release found")
            _, tag = max(candidates)
            return {"tag": tag, "checkedAt": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    raise ValueError("Release listing exceeded its limit")


def public_diagnostics(snapshot):
    """Discard unknown fields and arbitrary text, even when called outside the UI."""
    result = {"schema": 1, "application": "youtube-music-native", "version": installed_version(), "python": platform.python_version(), "qt": qVersion(), "platform": sys.platform, "createdAt": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    result["packages"] = {}
    for name in ("PySide6", "python-mpv", "ytmusicapi", "yt-dlp", "keyring"):
        try:
            result["packages"][name] = version(name)
        except PackageNotFoundError:
            result["packages"][name] = "unavailable"
    choices = {"renderer": {"Unknown", "Software", "OpenGL", "Direct3D11", "Direct3D12", "Vulkan", "Metal", "Null"}, "windowSystem": {"wayland", "xcb", "windows", "cocoa", "offscreen", "minimal"}}
    for key, values in choices.items():
        value = snapshot.get(key)
        result[key] = value if isinstance(value, str) and value in values else "Unknown"
    for key in ("width", "height", "uiScale"):
        value = snapshot.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and 0 <= value <= 20000:
            result[key] = round(value)
    value = snapshot.get("devicePixelRatio")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and 0 < value <= 16:
        result["devicePixelRatio"] = round(value, 2)
    for key in ("reducedMotion", "softwareRequested", "fixture"):
        if isinstance(snapshot.get(key), bool):
            result[key] = snapshot[key]
    return result


def perform(payload, opener=urlopen, progress=None):
    if payload.get("action") == "download":
        try:
            return updates.download(payload["tag"], payload["directory"], progress, opener)
        except Exception:
            return {"error": "Update download failed. Check your connection and free disk space, then retry."}
    if payload.get("action") == "install":
        try:
            updates.launch_installer(payload["asset"], payload["parent_pid"])
            return {"started": True}
        except Exception:
            return {"error": "Installer could not start. Retry or use Release Details."}
    if payload.get("action") == "release":
        path = Path(payload["cache_path"])
        try:
            result = lookup_release(opener)
        except Exception:
            try:
                if path.stat().st_size > 4096:
                    raise ValueError()
                cached = json.loads(path.read_text(encoding="utf-8"))
                if not str(cached.get("tag", "")).startswith("native-v") or not release_version(cached["tag"]):
                    raise ValueError()
                checked = datetime.fromisoformat(cached["checkedAt"]).isoformat(timespec="seconds")
                return {"tag": cached["tag"], "checkedAt": checked, "stale": True}
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                return {"error": "Release information is unavailable. Check your connection and retry."}
        try:
            write_state(path, json.dumps(result))
        except OSError:
            return {**result, "warning": "Release checked, but its offline cache could not be saved."}
        return result
    if payload.get("action") == "export":
        try:
            report = public_diagnostics(payload.get("snapshot") or {})
            write_state(Path(payload["path"]), json.dumps(report, indent=2) + "\n")
            return {"exported": True}
        except (OSError, ValueError, TypeError):
            return {"error": "Diagnostics could not be saved. Choose a writable folder and retry."}
    return {"error": "This maintenance operation is unavailable."}


class Maintenance(QObject):
    changed = Signal()

    def __init__(self, cache_path, shell, parent=None, worker_factory=Worker, fixture=False, software=False):
        super().__init__(parent)
        self._cache, self.shell, self.fixture, self.software = str(cache_path), shell, fixture, software
        self._factory, self._worker, self._pending = worker_factory, None, {}
        self._status, self._export_status, self._url = "Not checked", "", ""
        self.window = None
        self.prepare_restart = lambda: None
        self._tag, self._available, self._progress = "", False, 0
        self._mac = None
        self.settings = getattr(shell, "settings", None)
        if self.settings is None:
            self.settings = QSettings(str(Path(cache_path).parent.parent / "settings.ini"), QSettings.Format.IniFormat)
        self._supported = updates.supported() and not fixture
        self._automatic = self.settings.value("updates/automatic", True, type=bool)
        self.timer = QTimer(self)
        self.timer.setInterval(3600000)
        self.timer.timeout.connect(self._check_due)

    @Property(str, constant=True)
    def currentVersion(self):
        return installed_version()

    @Property(str, notify=changed)
    def status(self):
        return self._status

    @Property(str, notify=changed)
    def exportStatus(self):
        return self._export_status

    @Property(str, notify=changed)
    def releaseUrl(self):
        return self._url

    @Property(bool, notify=changed)
    def busy(self):
        return bool(self._pending)

    @Property(str, constant=True)
    def updateGuidance(self):
        return "Updates preserve settings and downloaded music. Installation may request OS authorization." if updates.supported() else "This installation needs a manual upgrade using Release Details. In-app updates support the packaged Arch, Windows and macOS apps."

    @Property(bool, notify=changed)
    def automaticChecks(self):
        return self._automatic

    @Property(bool, notify=changed)
    def updateAvailable(self):
        return self._available

    @Property(bool, constant=True)
    def installSupported(self):
        return self._supported

    @Property(bool, notify=changed)
    def downloading(self):
        return "download" in self._pending.values()

    @Property(int, notify=changed)
    def progress(self):
        return self._progress

    @Slot(bool)
    def setAutomaticChecks(self, enabled):
        self._automatic = bool(enabled)
        self.settings.setValue("updates/automatic", self._automatic)
        self.settings.sync()
        self.changed.emit()
        self._check_due()

    def start(self):
        if self.installSupported:
            self.timer.start()
            QTimer.singleShot(5000, self._check_due)
        for partial in (Path(self._cache).parent / "updates").glob("*.part"):
            partial.unlink(missing_ok=True)
        receipt = Path(self._cache).parent / "updates/result.json"
        if receipt.exists():
            try:
                success = json.loads(receipt.read_text())["success"]
                self._status = "Update installed." if success else "Installation failed or was cancelled. Retry or use Release Details."
            except (OSError, ValueError, KeyError, TypeError):
                self._status = "The previous update did not finish. Retry or use Release Details."
            receipt.unlink(missing_ok=True)
            self.changed.emit()

    def _check_due(self):
        if self._automatic and self.installSupported and not self.busy:
            last = self.settings.value("updates/lastAttempt", 0, type=float)
            if not 0 <= time.time() - last < 86400:
                self.checkRelease()

    @Slot()
    def installUpdate(self):
        if not self.installSupported or not self._available or self.busy:
            return
        if sys.platform == "darwin":
            try:
                if self._mac is None:
                    from .macos_updates import MacUpdater
                    self._mac = MacUpdater(self.prepare_restart)
                self._mac.install(self._tag)
            except Exception:
                self._status = "The macOS updater could not start. Use Release Details or retry."
                self.changed.emit()
            return
        self._progress = 0
        self._status = "Downloading update…"
        self._request("download", {"tag": self._tag, "directory": str(Path(self._cache).parent / "updates")})

    @Slot()
    def cancelUpdate(self):
        if "download" in self._pending.values():
            self._worker.reset()
            self._pending.clear()
            for path in (Path(self._cache).parent / "updates").glob("*.part"):
                path.unlink(missing_ok=True)
            self._status = "Update download cancelled."
            self.changed.emit()

    def _download_progress(self, identifier, result):
        if self._pending.get(identifier) == "download":
            self._progress = result.get("percent", 0)
            self.changed.emit()

    def _request(self, action, payload):
        if self.busy:
            return
        if self._worker is None:
            self._worker = self._factory(self, idle_ms=15000)
            self._worker.succeeded.connect(self._result)
            self._worker.failed.connect(self._failed)
            if hasattr(self._worker, "progress"):
                self._worker.progress.connect(self._download_progress)
        identifier = self._worker.request("maintenance", {"action": action, **payload})
        self._pending[identifier] = action
        self.changed.emit()

    @Slot()
    def checkRelease(self):
        if self.busy:
            return
        self._available = False
        self.settings.setValue("updates/lastAttempt", time.time())
        self._status = "Checking stable native releases…"
        self._request("release", {"cache_path": self._cache})

    def snapshot(self):
        result = {"windowSystem": QGuiApplication.platformName(), "fixture": self.fixture, "softwareRequested": self.software, "uiScale": getattr(self.shell, "uiScale", 100), "reducedMotion": getattr(self.shell, "reducedMotion", False)}
        if self.window:
            result.update(width=self.window.width(), height=self.window.height(), devicePixelRatio=self.window.devicePixelRatio(), renderer=self.window.rendererInterface().graphicsApi().name)
        return result

    @Slot(QUrl)
    def exportDiagnostics(self, url):
        if not url.isLocalFile() or not url.toLocalFile() or self.busy:
            return
        self._export_status = "Saving diagnostics…"
        self._request("export", {"path": url.toLocalFile(), "snapshot": self.snapshot()})

    @Slot(int, dict)
    def _result(self, identifier, result):
        action = self._pending.pop(identifier, None)
        if action is None:
            return
        if action == "download":
            if result.get("error"):
                self._status = result["error"]
            else:
                self._status = "Preparing installer…"
                self._request("install", {"asset": result, "parent_pid": os.getpid()})
            self.changed.emit()
            return
        if action == "install":
            if result.get("started"):
                QGuiApplication.instance().quit()
            else:
                self._status = result.get("error", "Installer could not start. Retry or use Release Details.")
            self.changed.emit()
            return
        if action == "export":
            self._export_status = result.get("error") or "Diagnostics saved locally."
        elif result.get("error"):
            self._status = result["error"]
        else:
            tag = result.get("tag", "")
            latest, current = release_version(tag), release_version(self.currentVersion)
            if not latest or not tag.startswith("native-v"):
                self._status = "Release information is invalid. Retry later."
            else:
                self._url = REPOSITORY + "/releases/tag/" + tag
                if result.get("stale"):
                    self._status = "Offline or lookup failed. Last known stable: " + tag + ". Checked " + result.get("checkedAt", "unknown") + ". Retry for current status."
                elif current and latest > current:
                    self._tag, self._available = tag, True
                    self._status = "Release available: " + tag
                elif current == latest:
                    self._status = "Installed version matches the latest stable release: " + tag
                else:
                    self._status = "Latest stable release: " + tag + ". This build has a different version."
                if result.get("warning"):
                    self._status += " " + result["warning"]
        self.changed.emit()

    @Slot(int, dict)
    def _failed(self, identifier, error):
        self._result(identifier, {"error": "This operation could not finish. Retry when ready."})

    def close(self):
        self.timer.stop()
        if self._worker:
            self._worker.close()
        self._pending.clear()
