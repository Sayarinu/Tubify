"""Check installed code and durable local media across an Arch package upgrade."""

import argparse
import hashlib
import json
from pathlib import Path
import wave

from PySide6.QtCore import QSettings

import youtube_music_native
from youtube_music_native.compat import play_source
from youtube_music_native.downloads import DownloadStore
from youtube_music_native.playback import write_state
from youtube_music_native.queue import Queue
from youtube_music_native.sources import Sources


TRACK = {"kind": "song", "videoId": "fixture0001", "title": "Package fixture", "duration": 3}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("prepare", "verify"))
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    assert Path(youtube_music_native.__file__).resolve().is_relative_to("/usr/lib"), "Test the installed package, not the source checkout"
    args.root.mkdir(parents=True, exist_ok=True)
    store = DownloadStore(args.root)
    settings = QSettings(str(args.root / "settings.ini"), QSettings.Format.IniFormat)
    if args.phase == "prepare":
        audio = store.root / "fixture.wav"
        with wave.open(str(audio), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(48000)
            handle.writeframes(b"\0\0" * 48000 * 3)
        key = store.schedule({"kind": "playlist", "id": "PLfixture", "title": "Upgrade fixture", "items": [TRACK, TRACK]})
        store.media.publish(TRACK["videoId"], audio)
        store.progress(key, 2, 2, state="complete")
        queue = Queue()
        queue.replace([TRACK, TRACK])
        write_state(args.root / "playback.json", json.dumps(queue.snapshot(1.25)))
        settings.setValue("volume", 31)
        settings.sync()
        (args.root / "audio.sha256").write_text(hashlib.sha256(audio.read_bytes()).hexdigest())
    else:
        class NoAccount:
            @property
            def session(self):
                raise AssertionError("Local playback must not access account credentials")
        source = Sources(NoAccount(), store.media).resolve(TRACK["videoId"])
        assert source["kind"] == "local"
        audio = Path(source["source"])
        assert hashlib.sha256(audio.read_bytes()).hexdigest() == (args.root / "audio.sha256").read_text()
        collection = store.lookup("playlist", "PLfixture")
        assert len(collection["items"]) == 2 and all(track["downloadState"] == "ready" for track in collection["items"])
        queue = Queue()
        assert queue.restore(json.loads((args.root / "playback.json").read_text())) == 1.25
        assert len(queue.entries) == 2 and int(settings.value("volume")) == 31
        play_source(audio)
    store.close()
    print("Installed package and preserved local media check passed: " + args.phase)


if __name__ == "__main__":
    main()
