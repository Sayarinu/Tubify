from datetime import timedelta
from types import SimpleNamespace

from PySide6.QtCore import QCoreApplication
import pytest

from youtube_music_native.browsers import NoBrowserSession, read_session
from youtube_music_native.windows import prepare_runtime
from youtube_music_native.windows_media import WindowsBus, metadata


class Event:
    def __init__(self):
        self.handlers = {}
        self.next_token = 1

    def add(self, callback):
        token, self.next_token = self.next_token, self.next_token + 1
        self.handlers[token] = callback
        return token

    def remove(self, token):
        self.handlers.pop(token)

    def fire(self, args):
        for callback in tuple(self.handlers.values()):
            callback(self, args)


class Timeline:
    def __init__(self):
        self.start_time = self.min_seek_time = self.position = None
        self.max_seek_time = self.end_time = None


class DisplayUpdater:
    def __init__(self):
        self.music_properties = SimpleNamespace(title="", artist="", album_title="")
        self.type, self.updates, self.clears = None, 0, 0

    def update(self):
        self.updates += 1

    def clear_all(self):
        self.clears += 1


class Controls:
    def __init__(self):
        self.button_pressed = Event()
        self.playback_position_change_requested = Event()
        self.display_updater = DisplayUpdater()
        self.timeline_updates = []
        # pywinrt exposes WinRT events as add_<event>(handler) -> token and remove_<event>(token).
        self.add_button_pressed, self.remove_button_pressed = self.button_pressed.add, self.button_pressed.remove
        self.add_playback_position_change_requested = self.playback_position_change_requested.add
        self.remove_playback_position_change_requested = self.playback_position_change_requested.remove

    def update_timeline_properties(self, value):
        self.timeline_updates.append(value)


MEDIA = SimpleNamespace(
    MediaPlaybackStatus=SimpleNamespace(PLAYING="playing", PAUSED="paused", STOPPED="stopped"),
    MediaPlaybackType=SimpleNamespace(MUSIC="music"),
    SystemMediaTransportControlsButton=SimpleNamespace(
        PLAY="PLAY", PAUSE="PAUSE", PLAY_PAUSE="PLAY_PAUSE", STOP="STOP", NEXT="NEXT", PREVIOUS="PREVIOUS",
    ),
    SystemMediaTransportControlsTimelineProperties=Timeline,
)


def snapshot(status="Playing", position=5_000_000):
    return {
        "PlaybackStatus": status,
        "Position": position,
        "Metadata": {
            "mpris:trackid": ("o", "/track/1"),
            "mpris:length": ("x", 120_000_000),
            "xesam:title": ("s", "Song"),
            "xesam:artist": ("as", ["First", "Second"]),
            "xesam:album": ("s", "Album"),
        },
        "CanPlay": True,
        "CanPause": True,
        "CanGoNext": True,
        "CanGoPrevious": False,
        "CanSeek": True,
    }


def test_windows_media_controls_publish_track_state_and_forward_commands():
    app = QCoreApplication.instance() or QCoreApplication([])
    controls = Controls()
    bus = WindowsBus(snapshot(), window=SimpleNamespace(), controls=controls, media=MEDIA)
    commands, availability = [], []
    bus.command.connect(lambda *value: commands.append(value))
    bus.availabilityChanged.connect(lambda *value: availability.append(value))

    bus.start()
    updater = controls.display_updater
    assert controls.is_enabled and controls.is_play_enabled and controls.is_next_enabled
    assert not controls.is_previous_enabled and controls.playback_status == "playing"
    assert updater.music_properties.title == "Song"
    assert updater.music_properties.artist == "First, Second"
    assert updater.music_properties.album_title == "Album"
    assert controls.timeline_updates[-1].position == timedelta(seconds=5)
    assert availability[-1] == (True, False)

    controls.button_pressed.fire(SimpleNamespace(button=MEDIA.SystemMediaTransportControlsButton.PLAY_PAUSE))
    controls.playback_position_change_requested.fire(SimpleNamespace(request_time=timedelta(seconds=42.5)))
    assert commands == [("PlayPause", []), ("SetPosition", ["/track/1", 42_500_000])]

    bus.publish(snapshot("Paused", 10_000_000))
    assert controls.playback_status == "paused"
    bus.seeked(30)
    assert controls.timeline_updates[-1].position == timedelta(seconds=30)
    bus.close()
    assert not controls.button_pressed.handlers
    assert not controls.playback_position_change_requested.handlers
    assert not controls.is_enabled and controls.display_updater.clears == 1


def test_windows_metadata_handles_empty_track_and_runtime_paths_are_platform_scoped(tmp_path):
    assert metadata({"Metadata": {}, "Position": 0})["track"] == ""
    bundle = tmp_path / "Tubify"
    (bundle / "mpv").mkdir(parents=True)
    (bundle / "helpers").mkdir()
    environment = {"PATH": r"C:\Windows\System32"}
    opened = []
    prepare_runtime(environment, platform="linux", bundle=bundle, add_dll_directory=opened.append)
    assert environment == {"PATH": r"C:\Windows\System32"} and opened == []

    prepare_runtime(environment, platform="win32", bundle=bundle, add_dll_directory=opened.append)
    prepare_runtime(environment, platform="win32", bundle=bundle, add_dll_directory=opened.append)
    paths = environment["PATH"].split(";")
    assert paths[:2] == [str(bundle / "helpers"), str(bundle / "mpv")]
    assert opened == [str(bundle / "mpv"), str(bundle / "helpers")]


def test_windows_sign_in_failure_explains_locked_chromium_cookies():
    with pytest.raises(NoBrowserSession, match="Firefox"):
        read_session(["chrome"], reader=lambda name: [], platform="win32")
    with pytest.raises(NoBrowserSession) as error:
        read_session(["chrome"], reader=lambda name: [], platform="linux")
    assert "Firefox" not in str(error.value)
