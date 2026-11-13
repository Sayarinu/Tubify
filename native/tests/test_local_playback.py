import os
import time
from types import SimpleNamespace

from PySide6.QtCore import QCoreApplication

from tubify.local.library import LocalLibrary
from tubify.lyrics.lyric_view import LyricView
from tubify.playback.playback import Playback, is_local
from tubify.worker import handle
from test_lyric_view import Account, Player
from test_local_library import LATER, song
from test_playback import FakeAudio, FakeWorker

ONLINE = {"videoId": "abcdefghijk", "title": "Online", "artist": "Artist", "duration": 180}


def forbidden(*args, **kwargs):
    raise AssertionError("Local playback must not touch the account or the network")


OFFLINE_SERVICE = SimpleNamespace(catalog=forbidden, restore=forbidden, session=None)


def library_song(tmp_path, *parts, title="Local"):
    music = tmp_path / "Music"
    path = song(music.joinpath(*parts), title, "Artist", "Album")
    os.utime(path, (time.time() - 60, time.time() - 60))
    library = LocalLibrary(tmp_path / "data")
    library.add_folder(music)
    track = next(entry for entry in library.scan(now=LATER)["songs"] if entry["title"] == title)
    library.close()
    return music, path, track


def resolve(tmp_path, track, resources, **extra):
    return handle(OFFLINE_SERVICE, {"operation": "resolve", "payload": {"data_dir": str(tmp_path / "data"), "videoId": track["videoId"], **extra}}, resources)


def close(resources):
    for value in resources.values():
        value.close()


def test_local_songs_resolve_offline_and_signed_out(tmp_path):
    music, path, track = library_song(tmp_path, "a.wav")
    assert is_local(track) and track["videoId"] == track["localId"] and track["path"] == str(path)
    resources = {}
    source = resolve(tmp_path, track, resources, available=False)
    assert source == {"kind": "local", "source": str(path), "headers": [], "videoId": track["videoId"]}
    close(resources)


def test_missing_disconnected_and_unplayable_files_explain_themselves(tmp_path):
    music, path, track = library_song(tmp_path, "a.wav")
    resources = {}
    path.rename(path.with_name("moved.wav"))
    try:
        resolve(tmp_path, track, resources)
        raise AssertionError("A missing file must not play")
    except Exception as error:
        assert "can't be found" in str(error)
    library = resources[("local", str((tmp_path / "data").resolve()))]
    assert library.song(track["id"])["state"] == "missing"
    path.with_name("moved.wav").rename(path)
    assert resolve(tmp_path, track, resources)["source"] == str(path)
    assert library.song(track["id"])["state"] == "ready"
    music.rename(tmp_path / "Unplugged")
    try:
        resolve(tmp_path, track, resources)
        raise AssertionError("A song on a disconnected drive must not play")
    except Exception as error:
        assert "isn't connected" in str(error)
    assert library.song(track["id"])["state"] == "offline"
    (tmp_path / "Unplugged").rename(music)
    # The backend opened the file and couldn't decode it.
    try:
        resolve(tmp_path, track, resources, damaged=True)
        raise AssertionError("A file that failed to play is reported")
    except Exception as error:
        assert "can't play this file" in str(error)
    assert library.song(track["id"])["state"] == "unplayable"
    # Trying again is allowed; the file itself is never changed.
    assert resolve(tmp_path, track, resources)["source"] == str(path)
    assert path.is_file()
    close(resources)


def test_player_plays_local_songs_without_radio_and_keeps_them_in_the_saved_queue(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    _, path, track = library_song(tmp_path, "a.wav")
    worker, radio = FakeWorker(), FakeWorker()
    player = Playback(tmp_path, worker, radio, audio_factory=FakeAudio)
    player.playTracks([track], 0, source_label="Local Music")
    operation, payload = worker.requests[-1]
    assert operation == "resolve" and payload["videoId"] == track["videoId"]
    worker.succeeded.emit(len(worker.requests), {"kind": "local", "source": str(path), "headers": [], "videoId": track["videoId"]})
    assert player.playing and player.audio.loads[-1][0]["source"] == str(path)
    assert not player.videoAvailable
    # The last song is local, so autoplay has no YouTube Music song to start a radio from.
    assert radio.requests == []
    player.audio.ended.emit(False)
    assert radio.requests == []
    # Saved and restored queues keep local songs, with their local identity.
    player.enqueue([ONLINE])
    snapshot = player.queue.snapshot()
    restored = Playback(tmp_path / "restored", FakeWorker(), audio_factory=FakeAudio)
    restored.queue.restore(snapshot)
    assert [entry["track"].get("localId") for entry in restored.queue.all_entries][0] == track["localId"]
    restored.close()
    player.close()


def test_lyrics_are_not_requested_for_local_files(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    player, worker = Player(), FakeWorker()
    view = LyricView(Account(), player, tmp_path, worker)
    view.setActive(True)
    requests = len(worker.requests)
    player.currentTrack = {"videoId": "local:0123456789abcdef0123", "title": "Local"}
    player.changed.emit()
    assert view.localFile and len(worker.requests) == requests
    view.refresh()
    assert len(worker.requests) == requests
    player.currentTrack = {"videoId": "lmnopqrstuv"}
    player.changed.emit()
    assert not view.localFile and worker.requests[-1][0] == "lyrics"
    view.close()
