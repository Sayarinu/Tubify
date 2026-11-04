"""Windows System Media Transport Controls adapter for the shared playback snapshot."""

from datetime import timedelta
import logging
from pathlib import Path
import time

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication, QObject, Signal

LOG = logging.getLogger(__name__)


PROJECTIONS = (
    "winrt.windows.foundation",
    "winrt.windows.media",
    "winrt.windows.media.interop",
    "winrt.windows.storage.streams",
)


def require_projections():
    """Import every projection used by the controls so packaging gaps fail loudly."""
    import importlib

    for name in PROJECTIONS:
        importlib.import_module(name)


def metadata(snapshot):
    values = (snapshot.get("Metadata") or {})

    def read(key, default=""):
        row = values.get(key)
        return row[1] if row else default

    artists = read("xesam:artist", [])
    return {
        "title": read("xesam:title"),
        "artist": ", ".join(str(artist) for artist in artists if artist),
        "album": read("xesam:album"),
        "duration": max(0., read("mpris:length", 0) / 1_000_000),
        "position": max(0., snapshot.get("Position", 0) / 1_000_000),
        "track": read("mpris:trackid", ""),
        "artwork": read("mpris:artUrl", ""),
        "playing": snapshot.get("PlaybackStatus") == "Playing",
        "can_play": bool(snapshot.get("CanPlay")),
        "can_pause": bool(snapshot.get("CanPause")),
        "can_next": bool(snapshot.get("CanGoNext")),
        "can_previous": bool(snapshot.get("CanGoPrevious")),
        "can_seek": bool(snapshot.get("CanSeek")),
    }


WM_POWERBROADCAST = 0x0218
PBT_APMSUSPEND, PBT_APMRESUMESUSPEND, PBT_APMRESUMEAUTOMATIC = 0x4, 0x7, 0x12


def power_transition(message, wparam):
    """Map a WM_POWERBROADCAST notification to Linux PrepareForSleep semantics."""
    if message != WM_POWERBROADCAST:
        return None
    if wparam == PBT_APMSUSPEND:
        return True
    if wparam in {PBT_APMRESUMESUSPEND, PBT_APMRESUMEAUTOMATIC}:
        return False
    return None


class PowerFilter(QAbstractNativeEventFilter):
    """Watch top-level window messages for suspend and resume."""

    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def nativeEventFilter(self, event_type, message):
        try:
            if bytes(event_type) == b"windows_generic_MSG":
                from ctypes import wintypes

                msg = wintypes.MSG.from_address(int(message))
                transition = power_transition(msg.message, msg.wParam)
                if transition is not None:
                    self.callback(transition)
        except Exception:
            pass
        return False, 0


class WindowsBus(QObject):
    """Publish metadata and timeline to Windows and relay system commands to Playback."""

    command = Signal(str, list)
    preparingForSleep = Signal(bool)
    availabilityChanged = Signal(bool, bool)

    def __init__(self, snapshot, window, parent=None, controls=None, media=None, timeline_factory=None, thumbnail_factory=None):
        super().__init__(parent)
        self.window, self.controls = window, controls
        self.media, self._timeline_factory = media, timeline_factory
        self._thumbnail_factory = thumbnail_factory
        self._snapshot = snapshot
        self._button_token = self._position_token = None
        self._closed = False
        self._published_metadata = None
        self._published_status = None
        self._published_flags = None
        self._power_filter = None
        self._last_timeline_position = None
        self._last_timeline_update = 0.

    def start(self):
        try:
            if self.media is None:
                from winrt.windows import media as win_media

                self.media = win_media
            if self._timeline_factory is None:
                self._timeline_factory = self.media.SystemMediaTransportControlsTimelineProperties
            if self.controls is None:
                from winrt.windows.media.interop import get_for_window

                self.controls = get_for_window(int(self.window.winId()))
            # Registration returns Windows.Foundation tokens; without that projection
            # installed it raises and the overlay would show the track with dead buttons.
            self._button_token = self.controls.add_button_pressed(self._button_pressed)
            self._position_token = self.controls.add_playback_position_change_requested(self._position_requested)
            available = self.publish(self._snapshot, force=True)
            self.availabilityChanged.emit(available, self._watch_power())
        except Exception:
            LOG.warning("Windows media controls are unavailable", exc_info=True)
            self._remove_handlers()
            self.controls = None
            self.availabilityChanged.emit(False, False)

    def _watch_power(self):
        application = QCoreApplication.instance()
        if application is None or self._power_filter is not None:
            return self._power_filter is not None
        self._power_filter = PowerFilter(self._power_changed)
        application.installNativeEventFilter(self._power_filter)
        return True

    def _power_changed(self, sleeping):
        if not self._closed:
            self.preparingForSleep.emit(sleeping)

    def _button_pressed(self, _sender, args):
        if self._closed:
            return
        try:
            buttons = self.media.SystemMediaTransportControlsButton
            actions = {
                buttons.PLAY: "Play",
                buttons.PAUSE: "Pause",
                buttons.PLAY_PAUSE: "PlayPause",
                buttons.STOP: "Stop",
                buttons.NEXT: "Next",
                buttons.PREVIOUS: "Previous",
            }
            action = actions.get(args.button)
            if action:
                self.command.emit(action, [])
        except Exception:
            LOG.warning("Could not handle a Windows media button", exc_info=True)

    def _position_requested(self, _sender, args):
        if self._closed:
            return
        try:
            current = metadata(self._snapshot)
            if current["track"] and current["can_seek"]:
                self.command.emit("SetPosition", [current["track"], round(args.request_time.total_seconds() * 1_000_000)])
        except Exception:
            LOG.warning("Could not handle a Windows media seek request", exc_info=True)

    def publish(self, snapshot, force=False):
        self._snapshot = snapshot
        if not self.controls:
            return False
        try:
            current = metadata(snapshot)
            controls, media = self.controls, self.media
            flags = (bool(current["track"]), current["can_play"], current["can_pause"], current["can_next"], current["can_previous"])
            if force or flags != self._published_flags:
                (controls.is_enabled, controls.is_play_enabled, controls.is_pause_enabled,
                 controls.is_next_enabled, controls.is_previous_enabled) = flags
                controls.is_fast_forward_enabled = False
                controls.is_rewind_enabled = False
                controls.is_stop_enabled = True
                self._published_flags = flags
            status = media.MediaPlaybackStatus.PLAYING if current["playing"] else (
                media.MediaPlaybackStatus.PAUSED if current["track"] else media.MediaPlaybackStatus.STOPPED
            )
            if status != self._published_status:
                controls.playback_status = status
                self._published_status = status
            updater = controls.display_updater
            identity = (current["track"], current["title"], current["artist"], current["album"], current["duration"], current["artwork"])
            if current["track"]:
                metadata_changed = identity != self._published_metadata
                if metadata_changed:
                    updater.type = media.MediaPlaybackType.MUSIC
                    music = updater.music_properties
                    music.title, music.artist, music.album_title = current["title"], current["artist"], current["album"]
                    thumbnail = self._thumbnail(current["artwork"])
                    if thumbnail is not None:
                        updater.thumbnail = thumbnail
                    updater.update()
                    self._published_metadata = identity
                timeline_due = (
                    force
                    or metadata_changed
                    or self._last_timeline_position is None
                    or abs(current["position"] - self._last_timeline_position) >= 5
                    or time.monotonic() - self._last_timeline_update >= 5
                )
                if timeline_due:
                    self._publish_timeline(current)
            else:
                if self._published_metadata is not None:
                    updater.clear_all()
                    updater.update()
                    self._published_metadata = None
            return True
        except Exception:
            LOG.warning("Could not publish Windows media state", exc_info=True)
            self.availabilityChanged.emit(False, False)
            return False

    def _thumbnail(self, artwork):
        """Return a stream reference for http(s) or local artwork; artwork never blocks controls."""
        if not artwork:
            return None
        try:
            if self._thumbnail_factory is None:
                from winrt.windows.foundation import Uri
                from winrt.windows.storage.streams import RandomAccessStreamReference

                self._thumbnail_factory = lambda url: RandomAccessStreamReference.create_from_uri(Uri(url))
            url = artwork if "://" in artwork else Path(artwork).resolve().as_uri()
            return self._thumbnail_factory(url)
        except Exception:
            LOG.info("Windows media artwork is unavailable", exc_info=True)
            return None

    def _publish_timeline(self, current):
        timeline = self._timeline_factory()
        timeline.start_time = timedelta(0)
        timeline.min_seek_time = timedelta(0)
        timeline.position = timedelta(seconds=current["position"])
        timeline.max_seek_time = timedelta(seconds=current["duration"])
        timeline.end_time = timedelta(seconds=current["duration"])
        self.controls.update_timeline_properties(timeline)
        self._last_timeline_position = current["position"]
        self._last_timeline_update = time.monotonic()

    def seeked(self, position):
        current = metadata(self._snapshot)
        if current["track"] and self.controls:
            current["position"] = max(0., float(position))
            try:
                self._publish_timeline(current)
            except Exception:
                self.availabilityChanged.emit(False, False)

    def _remove_handlers(self):
        if not self.controls:
            return
        if self._button_token is not None:
            try:
                self.controls.remove_button_pressed(self._button_token)
            except Exception:
                pass
            self._button_token = None
        if self._position_token is not None:
            try:
                self.controls.remove_playback_position_change_requested(self._position_token)
            except Exception:
                pass
            self._position_token = None

    def close(self):
        if self._closed:
            return
        self._closed = True
        self._remove_handlers()
        application = QCoreApplication.instance()
        if self._power_filter is not None and application is not None:
            application.removeNativeEventFilter(self._power_filter)
            self._power_filter = None
        if self.controls:
            try:
                self.controls.is_enabled = False
                self.controls.playback_status = self.media.MediaPlaybackStatus.STOPPED
                self.controls.display_updater.clear_all()
                self.controls.display_updater.update()
            except Exception:
                pass
