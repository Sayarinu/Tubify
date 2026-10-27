"""Windows System Media Transport Controls adapter for the shared playback snapshot."""

from datetime import timedelta
import time

from PySide6.QtCore import QObject, Signal


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
        "playing": snapshot.get("PlaybackStatus") == "Playing",
        "can_play": bool(snapshot.get("CanPlay")),
        "can_pause": bool(snapshot.get("CanPause")),
        "can_next": bool(snapshot.get("CanGoNext")),
        "can_previous": bool(snapshot.get("CanGoPrevious")),
        "can_seek": bool(snapshot.get("CanSeek")),
    }


class WindowsBus(QObject):
    """Publish metadata and timeline to Windows and relay system commands to Playback."""

    command = Signal(str, list)
    preparingForSleep = Signal(bool)
    availabilityChanged = Signal(bool, bool)

    def __init__(self, snapshot, window, parent=None, controls=None, media=None, timeline_factory=None):
        super().__init__(parent)
        self.window, self.controls = window, controls
        self.media, self._timeline_factory = media, timeline_factory
        self._snapshot = snapshot
        self._button_token = self._position_token = None
        self._closed = False
        self._published_metadata = None
        self._published_status = None
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
            self._button_token = self.controls.add_button_pressed(self._button_pressed)
            self._position_token = self.controls.add_playback_position_change_requested(self._position_requested)
            available = self.publish(self._snapshot, force=True)
            self.availabilityChanged.emit(available, False)
        except Exception:
            self._remove_handlers()
            self.availabilityChanged.emit(False, False)

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
            pass

    def _position_requested(self, _sender, args):
        if self._closed:
            return
        try:
            current = metadata(self._snapshot)
            if current["track"] and current["can_seek"]:
                self.command.emit("SetPosition", [current["track"], round(args.request_time.total_seconds() * 1_000_000)])
        except Exception:
            pass

    def publish(self, snapshot, force=False):
        self._snapshot = snapshot
        if not self.controls:
            return False
        try:
            current = metadata(snapshot)
            controls, media = self.controls, self.media
            controls.is_enabled = bool(current["track"])
            controls.is_play_enabled = current["can_play"]
            controls.is_pause_enabled = current["can_pause"]
            controls.is_next_enabled = current["can_next"]
            controls.is_previous_enabled = current["can_previous"]
            controls.is_fast_forward_enabled = False
            controls.is_rewind_enabled = False
            controls.is_stop_enabled = True
            status = media.MediaPlaybackStatus.PLAYING if current["playing"] else (
                media.MediaPlaybackStatus.PAUSED if current["track"] else media.MediaPlaybackStatus.STOPPED
            )
            if status != self._published_status:
                controls.playback_status = status
                self._published_status = status
            updater = controls.display_updater
            identity = (current["track"], current["title"], current["artist"], current["album"], current["duration"])
            if current["track"]:
                metadata_changed = identity != self._published_metadata
                if metadata_changed:
                    updater.type = media.MediaPlaybackType.MUSIC
                    music = updater.music_properties
                    music.title, music.artist, music.album_title = current["title"], current["artist"], current["album"]
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
            self.availabilityChanged.emit(False, False)
            return False

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
        if self.controls:
            try:
                self.controls.is_enabled = False
                self.controls.playback_status = self.media.MediaPlaybackStatus.STOPPED
                self.controls.display_updater.clear_all()
                self.controls.display_updater.update()
            except Exception:
                pass
