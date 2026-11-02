from http.cookiejar import CookieJar
from pathlib import Path
import shutil
import subprocess
import time
from types import SimpleNamespace

from PySide6.QtCore import QCoreApplication, QObject, Signal
import pytest

from youtube_music_native import sources
from youtube_music_native.compat import edl
from youtube_music_native.media import MediaFiles
from youtube_music_native.playback import Playback
from youtube_music_native.sources import Sources
from youtube_music_native.video import fit, has_video

from test_playback import FakeAudio, FakeWorker


VIDEO = {"videoId": "abcdefghijk", "title": "Official video", "duration": 120, "videoType": "MUSIC_VIDEO_TYPE_OMV"}
SONG = {"videoId": "lmnopqrstuv", "title": "Album track", "duration": 180, "videoType": "MUSIC_VIDEO_TYPE_ATV"}


class VideoAudio(FakeAudio):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.frames, self.videoCapable, self.video = QObject(), True, []

    def setVideo(self, enabled):
        self.video.append(enabled)
        return enabled


def test_edl_keeps_urls_with_commas_intact_and_fit_respects_the_720p_cap():
    video, audio = "https://v.invalid/a?sparams=expire,ei", "https://a.invalid/b"
    # Byte-length prefixes let mpv read URLs containing commas and semicolons.
    assert edl([video, audio]) == f"edl://!new_stream;!no_clip;!no_chapters;%{len(video)}%{video};!new_stream;!no_clip;!no_chapters;%{len(audio)}%{audio}"
    assert fit(3840, 2160, 1920, 1080) == (1280, 720)
    assert fit(400, 400, 1920, 1080) == (400, 224)
    assert has_video(VIDEO) and not has_video(SONG)


def test_video_plays_only_in_expanded_player_and_falls_back_to_audio(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    worker = FakeWorker()
    player = Playback(tmp_path, worker, audio_factory=VideoAudio)
    player.playTracks([VIDEO, SONG])
    assert not worker.requests[-1][1]["video"]
    worker.succeeded.emit(1, {"kind": "remote", "source": "https://media.invalid/audio", "videoId": VIDEO["videoId"], "expires": time.time() + 3600})
    player.audio.updated.emit({"time-pos": 30.})
    player.setVideoSurface(True)
    # Opening the expanded player reloads the same moment as video.
    assert worker.requests[-1][1]["video"] is True and player.position == 30.
    worker.succeeded.emit(len(worker.requests), {"kind": "remote", "video": True, "source": "edl://fixture", "videoId": VIDEO["videoId"], "expires": time.time() + 3600})
    assert player.showingVideo and player.audio.video[-1] is True
    requests = len(worker.requests)
    player.setVideoPreferred(False)
    app.processEvents()
    # Switching back reuses the prefetched audio without another resolve.
    assert all(payload["videoId"] != VIDEO["videoId"] for _, payload in worker.requests[requests:])
    assert player.audio.loads[-1][0]["source"] == "https://media.invalid/audio"
    assert player.audio.video[-1] is False and not player.showingVideo
    player.setVideoPreferred(True)
    worker.failed.emit(len(worker.requests), {"message": "No video format is available. Playing audio instead."})
    app.processEvents()
    assert not player.videoAvailable and "audio instead" in player.message
    player.setVideoSurface(False)
    player.close()


def test_songs_without_video_never_request_it(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    worker = FakeWorker()
    player = Playback(tmp_path, worker, audio_factory=VideoAudio)
    player.setVideoSurface(True)
    player.playTracks([SONG])
    assert not worker.requests[-1][1]["video"] and not player.videoAvailable
    player.close()


def test_video_resolution_combines_streams_but_downloads_stay_audio(tmp_path, monkeypatch):
    monkeypatch.setattr(sources, "extractor_options", lambda root: {})
    seen = []

    class Extractor:
        cookiejar = CookieJar()

        def __init__(self, options):
            seen.append(options["format"])

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def extract_info(self, url, download):
            return {"requested_formats": [
                {"url": "https://media.invalid/video?expire=4102444800", "vcodec": "avc1", "http_headers": {"User-Agent": "fixture"}},
                {"url": "https://media.invalid/audio?expire=4102444700", "vcodec": "none"},
            ]}

    media = MediaFiles(tmp_path)
    service = Sources(SimpleNamespace(session=SimpleNamespace(cookie_jar=CookieJar)), media, Extractor)
    source = service.resolve("abcdefghijk", video=True)
    assert source["video"] and source["source"].startswith("edl://") and source["expires"] == 4102444700
    assert "height<=720" in seen[0]
    audio = tmp_path / "complete.opus"
    audio.write_bytes(b"complete")
    media.db.execute("INSERT INTO audio VALUES (?, ?, ?, 'ready')", ("abcdefghijk", "complete.opus", 8))
    media.db.commit()
    assert service.resolve("abcdefghijk", video=True)["kind"] == "local"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg creates the local video fixture")
def test_libmpv_software_renderer_produces_frames(tmp_path):
    from PySide6.QtGui import QGuiApplication
    from youtube_music_native.audio import Audio

    pytest.importorskip("mpv")
    app = QCoreApplication.instance() or QGuiApplication([])
    clip = tmp_path / "clip.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25",
                    "-f", "lavfi", "-i", "sine=frequency=440", "-t", "2", "-pix_fmt", "yuv420p", "-y", str(clip)], check=True, timeout=60)
    audio = Audio(output="null")
    try:
        assert audio.frames is None  # audio-only players never create a render context
        assert audio.setVideo(True) and audio.frames is not None, "libmpv lacks the software render API"
        audio.frames.request_size(160, 120)
        audio.load({"source": str(clip), "headers": []})
        deadline = time.monotonic() + 10
        while audio.frames.image.isNull() and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        image = audio.frames.image
        assert not image.isNull() and image.width() == 160 and image.height() == 120
        assert len({image.pixelColor(x, 60).name() for x in range(0, 160, 10)}) > 3
    finally:
        audio.close()
