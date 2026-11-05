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
from ..jobs import Worker
from ..util import atomic_write

REPOSITORY = "https://github.com/Sayarinu/Tubify"
RELEASE_API = "https://api.github.com/repos/Sayarinu/Tubify/releases"
CHANNELS = ("stable", "experimental")
CHECK_INTERVAL = 6 * 60 * 60
NOTES_LIMIT = 1500


def release_notes(value):
    """Plain, bounded release notes; the popup renders them as text, never markup."""
    text = value if isinstance(value, str) else ""
    # The popup shows what changed; the download table after "---" is for the release page.
    text = re.split(r"(?m)^-{3,}\s*$", text.replace("\r\n", "\n"), maxsplit=1)[0]
    text = "\n".join(re.sub(r"^#{1,6}\s+", "", line.rstrip()) for line in text.splitlines()).strip()
    return text if len(text) <= NOTES_LIMIT else text[:NOTES_LIMIT].rstrip() + "…"


def installed_version():
    source = Path(__file__).resolve().parents[3] / "pyproject.toml"
    try:
        return tomllib.loads(source.read_text(encoding="utf-8"))["project"]["version"]
    except (OSError, KeyError, ValueError):
        try:
            return version("youtube-music-native")
        except PackageNotFoundError:
            return "unknown"


def release_version(value):
    """Sortable version (stable X.Y.Z or experimental X.Y.ZbN), or None."""
    return updates.version_key(value)


def channel_accepts(row, channel):
    """Stable sees only stable releases; experimental sees both and takes the newest."""
    tag = row.get("tag_name", "")
    if row.get("draft") or not updates.tag_version(tag) or bool(row.get("prerelease")) != updates.is_experimental(tag):
        return False
    return channel == "experimental" or not updates.is_experimental(tag)


def cache_fits(cached, channel):
    """A cached lookup still answers for ``channel``: experimental also sees stable releases,
    and caches written before channels existed were stable lookups."""
    return cached.get("channel", "stable") in (CHANNELS if channel == "experimental" else ("stable",))


def lookup_release(opener=urlopen, channel="stable"):
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
            if isinstance(row, dict) and channel_accepts(row, channel):
                tag = row["tag_name"]
                candidates.append((release_version(tag), tag, release_notes(row.get("body"))))
        if len(rows) < 100:
            if not candidates:
                raise ValueError("No Tubify release found")
            _, tag, notes = max(candidates)
            return {"tag": tag, "notes": notes, "channel": channel, "checkedAt": datetime.now(timezone.utc).isoformat(timespec="seconds")}
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


UNSIGNED_UPDATE = "This update couldn't be verified as coming from Tubify, so it wasn't installed."


def perform(payload, opener=urlopen, progress=None):
    if payload.get("action") == "download":
        try:
            return updates.download(payload["tag"], payload["directory"], progress, opener)
        except updates.UnsignedUpdate:
            return {"error": UNSIGNED_UPDATE}
        except Exception:
            return {"error": "Update download failed. Check your connection and free disk space, then retry."}
    if payload.get("action") == "install":
        try:
            updates.launch_installer(payload["asset"], payload["parent_pid"])
            return {"started": True}
        except updates.UnsignedUpdate:
            return {"error": UNSIGNED_UPDATE}
        except Exception:
            return {"error": "Installer could not start. Retry or use Release Details."}
    if payload.get("action") == "release":
        path = Path(payload["cache_path"])
        channel = payload.get("channel") if payload.get("channel") in CHANNELS else "stable"
        try:
            result = lookup_release(opener, channel)
        except Exception:
            try:
                if path.stat().st_size > 16384:
                    raise ValueError()
                cached = json.loads(path.read_text(encoding="utf-8"))
                if not updates.tag_version(str(cached.get("tag", ""))) or not cache_fits(cached, channel):
                    raise ValueError()
                checked = datetime.fromisoformat(cached["checkedAt"]).isoformat(timespec="seconds")
                return {"tag": cached["tag"], "checkedAt": checked, "stale": True}
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                return {"error": "Release information is unavailable. Check your connection and retry."}
        try:
            atomic_write(path, json.dumps(result))
        except OSError:
            return {**result, "warning": "Release checked, but its offline cache could not be saved."}
        return result
    if payload.get("action") == "export":
        try:
            report = public_diagnostics(payload.get("snapshot") or {})
            atomic_write(Path(payload["path"]), json.dumps(report, indent=2) + "\n")
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
        self._notes, self._downgrade, self._switching = "", False, False
        self._mac = None
        self.settings = getattr(shell, "settings", None)
        if self.settings is None:
            self.settings = QSettings(str(Path(cache_path).parent.parent / "settings.ini"), QSettings.Format.IniFormat)
        self._supported = updates.supported() and not fixture
        self._automatic = self.settings.value("updates/automatic", True, type=bool)
        # Experimental builds follow the experimental channel until the user picks Stable.
        channel = str(self.settings.value("updates/channel", "") or "")
        self._channel = channel if channel in CHANNELS else "experimental" if updates.is_experimental(installed_version()) else "stable"
        self.timer = QTimer(self)
        self.timer.setInterval(3600000)
        self.timer.timeout.connect(self._check_due)

    @Property(QUrl, constant=True)
    def noticesUrl(self):
        """Third-party license notices shipped inside every package."""
        return QUrl.fromLocalFile(str(Path(__file__).resolve().parents[1] / "assets" / "THIRD_PARTY_NOTICES.md"))

    @Property(str, constant=True)
    def currentVersion(self):
        return installed_version()

    @Property(str, constant=True)
    def versionName(self):
        return updates.release_name(installed_version())

    @Property(str, notify=changed)
    def channel(self):
        return self._channel

    @Property(bool, notify=changed)
    def switchingChannel(self):
        """The offered build moves this install onto the selected channel."""
        return self._available and self._switching

    @Property(bool, notify=changed)
    def downgrading(self):
        """The offered build is an older stable release replacing an experimental one."""
        return self._available and self._downgrade

    @Slot(str)
    def setChannel(self, channel):
        if channel not in CHANNELS or channel == self._channel:
            return
        self._channel = channel
        self.settings.setValue("updates/channel", channel)
        self.settings.sync()
        self._tag, self._available, self._downgrade, self._switching, self._notes = "", False, False, False, ""
        self.changed.emit()
        self.checkRelease()

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
        return "Updates preserve settings and downloaded music. Installation may request OS authorization." if updates.supported() else "This installation needs a manual upgrade using Release Details. In-app updates support the packaged Linux, Windows and macOS apps."

    @Property(bool, notify=changed)
    def automaticChecks(self):
        return self._automatic

    @Property(bool, notify=changed)
    def updateAvailable(self):
        return self._available

    @Property(str, notify=changed)
    def latestName(self):
        return updates.release_name(self._tag) if self._tag else ""

    @Property(str, notify=changed)
    def releaseNotes(self):
        return self._notes

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

    def _known_newer(self):
        """A previously found release that is newer than this build."""
        try:
            if Path(self._cache).stat().st_size > 16384:
                return False
            cached = json.loads(Path(self._cache).read_text(encoding="utf-8"))
            if not cache_fits(cached, self._channel):
                return False
            latest, current = release_version(cached.get("tag")), release_version(self.currentVersion)
            return bool(latest and current and latest > current)
        except (OSError, ValueError, TypeError, AttributeError):
            return False

    def _channel_differs(self):
        """The selected channel isn't the one this build came from, so a switch may be waiting."""
        return updates.is_experimental(self.currentVersion) != (self._channel == "experimental")

    def start(self):
        if self.installSupported:
            self.timer.start()
            # Re-confirm a known update or a chosen switch right away so the offer returns
            # after a restart; cached data alone never advertises an install.
            due = self._known_newer() or self._channel_differs()
            QTimer.singleShot(3000 if due else 5000, self.checkRelease if due else self._check_due)
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
            if not 0 <= time.time() - last < CHECK_INTERVAL:
                self.checkRelease()

    @Slot()
    def installUpdate(self):
        if not self.installSupported or not self._available or self.busy:
            return
        if sys.platform == "darwin":
            if self._downgrade:
                # Sparkle only installs newer builds; an older stable build is a manual download.
                self._status = "To switch to " + self.latestName + " on macOS, download it from Release Details and replace Tubify."
                self.changed.emit()
                return
            try:
                if self._mac is None:
                    from ..system.macos_updates import MacUpdater
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
        self._available, self._downgrade, self._switching = False, False, False
        self.settings.setValue("updates/lastAttempt", time.time())
        self._status = "Checking for " + self._channel + " releases…"
        self._request("release", {"cache_path": self._cache, "channel": self._channel})

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
                self._request("install", {"asset": {**result, "downgrade": self._downgrade}, "parent_pid": os.getpid()})
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
            label = updates.release_name(tag)
            if not latest or not updates.tag_version(tag):
                self._status = "Release information is invalid. Retry later."
            else:
                self._url = REPOSITORY + "/releases/tag/" + tag
                # Leaving the experimental channel offers the latest stable build even when it is older.
                downgrade = bool(current) and latest < current and updates.is_experimental(self.currentVersion) and self._channel == "stable"
                # Experimental also offers newer stable releases, which are ordinary updates for a stable build.
                switching = self._channel_differs() and updates.is_experimental(tag) == (self._channel == "experimental")
                if result.get("stale"):
                    self._status = "Offline or lookup failed. Last known " + self._channel + " release: " + label + ". Checked " + result.get("checkedAt", "unknown") + ". Retry for current status."
                elif current and (latest > current or downgrade):
                    self._tag, self._available, self._downgrade, self._switching = tag, True, downgrade, switching
                    self._notes = release_notes(result.get("notes"))
                    self._status = (label + " is available to switch to " + self._channel.capitalize() + "." if switching else label + " is available.")
                elif current == latest:
                    self._status = "You have the latest " + self._channel + " release, " + label + "."
                else:
                    self._status = "The latest " + self._channel + " release is " + label + ". This build has a different version."
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
