"""Real libmpv filters with synthetic sources and null output; no speaker access."""
from pathlib import Path
import struct
import tempfile
import wave

from PySide6.QtCore import QCoreApplication
from PySide6.QtTest import QTest

from youtube_music_native.audio import Audio
from youtube_music_native import speaker_fill
from youtube_music_native.speaker_fill import LABEL


def wait_for(predicate):
    for _ in range(100):
        QCoreApplication.processEvents()
        if predicate():
            return
        QTest.qWait(20)
    assert predicate(), "Synthetic libmpv state did not settle"


def main():
    app = QCoreApplication.instance() or QCoreApplication([])
    with tempfile.TemporaryDirectory(prefix="youtube-music-speaker-fill-") as folder:
        root = Path(folder)
        sources = {}
        for name, channels in (("stereo", 2), ("mono", 1), ("surround", 6)):
            path = root / (name + ".wav")
            with wave.open(str(path), "wb") as handle:
                handle.setnchannels(channels)
                handle.setsampwidth(2)
                handle.setframerate(48000)
                handle.writeframes(struct.pack("<" + "h" * channels, *([3000] * channels)) * 48000)
            sources[name] = {"kind": "local", "source": str(path)}
        normal = Audio(output="null")
        try:
            normal.setSpeakerFill(True)
            normal.load(sources["stereo"], paused=True)
            wait_for(lambda: normal._ready)
            assert normal.player.audio_channels == "auto-safe"
            assert normal.player.audio_out_params["channels"] == "stereo"
            assert normal.player.af == []
        finally:
            normal.close()
        for layout in ("5.1", "5.1(side)", "7.1"):
            audio = Audio(output="null")
            states = []
            audio.optionsChanged.connect(states.append)
            try:
                assert audio.player.audio_channels == "auto-safe"
                # Only this null-output fixture requests a surround layout.
                audio.player.audio_channels = layout
                audio.player.command("af", "add", "@fixture:lavfi=[volume=1]")
                audio.load(sources["stereo"], paused=True)
                wait_for(lambda: bool(states and states[-1]["available"]))
                assert not states[-1]["active"]
                audio.setSpeakerFill(True)
                wait_for(lambda: states[-1]["active"])
                assert {f.get("label") for f in audio.player.af} == {"fixture", LABEL}
                assert audio.player.audio_out_params["channels"] == layout
                assert audio.player.audio_params["channels"] == "stereo"
                QTest.qWait(100)
                assert states[-1]["active"] and not states[-1]["failed"]
                assert audio.player.pause and audio.player.audio_device == "auto"
                audio.setSpeakerFill(False)
                assert not states[-1]["active"] and len(audio.player.af) == 1
                original_graph = speaker_fill.channel_graph
                try:
                    speaker_fill.channel_graph = lambda layout: "this-filter-does-not-exist"
                    audio.setSpeakerFill(True)
                    assert states[-1]["failed"] and not states[-1]["active"]
                    assert len(audio.player.af) == 1
                finally:
                    speaker_fill.channel_graph = original_graph
                audio.setSpeakerFill(True)
                assert states[-1]["active"]
                for source in ("mono", "surround"):
                    audio.load(sources[source], paused=True)
                    wait_for(lambda: audio._ready)
                    assert not states[-1]["available"] and not states[-1]["active"]
                    assert len(audio.player.af) == 1
                audio.load(sources["stereo"], paused=True)
                wait_for(lambda: states[-1]["active"])
                audio.stop()
                assert not states[-1]["active"] and len(audio.player.af) == 1
            finally:
                audio.close()
    print("libmpv stereo/surround/mono transitions, owned filter and three null-output layouts passed.")


if __name__ == "__main__":
    main()
