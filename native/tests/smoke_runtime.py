"""Exercise an actual Qt window and libmpv decoder on each CI operating system."""

from pathlib import Path
import subprocess
import sys
import tempfile
import wave

from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer

from youtube_music_native.audio import Audio
from youtube_music_native.compat import play_source


def main():
    with tempfile.TemporaryDirectory(prefix="youtube-music-runtime-") as folder:
        root = Path(folder)
        subprocess.run(
            [sys.executable, "-m", "youtube_music_native.app", "--fixture", "--smoke-test", "--data-dir", str(root)],
            check=True, timeout=30,
        )
        subprocess.run([sys.executable, str(Path(__file__).with_name("smoke_docks.py"))], check=True, timeout=30)
        subprocess.run([sys.executable, str(Path(__file__).with_name("smoke_library.py"))], check=True, timeout=30)
        subprocess.run([sys.executable, str(Path(__file__).with_name("smoke_player.py"))], check=True, timeout=30)
        subprocess.run([sys.executable, str(Path(__file__).with_name("smoke_downloads.py"))], check=True, timeout=30)
        subprocess.run([sys.executable, str(Path(__file__).with_name("smoke_visual.py"))], check=True, timeout=30)
        subprocess.run([sys.executable, str(Path(__file__).with_name("smoke_priority_queue.py"))], check=True, timeout=40)
        audio = root / "fixture.wav"
        with wave.open(str(audio), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(48000)
            handle.writeframes(b"\0\0" * 96000)
        play_source(audio)
        app = QCoreApplication.instance() or QCoreApplication([])
        player = Audio(output="null")
        loop = QEventLoop()
        progress, ended = [], []
        player.updated.connect(lambda values: progress.append(values["time-pos"]) if isinstance(values.get("time-pos"), (int, float)) else None)
        player.ended.connect(lambda failed: (ended.append(failed), loop.quit()))
        player.volume(37)
        player.load({"kind": "local", "source": str(audio)}, position=0.2)
        QTimer.singleShot(10000, loop.quit)
        loop.exec()
        player.close()
        assert progress and max(progress) >= 1
        assert ended == [False]
    print("Native Qt launch and local libmpv playback passed.")


if __name__ == "__main__":
    main()
