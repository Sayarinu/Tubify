"""Decode a source/manual/source sequence through real worker processes and libmpv."""

from pathlib import Path
import tempfile
import wave

from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer

from youtube_music_native.audio import Audio
from youtube_music_native.jobs import Worker
from youtube_music_native.media import MediaFiles
from youtube_music_native.playback import Playback


def main():
    app = QCoreApplication.instance() or QCoreApplication([])
    with tempfile.TemporaryDirectory(prefix="youtube-music-priority-") as folder:
        root = Path(folder)
        media = MediaFiles(root / "media")
        audio = media.root / "fixture.wav"
        with wave.open(str(audio), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(48000)
            handle.writeframes(b"\0\0" * 24000)
        tracks = [{"videoId": identifier, "title": "Synthetic local audio", "duration": 0.5} for identifier in ("sourcefirst", "manualtrack", "sourcesecon")]
        for track in tracks:
            media.publish(track["videoId"], audio)
        media.close()
        player = Playback(root, Worker(), audio_factory=lambda **options: Audio(output="null", **options))
        player.toggleAutoplay()
        loop, started = QEventLoop(), []

        def record(track):
            started.append((track["videoId"], player.sourceKind))
            if len(started) == 1:
                player.enqueue([tracks[1]])

        player.trackStarted.connect(record)
        player.changed.connect(lambda: loop.quit() if len(started) == 3 and player.stopped else None)
        player.playTracks([tracks[0], tracks[2]])
        QTimer.singleShot(15000, loop.quit)
        loop.exec()
        snapshot = player.queue.snapshot(player.position)
        player.close()
        assert started == [(track["videoId"], "local") for track in tracks], started
        assert not snapshot["manual"]
        restored = Playback(root, Worker(), audio_factory=lambda **options: Audio(output="null", **options))
        restore_loop = QEventLoop()
        restored.trackStarted.connect(lambda track: restore_loop.quit())
        QTimer.singleShot(10000, restore_loop.quit)
        restore_loop.exec()
        assert restored.sourceKind == "local" and not restored.playing
        assert restored.queue.snapshot(snapshot["position"]) == snapshot
        restored.close()
    print("Real libmpv source/manual/source playback and paused restart passed.")


if __name__ == "__main__":
    main()
