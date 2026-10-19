"""Verify the real MPRIS wire protocol on an isolated session bus with local audio."""

from pathlib import Path
import tempfile
from threading import Thread
import time
import traceback
from types import SimpleNamespace
import wave

from PySide6.QtCore import QCoreApplication, QTimer
from jeepney import DBusAddress, new_method_call
from jeepney.bus_messages import message_bus, MatchRule
from jeepney.io.blocking import open_dbus_connection
from jeepney.low_level import HeaderFields, MessageType

from youtube_music_native.audio import Audio
from youtube_music_native.desktop import Desktop
from youtube_music_native.jobs import Worker
from youtube_music_native.linux_media import LinuxBus, PLAYER, PROPERTIES, PATH
from youtube_music_native.media import MediaFiles
from youtube_music_native.playback import Playback
from youtube_music_native.shell import ShellController


def main():
    app = QCoreApplication([])
    passed, failures = [], []
    with tempfile.TemporaryDirectory(prefix="youtube-music-desktop-") as directory:
        root = Path(directory)
        media = MediaFiles(root / "media")
        audio = media.root / "fixture.wav"
        with wave.open(str(audio), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(16000)
            handle.writeframes(b"\0\0" * 16000 * 60)
        media.publish("abcdefghijk", audio)
        media.close()
        worker = Worker()
        player = Playback(root, worker, audio_factory=lambda **options: Audio(output="null", **options))
        shell = ShellController(root / "settings.ini")
        desktop = Desktop(shell, player, SimpleNamespace(), bus_factory=lambda snapshot, parent: LinuxBus(snapshot, parent, monitor_sleep=False))
        player.playTracks([{"videoId": "abcdefghijk", "title": "Original desktop fixture", "artist": "Fixture artist", "duration": 60}])

        def client():
            connection = None
            try:
                connection = open_dbus_connection()
                properties = DBusAddress(PATH, bus_name=desktop.bus.service, interface=PROPERTIES)
                transport = DBusAddress(PATH, bus_name=desktop.bus.service, interface=PLAYER)
                def call(address, member, signature="", body=()):
                    result = connection.send_and_get_reply(new_method_call(address, member, signature or None, body), timeout=5)
                    assert result.header.message_type == MessageType.method_return
                    return result.body
                def get(name):
                    return call(properties, "Get", "ss", (PLAYER, name))[0]
                def wait_value(name, expected):
                    deadline = time.monotonic() + 5
                    while time.monotonic() < deadline:
                        value = get(name)[1]
                        if value == expected:
                            return
                        time.sleep(0.01)
                    raise AssertionError("Desktop state did not update: " + name)
                values = call(properties, "GetAll", "s", (PLAYER,))[0]
                assert values["Position"][0] == "x"
                metadata = values["Metadata"][1]
                assert metadata["mpris:trackid"][0] == "o"
                assert metadata["mpris:length"] == ("x", 60000000)
                assert metadata["xesam:artist"] == ("as", ["Fixture artist"])
                owner = connection.send_and_get_reply(message_bus.GetNameOwner(desktop.bus.service), timeout=5).body[0]
                rule = MatchRule(type="signal", sender=owner, interface=PLAYER, member="Seeked", path=PATH)
                subscribed = connection.send_and_get_reply(message_bus.AddMatch(rule), timeout=5)
                assert subscribed.header.message_type == MessageType.method_return
                with connection.filter(rule, bufsize=10) as signals:
                    call(transport, "Pause")
                    wait_value("PlaybackStatus", "Paused")
                    call(transport, "SetPosition", "ox", (metadata["mpris:trackid"][1], 3000000))
                    message = connection.recv_until_filtered(signals, timeout=5)
                    assert message.header.fields[HeaderFields.signature] == "x" and message.body == (3000000,)
                    assert get("Position") == ("x", 3000000)
                    call(transport, "SetPosition", "ox", ("/stale/track", 5000000))
                    assert get("Position") == ("x", 3000000)
                    call(properties, "Set", "ssv", (PLAYER, "Volume", ("d", 0.32)))
                    wait_value("Volume", 0.32)
                    call(properties, "Set", "ssv", (PLAYER, "LoopStatus", ("s", "Track")))
                    wait_value("LoopStatus", "Track")
                    call(properties, "Set", "ssv", (PLAYER, "Shuffle", ("b", True)))
                    wait_value("Shuffle", True)
                    invalid = connection.send_and_get_reply(new_method_call(properties, "Set", "ssv", (PLAYER, "Volume", ("s", "invalid"))), timeout=5)
                    assert invalid.header.message_type == MessageType.error
                    call(transport, "Play")
                    wait_value("PlaybackStatus", "Playing")
                    call(transport, "Stop")
                    wait_value("PlaybackStatus", "Stopped")
                    call(transport, "PlayPause")
                    wait_value("PlaybackStatus", "Playing")
                    passed.append(True)
            except Exception:
                failures.append(traceback.format_exc())
            finally:
                if connection:
                    connection.close()

        state = {"thread": None}
        def tick():
            if state["thread"] is None and desktop.available and player.position > 0.2:
                state["thread"] = Thread(target=client, daemon=True)
                state["thread"].start()
            if passed or failures:
                app.quit()
        timer = QTimer()
        timer.setInterval(20)
        timer.timeout.connect(tick)
        timer.start()
        QTimer.singleShot(20000, app.quit)
        app.exec()
        desktop.close()
        player.close()
        if state["thread"]:
            state["thread"].join(timeout=1)
        assert passed, failures or "Desktop bus did not become available"
    print("MPRIS typed metadata, properties, transport, seek signals and local audio passed.")


if __name__ == "__main__":
    main()
