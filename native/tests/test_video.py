from http.cookiejar import CookieJar
from pathlib import Path
import shutil
import subprocess
import time
from types import SimpleNamespace

from PySide6.QtCore import QCoreApplication, QObject, Signal
import pytest

from tubify.playback import sources
from tubify.playback.media import MediaFiles
from tubify.playback.playback import Playback
from tubify.playback.sources import Sources
from tubify.playback.video import fit, has_video

from test_playback import FakeAudio, FakeWorker


VIDEO = {"videoId": "abcdefghijk", "title": "Official video", "duration": 120, "videoType": "MUSIC_VIDEO_TYPE_OMV"}
SONG = {"videoId": "lmnopqrstuv", "title": "Album track", "duration": 180, "videoType": "MUSIC_VIDEO_TYPE_ATV"}


class VideoAudio(FakeAudio):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.frames, self.videoCapable = QObject(), True


AUDIO_SOURCE = {"kind": "remote", "source": "https://media.invalid/audio", "videoId": VIDEO["videoId"], "expires": time.time() + 3600}
VIDEO_SOURCE = {"kind": "remote", "video": True, "source": "https://media.invalid/video", "videoId": VIDEO["videoId"], "expires": time.time() + 3600}


def playing_video(tmp_path, track=VIDEO):
    """A player partway through the song's audio, with the expanded player open on Song."""
    QCoreApplication.instance() or QCoreApplication([])
    worker = FakeWorker()
    player = Playback(tmp_path, worker, audio_factory=VideoAudio)
    player.setVideoPreferred(False)
    player.setVideoSurface(True)
    player.playTracks([track])
    worker.succeeded.emit(1, {**AUDIO_SOURCE, "videoId": track["videoId"]})
    player.audio.updated.emit({"time-pos": 30.})
    return player, worker


def test_fit_respects_the_720p_cap_and_only_video_types_have_video():
    assert fit(3840, 2160, 1920, 1080) == (1280, 720)
    assert fit(400, 400, 1920, 1080) == (400, 224)
    assert has_video(VIDEO) and not has_video(SONG)


@pytest.mark.parametrize("paused", [False, True])
def test_swapping_between_song_and_video_never_touches_the_audio(tmp_path, paused):
    player, worker = playing_video(tmp_path)
    audio = player.audio
    if paused:
        player.pause()
    stops, loads, wants = audio.stops, len(audio.loads), player.wantsPlayback
    player.setVideoPreferred(True)
    assert worker.requests[-1][1]["video"] is True and not player.showingVideo
    assert player.position == 30. and not player.busy
    worker.succeeded.emit(len(worker.requests), VIDEO_SOURCE)
    assert audio.attached == [VIDEO_SOURCE]
    audio.videoAttached.emit(1, True)
    audio.videoFirstFrame.emit()
    assert player.showingVideo
    player.setVideoPreferred(False)
    assert audio.video[-1] is False and not player.showingVideo
    # The track stays attached, so coming back needs no second resolve.
    requests = len(worker.requests)
    player.setVideoPreferred(True)
    audio.videoFirstFrame.emit()
    assert audio.video[-1] is True and player.showingVideo and len(worker.requests) == requests
    # So does leaving the expanded player.
    player.setVideoSurface(False)
    assert not player.showingVideo
    assert (audio.stops, len(audio.loads), player.wantsPlayback, player.position) == (stops, loads, wants, 30.)
    player.close()


def test_changing_mode_while_the_video_resolves_keeps_the_audio_and_the_answer(tmp_path):
    player, worker = playing_video(tmp_path)
    audio = player.audio
    stops, loads = audio.stops, len(audio.loads)
    player.setVideoPreferred(True)
    requests = len(worker.requests)
    player.setVideoPreferred(False)
    player.setVideoPreferred(True)
    assert len(worker.requests) == requests  # The running resolve is still the answer.
    player.setVideoPreferred(False)
    worker.succeeded.emit(requests, VIDEO_SOURCE)
    assert not audio.attached  # Video is no longer wanted, so nothing opens.
    player.setVideoPreferred(True)
    assert audio.attached == [VIDEO_SOURCE] and len(worker.requests) == requests
    # Turned off while it opens: the track arrives and is hidden again.
    player.setVideoPreferred(False)
    audio.videoAttached.emit(1, True)
    assert audio.video[-1] is False and not player.showingVideo
    assert (audio.stops, len(audio.loads)) == (stops, loads)
    player.close()


@pytest.mark.parametrize("failure", ["resolve", "open"])
def test_a_video_that_cannot_load_leaves_the_audio_playing(tmp_path, failure):
    player, worker = playing_video(tmp_path)
    audio = player.audio
    stops, loads = audio.stops, len(audio.loads)
    player.setVideoPreferred(True)
    if failure == "resolve":
        worker.failed.emit(len(worker.requests), {"message": "No video format is available. Playing audio instead."})
    else:
        worker.succeeded.emit(len(worker.requests), VIDEO_SOURCE)
        audio.videoAttached.emit(1, False)
    assert "audio instead" in player.message
    assert not player.videoAvailable and not player.showingVideo and player.wantsPlayback
    assert (audio.stops, len(audio.loads)) == (stops, loads)
    player.close()


def test_the_next_song_does_not_inherit_the_video(tmp_path):
    QCoreApplication.instance() or QCoreApplication([])
    worker = FakeWorker()
    player = Playback(tmp_path, worker, audio_factory=VideoAudio)
    player.setVideoSurface(True)
    player.playTracks([VIDEO, {**VIDEO, "videoId": "bbbbbbbbbbb"}])
    # Audio always starts first, so a slow video never delays the song.
    assert not worker.requests[-1][1].get("video")
    worker.succeeded.emit(1, AUDIO_SOURCE)
    assert worker.requests[-1][1]["video"] is True
    worker.succeeded.emit(len(worker.requests), VIDEO_SOURCE)
    player.audio.videoAttached.emit(1, True)
    player.audio.videoFirstFrame.emit()
    assert player.showingVideo
    player.select(1)
    assert not player.showingVideo
    # A late answer about the previous song's video changes nothing.
    player.audio.videoAttached.emit(1, True)
    assert not player.showingVideo
    next_audio = [index for index, (_, payload) in enumerate(worker.requests, 1) if payload["videoId"] == "bbbbbbbbbbb"][-1]
    worker.succeeded.emit(next_audio, {**AUDIO_SOURCE, "videoId": "bbbbbbbbbbb"})
    assert player.audio.video[-1] is False and worker.requests[-1][1]["video"] is True and worker.requests[-1][1]["videoId"] == "bbbbbbbbbbb"
    player.close()


def test_artwork_loading_lasts_until_the_first_frame(tmp_path):
    player, worker = playing_video(tmp_path)
    audio = player.audio
    assert not player.videoLoading  # Song mode has nothing to wait for.
    player.setVideoPreferred(True)
    assert player.videoLoading and not player.showingVideo  # Resolving.
    worker.succeeded.emit(len(worker.requests), VIDEO_SOURCE)
    assert player.videoLoading and not player.showingVideo  # Opening.
    audio.videoAttached.emit(1, True)
    assert player.videoLoading and not player.showingVideo  # Open, with nothing drawn yet.
    audio.videoFirstFrame.emit()
    assert player.showingVideo and not player.videoLoading
    # Hiding and showing again waits for a new frame instead of showing the old one.
    player.setVideoPreferred(False)
    assert not player.videoLoading and not player.showingVideo
    player.setVideoPreferred(True)
    assert player.videoLoading and not player.showingVideo
    audio.videoFirstFrame.emit()
    assert player.showingVideo and not player.videoLoading
    player.close()


def test_a_first_frame_can_arrive_before_the_open_is_reported(tmp_path):
    player, worker = playing_video(tmp_path)
    player.setVideoPreferred(True)
    worker.succeeded.emit(len(worker.requests), VIDEO_SOURCE)
    player.audio.videoFirstFrame.emit()
    assert not player.showingVideo
    player.audio.videoAttached.emit(1, True)
    assert player.showingVideo and not player.videoLoading
    player.close()


def test_a_video_that_never_draws_stops_loading_and_leaves_the_audio_playing(tmp_path):
    player, worker = playing_video(tmp_path)
    audio = player.audio
    stops, loads = audio.stops, len(audio.loads)
    player.setVideoPreferred(True)
    worker.succeeded.emit(len(worker.requests), VIDEO_SOURCE)
    assert player._video_timeout.isActive()
    audio.videoAttached.emit(1, True)
    player._video_timeout.timeout.emit()
    assert not player.videoLoading and not player.showingVideo and not player.videoAvailable
    assert "audio instead" in player.message and audio.video[-1] is False
    assert (audio.stops, len(audio.loads)) == (stops, loads) and player.wantsPlayback
    player.close()


def test_a_video_opening_after_the_timeout_stays_hidden(tmp_path):
    player, worker = playing_video(tmp_path)
    player.setVideoPreferred(True)
    worker.succeeded.emit(len(worker.requests), VIDEO_SOURCE)
    player._video_timeout.timeout.emit()
    player.audio.video.clear()
    player.audio.videoAttached.emit(1, True)
    assert player.audio.video == [False] and not player.showingVideo
    player.close()


def test_downloaded_songs_offer_no_video(tmp_path):
    QCoreApplication.instance() or QCoreApplication([])
    worker = FakeWorker()
    player = Playback(tmp_path, worker, audio_factory=VideoAudio)
    player.setVideoSurface(True)
    player.playTracks([VIDEO])
    worker.succeeded.emit(1, {"kind": "local", "source": "/music/song.opus", "headers": [], "videoId": VIDEO["videoId"]})
    assert not player.videoAvailable and len(worker.requests) == 1 and not player.audio.attached
    player.close()


def test_songs_without_video_never_request_it(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    worker = FakeWorker()
    player = Playback(tmp_path, worker, audio_factory=VideoAudio)
    player.setVideoSurface(True)
    player.playTracks([SONG])
    assert not worker.requests[-1][1].get("video") and not player.videoAvailable
    player.close()


def test_video_resolution_returns_the_picture_stream_but_downloads_stay_audio(tmp_path, monkeypatch):
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
    assert source["video"] and source["source"] == "https://media.invalid/video?expire=4102444800" and source["expires"] == 4102444800
    assert source["headers"] == ["User-Agent: fixture"]
    assert "height<=720" in seen[0]
    audio = tmp_path / "complete.opus"
    audio.write_bytes(b"complete")
    media.db.execute("INSERT INTO audio VALUES (?, ?, ?, 'ready')", ("abcdefghijk", "complete.opus", 8))
    media.db.commit()
    assert service.resolve("abcdefghijk", video=True)["kind"] == "local"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg creates the local video fixture")
def test_libmpv_software_renderer_produces_frames(tmp_path):
    from PySide6.QtGui import QGuiApplication
    from tubify.playback.audio import Audio

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


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg creates the local fixtures")
def test_libmpv_adds_and_hides_video_while_the_audio_keeps_playing(tmp_path):
    from PySide6.QtGui import QGuiApplication
    from tubify.playback.audio import Audio

    pytest.importorskip("mpv")
    app = QCoreApplication.instance() or QGuiApplication([])
    song, clip = tmp_path / "song.m4a", tmp_path / "clip.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440", "-t", "20", "-y", str(song)], check=True, timeout=60)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25", "-t", "20", "-pix_fmt", "yuv420p", "-y", str(clip)], check=True, timeout=60)
    audio = Audio(output="null")
    results, restarts, ends = [], [], []
    audio.videoAttached.connect(lambda token, succeeded: results.append((token, succeeded)))
    audio.fileEnded.connect(lambda: ends.append(True))
    audio.player.event_callback("playback-restart")(lambda event: restarts.append(True))

    def pump(seconds, until=lambda: False):
        deadline = time.monotonic() + seconds
        while not until() and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)

    def clock():
        return audio.player.audio_pts

    def assert_audio_kept_time(since_clock, since_wall):
        # The restart and end-of-file events catch a stop or reload. This catches audio going
        # missing some other way, allowing for how far a busy CI machine's null output falls behind.
        assert abs((clock() - since_clock) - (time.monotonic() - since_wall)) < 1

    try:
        audio.load({"source": str(song), "headers": []}, 2)
        pump(10, lambda: clock() is not None and clock() > 2.2)
        begin_clock, begin_wall = clock(), time.monotonic()
        restarts.clear()
        first_frames = []
        audio.videoFirstFrame.connect(lambda: first_frames.append(True))
        token = audio.attachVideo({"source": str(clip), "headers": []})
        audio.frames.request_size(160, 120)
        pump(10, lambda: results and not audio.frames.image.isNull())
        assert results == [(token, True)] and not audio.frames.image.isNull() and first_frames == [True]
        pump(1.5)  # The picture reaches the audio shortly after its first frame.
        assert abs(audio.player.avsync) < 0.1
        assert_audio_kept_time(begin_clock, begin_wall)
        audio.setVideo(False)
        assert audio.frames.image.isNull()
        pump(0.3)
        assert_audio_kept_time(begin_clock, begin_wall)
        audio.setVideo(True)
        pump(5, lambda: not audio.frames.image.isNull())
        assert not audio.frames.image.isNull() and first_frames == [True, True]
        pump(1.5)
        assert abs(audio.player.avsync) < 0.1
        assert_audio_kept_time(begin_clock, begin_wall)
        assert not restarts and not ends

        bad = audio.attachVideo({"source": str(tmp_path / "missing.mp4"), "headers": []})
        pump(5, lambda: (bad, False) in results)
        assert (bad, False) in results
        assert_audio_kept_time(begin_clock, begin_wall)
    finally:
        audio.close()
