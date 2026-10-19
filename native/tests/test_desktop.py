from types import SimpleNamespace

from PySide6.QtCore import QCoreApplication, QObject, Signal
from PySide6.QtTest import QTest

from youtube_music_native.desktop import Desktop
from youtube_music_native.playback import Playback
from youtube_music_native.shell import ShellController
from test_playback import FakeAudio, FakeWorker, TRACKS


class Bus(QObject):
    command = Signal(str, list)
    preparingForSleep = Signal(bool)
    availabilityChanged = Signal(bool, bool)

    def __init__(self, snapshot, parent=None):
        super().__init__(parent)
        self.values, self.seeks = [snapshot], []

    def publish(self, value):
        self.values.append(value)

    def start(self):
        pass

    def seeked(self, value):
        self.seeks.append(value)

    def close(self):
        pass


def test_desktop_commands_metadata_and_paused_next_are_consistent(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    worker = FakeWorker()
    player = Playback(tmp_path, worker, audio_factory=FakeAudio)
    shell = ShellController(tmp_path / "settings.ini")
    desktop = Desktop(shell, player, SimpleNamespace(), bus_factory=Bus)
    player.playTracks(TRACKS)
    worker.succeeded.emit(1, {"kind": "local", "source": "/fixture/track.wav"})
    assert desktop.snapshot()["Metadata"]["mpris:length"] == ("x", 120000000)
    first = desktop.track_id()
    desktop.command("SetPosition", ["/stale/track", 30000000])
    assert player.position == 0
    desktop.command("SetPosition", [first, 30000000])
    assert player.position == 30 and desktop.bus.seeks[-1] == 30
    desktop.command("Pause", [])
    desktop.command("Next", [])
    assert not player.wantsPlayback
    worker.succeeded.emit(len(worker.requests), {"kind": "local", "source": "/fixture/second.wav"})
    assert not player.playing and player.audio.loads[-1][2]
    assert desktop.track_id() != first
    desktop.command("SetPosition", [first, 5000000])
    assert player.position == 0
    desktop.command("SetVolume", [0.32])
    desktop.command("SetLoopStatus", ["Track"])
    desktop.command("SetShuffle", [True])
    assert shell.volume == 32 and player.repeat == "one" and player.shuffled
    desktop.command("Play", [])
    assert player.playing
    desktop.command("Stop", [])
    assert player.stopped and not player.playing and player.position == 0
    assert desktop.snapshot()["PlaybackStatus"] == "Stopped"
    desktop.close()
    player.close()


def test_interrupt_recovery_keeps_position_and_ignores_duplicate_or_superseded_tokens(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    worker = FakeWorker()
    player = Playback(tmp_path, worker, audio_factory=FakeAudio)
    player.playTracks(TRACKS[:1])
    worker.succeeded.emit(1, {"kind": "local", "source": "/fixture/track.wav"})
    player.seek(37)
    token = player.interrupt()
    assert not player.playing and player.position == 37 and worker.resets == 1
    player.recover(token)
    request_count = len(worker.requests)
    player.recover(token)
    assert len(worker.requests) == request_count
    worker.succeeded.emit(request_count, {"kind": "local", "source": "/fixture/track.wav"})
    assert player.audio.loads[-1][1] == 37
    token = player.interrupt()
    player.pause()
    player.recover(token)
    assert len(worker.requests) == request_count
    player.resume()
    worker.succeeded.emit(len(worker.requests), {"kind": "remote", "source": "https://media.invalid/fixture"})
    token = player.interrupt()
    player.recover(token)
    assert worker.requests[-1][1]["prepared"] is None
    assert worker.requests[-1][1]["force"] is False
    player.close()


def test_output_failure_does_not_damage_local_audio_or_restart_after_manual_pause(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    worker = FakeWorker()
    player = Playback(tmp_path, worker, audio_factory=FakeAudio)
    player.playTracks(TRACKS[:1])
    worker.succeeded.emit(1, {"kind": "local", "source": "/fixture/track.wav"})
    player.seek(18)
    player.audio.deviceFailed.emit()
    assert not player.playing and player.position == 18 and "audio output" in player.message
    player.audio.outputChanged.emit()
    assert not worker.requests[-1][1]["damaged"]
    worker.succeeded.emit(len(worker.requests), {"kind": "local", "source": "/fixture/track.wav"})
    assert player.audio.loads[-1][1] == 18
    player.audio.deviceFailed.emit()
    player.pause()
    count = len(worker.requests)
    player.audio.outputChanged.emit()
    assert len(worker.requests) == count
    player.close()


def test_duplicate_sleep_and_wake_signals_restart_audio_only_once(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    worker = FakeWorker()
    player = Playback(tmp_path, worker, audio_factory=FakeAudio)
    desktop = Desktop(ShellController(tmp_path / "settings.ini"), player, SimpleNamespace(), bus_factory=Bus)
    player.playTracks(TRACKS[:1])
    worker.succeeded.emit(1, {"kind": "local", "source": "/fixture/track.wav"})
    player.seek(22)
    desktop.prepareForSleep(True)
    desktop.prepareForSleep(True)
    assert worker.resets == 1 and not player.playing
    desktop.prepareForSleep(False)
    desktop.prepareForSleep(False)
    QTest.qWait(350)
    assert len(worker.requests) == 2
    worker.succeeded.emit(2, {"kind": "local", "source": "/fixture/track.wav"})
    assert player.audio.loads[-1][1] == 22 and player.playing
    desktop.close()
    player.close()
