"""macOS Now Playing and media keys, fed the same snapshot and commands as the Linux MPRIS bus."""

from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

ARTWORK_LIMIT = 4 * 1024 * 1024
STATES = {"Playing": 1, "Paused": 2, "Stopped": 3}
# Remote command name, MPRIS command, snapshot capability.
COMMANDS = (
    ("playCommand", "Play", "CanPlay"),
    ("pauseCommand", "Pause", "CanPause"),
    ("togglePlayPauseCommand", "PlayPause", "CanPause"),
    ("stopCommand", "Stop", "CanControl"),
    ("nextTrackCommand", "Next", "CanGoNext"),
    ("previousTrackCommand", "Previous", "CanGoPrevious"),
    ("changePlaybackPositionCommand", "SetPosition", "CanSeek"),
)


def value(metadata, key, default=None):
    entry = metadata.get(key)
    return entry[1] if entry else default


def now_playing(snapshot, keys, position=None):
    """Translate the MPRIS-shaped snapshot to MPNowPlayingInfoCenter fields."""
    metadata = snapshot.get("Metadata") or {}
    if not metadata:
        return None
    playing = snapshot.get("PlaybackStatus") == "Playing"
    elapsed = snapshot.get("Position", 0) if position is None else position
    return {
        keys.MPMediaItemPropertyTitle: value(metadata, "xesam:title", ""),
        keys.MPMediaItemPropertyArtist: ", ".join(value(metadata, "xesam:artist", [])),
        keys.MPMediaItemPropertyAlbumTitle: value(metadata, "xesam:album", ""),
        keys.MPMediaItemPropertyPlaybackDuration: value(metadata, "mpris:length", 0) / 1000000,
        keys.MPNowPlayingInfoPropertyElapsedPlaybackTime: elapsed / 1000000,
        keys.MPNowPlayingInfoPropertyPlaybackRate: 1. if playing else 0.,
    }


def local_path(url):
    if url.startswith("file://"):
        return QUrl(url).toLocalFile()
    return url if url.startswith("/") else ""


def _sleep_observer_class():
    from Foundation import NSObject

    class SleepObserver(NSObject):
        def initWithBus_(self, bus):
            self = self.init()
            if self is not None:
                self.bus = bus
            return self

        def willSleep_(self, notification):
            self.bus.preparingForSleep.emit(True)

        def didWake_(self, notification):
            self.bus.preparingForSleep.emit(False)

    return SleepObserver


_SleepObserver = None


class MacBus(QObject):
    command = Signal(str, list)
    preparingForSleep = Signal(bool)
    availabilityChanged = Signal(bool, bool)

    def __init__(self, snapshot, parent=None, media=None, center=None, commands=None, workspace=None):
        super().__init__(parent)
        if media is None:
            import MediaPlayer as media
        self.media = media
        self.center = center or media.MPNowPlayingInfoCenter.defaultCenter()
        self.commands = commands or media.MPRemoteCommandCenter.sharedCommandCenter()
        self._workspace = workspace
        self._snapshot, self._published = snapshot, None
        self._targets, self._observer = [], None
        self._art_url, self._artwork, self._reply = "", None, None
        self._network = None

    def start(self):
        for name, action, _ in COMMANDS:
            remote = getattr(self.commands, name)()
            self._targets.append((remote, remote.addTargetWithHandler_(self._handler(action))))
        self._observe_sleep()
        self.publish(self._snapshot, force=True)
        self.availabilityChanged.emit(True, self._observer is not None)

    def _handler(self, action):
        def handle(event):
            if action == "SetPosition":
                track = value((self._snapshot.get("Metadata") or {}), "mpris:trackid")
                if track is None:
                    return 1
                self.command.emit(action, [track, int(event.positionTime() * 1000000)])
            else:
                self.command.emit(action, [])
            return 0  # MPRemoteCommandHandlerStatusSuccess

        return handle

    def _observe_sleep(self):
        global _SleepObserver
        try:
            if self._workspace is None:
                from AppKit import NSWorkspace

                self._workspace = NSWorkspace.sharedWorkspace()
            if _SleepObserver is None:
                _SleepObserver = _sleep_observer_class()
        except ImportError:
            return
        self._observer = _SleepObserver.alloc().initWithBus_(self)
        notices = self._workspace.notificationCenter()
        notices.addObserver_selector_name_object_(self._observer, "willSleep:", "NSWorkspaceWillSleepNotification", None)
        notices.addObserver_selector_name_object_(self._observer, "didWake:", "NSWorkspaceDidWakeNotification", None)

    def publish(self, snapshot, force=False):
        # Position ticks are extrapolated by macOS from the rate; only real changes are sent.
        steady = {key: item for key, item in snapshot.items() if key != "Position"}
        self._snapshot = snapshot
        if not force and steady == self._published:
            return
        self._published = steady
        for name, _, capability in COMMANDS:
            getattr(self.commands, name)().setEnabled_(bool(snapshot.get(capability)))
        self._update(snapshot)

    def seeked(self, position):
        self._update(self._snapshot, int(position * 1000000))

    def _update(self, snapshot, position=None):
        info = now_playing(snapshot, self.media, position)
        self.center.setPlaybackState_(STATES.get(snapshot.get("PlaybackStatus"), 3))
        if info is None:
            self.center.setNowPlayingInfo_(None)
            return
        self._load_artwork(value(snapshot["Metadata"], "mpris:artUrl", ""))
        if self._artwork is not None:
            info[self.media.MPMediaItemPropertyArtwork] = self._artwork
        self.center.setNowPlayingInfo_(info)

    def _load_artwork(self, url):
        if url == self._art_url:
            return
        self._art_url, self._artwork = url, None
        if self._reply is not None:
            self._reply.abort()
            self._reply = None
        path = local_path(url)
        if path:
            if Path(path).is_file() and Path(path).stat().st_size <= ARTWORK_LIMIT:
                self._artwork = self._make_artwork(Path(path).read_bytes())
        elif url.startswith("https://"):
            self._network = self._network or QNetworkAccessManager(self)
            reply = self._reply = self._network.get(QNetworkRequest(QUrl(url)))
            reply.finished.connect(lambda: self._artwork_loaded(reply, url))

    def _artwork_loaded(self, reply, url):
        reply.deleteLater()
        if reply is not self._reply:
            return
        self._reply = None
        if reply.error() == QNetworkReply.NetworkError.NoError and url == self._art_url:
            data = bytes(reply.read(ARTWORK_LIMIT))
            self._artwork = self._make_artwork(data)
            if self._artwork is not None:
                self._update(self._snapshot)

    def _make_artwork(self, data):
        try:
            from AppKit import NSImage
            from Foundation import NSData
        except ImportError:
            return None
        image = NSImage.alloc().initWithData_(NSData.dataWithBytes_length_(data, len(data)))
        if image is None:
            return None
        return self.media.MPMediaItemArtwork.alloc().initWithBoundsSize_requestHandler_(image.size(), lambda size: image)

    def close(self):
        for remote, target in self._targets:
            remote.removeTarget_(target)
        self._targets = []
        if self._observer is not None:
            self._workspace.notificationCenter().removeObserver_(self._observer)
            self._observer = None
        if self._reply is not None:
            self._reply.abort()
            self._reply = None
        self.center.setNowPlayingInfo_(None)
        self.center.setPlaybackState_(STATES["Stopped"])
