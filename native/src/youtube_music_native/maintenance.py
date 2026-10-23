"""Explicit release lookup and allowlisted local diagnostics; no telemetry or updater."""

from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
import json
import math
from pathlib import Path
import platform
import re
import sys
import tomllib
from urllib.request import Request, urlopen

from PySide6.QtCore import QObject, Property, QUrl, Signal, Slot, qVersion
from PySide6.QtGui import QGuiApplication

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


def perform(payload, opener=urlopen):
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
        return "On Arch Linux, update youtube-music-native through your package manager. Other installations should use their native release instructions. This app does not install updates."

    def _request(self, action, payload):
        if self.busy:
            return
        if self._worker is None:
            self._worker = self._factory(self, idle_ms=15000)
            self._worker.succeeded.connect(self._result)
            self._worker.failed.connect(self._failed)
        identifier = self._worker.request("maintenance", {"action": action, **payload})
        self._pending[identifier] = action
        self.changed.emit()

    @Slot()
    def checkRelease(self):
        if self.busy:
            return
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
        if self._worker:
            self._worker.close()
        self._pending.clear()
