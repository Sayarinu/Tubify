from datetime import timedelta
import os
import subprocess
import sys
from types import SimpleNamespace

from PySide6.QtCore import QCoreApplication
import pytest

from youtube_music_native.account.browsers import NoBrowserSession, read_session
from youtube_music_native.system import windows
from youtube_music_native.system.windows import prepare_runtime
from youtube_music_native.system.windows_media import WindowsBus, metadata


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
    assert availability[-1] == (True, True)

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
    (bundle / "helpers").mkdir(parents=True)
    environment = {"PATH": r"C:\Windows\System32"}
    opened = []
    prepare_runtime(environment, platform="linux", bundle=bundle, add_dll_directory=opened.append)
    assert environment == {"PATH": r"C:\Windows\System32"} and opened == []

    prepare_runtime(environment, platform="win32", bundle=bundle, add_dll_directory=opened.append)
    prepare_runtime(environment, platform="win32", bundle=bundle, add_dll_directory=opened.append)
    paths = environment["PATH"].split(";")
    assert paths[0] == str(bundle / "helpers") and str(bundle / "mpv") not in paths
    assert opened == [str(bundle / "helpers")]


def test_windows_loads_bundled_openssl_by_path_crypto_first(tmp_path, monkeypatch):
    monkeypatch.setattr(windows, "_PRELOADED", [])
    helpers = tmp_path / "Tubify" / "helpers"
    helpers.mkdir(parents=True)
    loaded = []
    prepare_runtime({}, platform="win32", bundle=helpers.parent, add_dll_directory=lambda path: None, load_library=loaded.append)
    # Bundles without OpenSSL load nothing.
    assert loaded == []

    for name in windows.OPENSSL:
        (helpers / name).write_bytes(b"")
    prepare_runtime({}, platform="win32", bundle=helpers.parent, add_dll_directory=lambda path: None, load_library=loaded.append)
    prepare_runtime({}, platform="win32", bundle=helpers.parent, add_dll_directory=lambda path: None, load_library=loaded.append)
    assert loaded == [str(helpers / "libcrypto-3-x64.dll"), str(helpers / "libssl-3-x64.dll")]


def test_windows_openssl_load_failure_does_not_stop_startup(tmp_path, monkeypatch):
    monkeypatch.setattr(windows, "_PRELOADED", [])
    helpers = tmp_path / "Tubify" / "helpers"
    helpers.mkdir(parents=True)
    for name in windows.OPENSSL:
        (helpers / name).write_bytes(b"")
    tried = []

    def refuse(path):
        tried.append(path)
        raise OSError("bad image")

    prepare_runtime({}, platform="win32", bundle=helpers.parent, add_dll_directory=lambda path: None, load_library=refuse)
    assert tried == [str(helpers / "libcrypto-3-x64.dll")]


def test_windows_sign_in_failure_explains_locked_chromium_cookies():
    with pytest.raises(NoBrowserSession, match="Firefox"):
        read_session(["chrome"], reader=lambda name: [], platform="win32")
    with pytest.raises(NoBrowserSession) as error:
        read_session(["chrome"], reader=lambda name: [], platform="linux")
    assert "Firefox" not in str(error.value)


def test_windows_media_controls_publish_thumbnail_and_skip_unchanged_flags():
    app = QCoreApplication.instance() or QCoreApplication([])
    controls = Controls()
    references = []
    bus = WindowsBus(snapshot(), window=SimpleNamespace(), controls=controls, media=MEDIA,
                     thumbnail_factory=lambda url: references.append(url) or url)
    value = snapshot()
    value["Metadata"]["mpris:artUrl"] = ("s", "https://example.invalid/art.jpg")
    bus.publish(value, force=True)
    assert controls.display_updater.thumbnail == "https://example.invalid/art.jpg"
    controls.is_next_enabled = "untouched"
    bus.publish(value)
    assert controls.is_next_enabled == "untouched" and references == ["https://example.invalid/art.jpg"]


def test_windows_media_registration_failure_disables_controls():
    app = QCoreApplication.instance() or QCoreApplication([])
    controls = Controls()

    def broken(_handler):
        raise ImportError("winrt._winrt_windows_foundation")

    controls.add_button_pressed = broken
    bus = WindowsBus(snapshot(), window=SimpleNamespace(), controls=controls, media=MEDIA)
    availability = []
    bus.availabilityChanged.connect(lambda *value: availability.append(value))
    bus.start()
    assert availability == [(False, False)] and bus.controls is None
    assert bus.publish(snapshot()) is False


REAL_REGISTRATION = """
from PySide6.QtGui import QGuiApplication, QWindow
from youtube_music_native.system.windows_media import WindowsBus, require_projections
require_projections()
app = QGuiApplication([])
window = QWindow()
window.show()
app.processEvents()
bus = WindowsBus({"Metadata": {}, "Position": 0}, window=window)
available = []
bus.availabilityChanged.connect(lambda value, _sleep: available.append(value))
bus.start()
assert available == [True], available
assert bus._button_token is not None and bus._position_token is not None
bus.close()
"""


@pytest.mark.skipif(sys.platform != "win32", reason="System Media Transport Controls are Windows-only")
def test_windows_media_controls_register_real_handlers():
    environment = {key: value for key, value in os.environ.items() if key != "QT_QPA_PLATFORM"}
    subprocess.run([sys.executable, "-c", REAL_REGISTRATION], check=True, timeout=60, env=environment)


def test_power_broadcast_maps_to_prepare_for_sleep():
    from youtube_music_native.system.windows_media import power_transition, WM_POWERBROADCAST

    assert power_transition(WM_POWERBROADCAST, 0x4) is True
    assert power_transition(WM_POWERBROADCAST, 0x7) is False
    assert power_transition(WM_POWERBROADCAST, 0x12) is False
    assert power_transition(WM_POWERBROADCAST, 0xA) is None
    assert power_transition(0x10, 0x4) is None
