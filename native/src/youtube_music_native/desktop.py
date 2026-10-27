"""Desktop integration boundary; catalog and playback remain platform independent."""

import sys

from PySide6.QtCore import QObject, QTimer, Slot
from PySide6.QtGui import QGuiApplication


def platform_bus():
    if sys.platform == "linux":
        from .linux_media import LinuxBus

        return LinuxBus
    if sys.platform == "darwin":
        try:
            from .macos_media import MacBus
            import MediaPlayer  # noqa: F401
        except ImportError:
            # Without PyObjC the app still plays; it just isn't in Now Playing.
            return None
        return MacBus
    return None


class Desktop(QObject):
    def __init__(self, shell, player, window, downloads=None, parent=None, bus_factory=None):
        super().__init__(parent)
        self.shell, self.player, self.window, self.downloads = shell, player, window, downloads
        self.bus, self._sleep_token = None, None
        self.available, self.sleepAvailable = False, False
        self._closed = False
        if bus_factory is None:
            if sys.platform == "win32":
                from .windows_media import WindowsBus

                bus_factory = lambda snapshot, parent=None: WindowsBus(snapshot, window=window, parent=parent)
            else:
                bus_factory = platform_bus()
        if bus_factory:
            self.bus = bus_factory(self.snapshot(), parent=self)
            self.bus.command.connect(self.command)
            self.bus.preparingForSleep.connect(self.prepareForSleep)
            self.bus.availabilityChanged.connect(self._available)
            player.changed.connect(self.publish)
            player.positionChanged.connect(self.publish)
            player.seeked.connect(self.bus.seeked)
            shell.volumeChanged.connect(self.publish)
            if downloads:
                downloads.changed.connect(self.publish)
            self.bus.start()

    def track_id(self):
        entry = self.player.queue.current
        return "/org/mpris/MediaPlayer2/track/" + entry["key"] if entry else "/org/mpris/MediaPlayer2/TrackList/NoTrack"

    def snapshot(self):
        track = self.player.currentTrack
        metadata = {}
        if self.player.hasTrack:
            metadata = {"mpris:trackid": ("o", self.track_id()), "mpris:length": ("x", int(self.player.duration * 1000000)), "xesam:title": ("s", str(track.get("title", ""))), "xesam:artist": ("as", [str(artist["name"]) for artist in track.get("artists", []) if artist.get("name")] or ([track["artist"]] if track.get("artist") else [])), "xesam:album": ("s", str((track.get("album") or {}).get("name", "")))}
            artwork = self.downloads.artwork.get(track.get("videoId") or track.get("id"), "") if self.downloads else ""
            artwork = artwork or track.get("thumbnail", "")
            if artwork:
                metadata["mpris:artUrl"] = ("s", artwork)
        queue = self.player.queue
        return {
            "PlaybackStatus": "Stopped" if self.player.stopped else "Playing" if self.player.wantsPlayback else "Paused",
            "LoopStatus": {"off": "None", "one": "Track", "all": "Playlist"}[self.player.repeat],
            "Rate": 1., "Shuffle": self.player.shuffled, "Metadata": metadata,
            "Volume": self.shell.volume / 100., "Position": int(self.player.position * 1000000),
            "MinimumRate": 1., "MaximumRate": 1.,
            "CanGoNext": queue.peek() is not None or self.player.hasTrack and self.player.autoplay and self.player.radio_worker is not None,
            "CanGoPrevious": self.player.hasTrack and (bool(queue.history) or self.player.position > 3),
            "CanPlay": self.player.hasTrack, "CanPause": self.player.hasTrack,
            "CanSeek": self.player.hasTrack and self.player.duration > 0, "CanControl": True,
        }

    @Slot()
    def publish(self):
        if self.bus:
            self.bus.publish(self.snapshot())

    @Slot(bool, bool)
    def _available(self, media, sleep):
        self.available, self.sleepAvailable = media, sleep

    @Slot(str, list)
    def command(self, name, args):
        if self._closed:
            return
        if name in {"Next", "Previous"}:
            capability = "CanGoNext" if name == "Next" else "CanGoPrevious"
            if not self.snapshot()[capability]:
                return
            paused = not self.player.wantsPlayback
            self.player.next() if name == "Next" else self.player.previous()
            if paused:
                self.player.pause()
        elif name == "Pause":
            self.player.pause()
        elif name == "Play":
            self.player.resume()
        elif name == "Stop":
            self.player.stop()
        elif name == "PlayPause":
            self.player.togglePlayback()
        elif name == "Seek":
            position = self.player.position + args[0] / 1000000
            if self.player.hasTrack:
                self.command("Next", []) if position > self.player.duration else self.player.seek(position)
        elif name == "SetPosition":
            if self.player.hasTrack and args[0] == self.track_id() and 0 <= args[1] <= self.player.duration * 1000000:
                self.player.seek(args[1] / 1000000)
        elif name == "SetVolume":
            self.shell.setVolume(round(max(0., min(1., args[0])) * 100))
        elif name == "SetShuffle":
            self.player.setShuffle(args[0])
        elif name == "SetLoopStatus":
            self.player.setRepeat({"None": "off", "Track": "one", "Playlist": "all"}[args[0]])
        elif name == "SetRate" and args[0] == 0:
            self.player.pause()
        elif name == "Raise":
            self.window.showNormal()
            self.window.raise_()
            self.window.requestActivate()
        elif name == "Quit":
            QGuiApplication.instance().quit()

    @Slot(bool)
    def prepareForSleep(self, preparing):
        if preparing:
            if self._sleep_token is None:
                self._sleep_token = self.player.interrupt()
        elif self._sleep_token is not None:
            token, self._sleep_token = self._sleep_token, None
            QTimer.singleShot(300, lambda: self.player.recover(token))

    def close(self):
        self._closed = True
        if self.bus:
            self.bus.close()
