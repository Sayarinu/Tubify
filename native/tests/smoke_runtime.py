"""Exercise an actual Qt window and libmpv decoder on each CI operating system."""

from pathlib import Path
import subprocess
import sys
import tempfile
import wave

from youtube_music_native.compat import play_source


def main():
    with tempfile.TemporaryDirectory(prefix="youtube-music-runtime-") as folder:
        root = Path(folder)
        subprocess.run(
            [sys.executable, "-m", "youtube_music_native.app", "--fixture", "--smoke-test", "--data-dir", str(root)],
            check=True, timeout=30,
        )
        audio = root / "fixture.wav"
        with wave.open(str(audio), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(48000)
            handle.writeframes(b"\0\0" * 96000)
        play_source(audio)
    print("Native Qt launch and local libmpv playback passed.")


if __name__ == "__main__":
    main()
