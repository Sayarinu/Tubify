import os
from pathlib import Path
import shutil
import subprocess
import time
from types import SimpleNamespace

import pytest
from mutagen.id3 import APIC, TALB, TIT2, TPE1, TRCK
from mutagen.wave import WAVE
from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QColor, QImage

from tubify.local import tags as tag_reader
from tubify.local.library import LibraryError, LocalLibrary, SETTLE_SECONDS
from tubify.worker import handle
from test_downloads import write_wave

LATER = time.time() + 3600


def png(color="red", size=32):
    image = QImage(size, size, QImage.Format.Format_RGB32)
    image.fill(QColor(color))
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(data.data())


def song(path, title="", artist="", album="", track=0, picture=b"", seconds=1):
    """A WAV file with ID3 tags, like files from other downloaders and rippers."""
    path.parent.mkdir(parents=True, exist_ok=True)
    write_wave(path, seconds)
    audio = WAVE(str(path))
    audio.add_tags()
    if title:
        audio.tags.add(TIT2(encoding=3, text=title))
    if artist:
        audio.tags.add(TPE1(encoding=3, text=artist))
    if album:
        audio.tags.add(TALB(encoding=3, text=album))
    if track:
        audio.tags.add(TRCK(encoding=3, text=f"{track}/12"))
    if picture:
        audio.tags.add(APIC(encoding=3, mime="image/png", type=3, desc="Cover", data=picture))
    audio.save()
    return path


def snapshot(folder):
    return {path: (path.stat().st_size, path.read_bytes()) for path in sorted(Path(folder).rglob("*")) if path.is_file()}


@pytest.fixture
def library(tmp_path):
    value = LocalLibrary(tmp_path / "data")
    yield value
    value.close()


def by_title(result):
    return {entry["title"]: entry for entry in result["songs"]}


def test_scan_reads_tags_and_artwork_and_never_changes_files(tmp_path, library):
    music = tmp_path / "Music"
    song(music / "Artist" / "Album" / "01.wav", "First", "Artist", "Album", 1, png("red"))
    song(music / "Artist" / "Album" / "02.wav", "Second", "Artist", "Album", 2, png("red"))
    before = snapshot(music)
    library.add_folder(music)
    result = library.scan(now=LATER)
    assert result["added"] == 2 and result["missing"] == 0
    songs = by_title(result)
    first = songs["First"]
    assert (first["artist"], first["albumName"], first["track"], first["codec"]) == ("Artist", "Album", 1, "WAV")
    assert first["album"] == {"id": "", "name": "Album"}
    assert first["local"] and first["available"] and first["tagsReadable"] and first["localId"].startswith("local:")
    assert first["duration"] == pytest.approx(1, abs=.05)
    # The album's shared cover is cached once, inside Tubify's data.
    assert first["thumbnail"] == songs["Second"]["thumbnail"] and first["thumbnail"].startswith("file://")
    assert len(list(library.artwork.iterdir())) == 1
    assert snapshot(music) == before


def test_rescans_are_incremental_and_never_duplicate(tmp_path, library):
    music = tmp_path / "Music"
    song(music / "a.wav", "A", "Artist")
    library.add_folder(music)
    first = library.scan(now=LATER)
    ids = {entry["id"] for entry in first["songs"]}
    second = library.scan(now=LATER)
    assert (second["added"], second["updated"]) == (0, 0)
    assert {entry["id"] for entry in second["songs"]} == ids
    # Adding the same folder again, or a folder inside it, lists nothing twice.
    library.add_folder(music)
    library.add_folder(music / ".")
    (music / "Inner").mkdir()
    song(music / "Inner" / "b.wav", "B", "Artist")
    library.add_folder(music / "Inner")
    result = library.scan(now=LATER)
    assert sorted(entry["title"] for entry in result["songs"]) == ["A", "B"]
    assert len(result["folders"]) == 2
    # Only changed songs come back when asked for changes since a revision.
    revision = result["revision"]
    assert library.changes(revision)["songs"] == []
    song(music / "a.wav", "A renamed", "Artist")
    os.utime(music / "a.wav", (time.time() - 60, time.time() - 60))
    later = library.scan(now=LATER)
    assert later["updated"] == 1
    assert [entry["title"] for entry in library.changes(revision)["songs"]] == ["A renamed"]


@pytest.mark.skipif(os.name == "nt", reason="Hard links need administrator rights on some Windows runners")
def test_hard_links_and_other_downloaders_names(tmp_path, library):
    music = tmp_path / "Music"
    original = song(music / "Artist — Title [dQw4w9WgXcQ].wav", "Title", "Artist")
    os.link(original, music / "copy.wav")
    song(music / "Untagged track.wav")
    library.add_folder(music)
    result = library.scan(now=LATER)
    titles = sorted(entry["title"] for entry in result["songs"])
    # The file name is never trusted as a YouTube identity; it is only a title fallback.
    assert titles == ["Title", "Untagged track"]
    assert all("videoId" not in entry for entry in result["songs"])


def test_partial_and_hidden_files_are_skipped_until_settled(tmp_path, library):
    music = tmp_path / "Music"
    song(music / "done.wav", "Done")
    write_wave(music / "song.m4a.part")
    write_wave(music / "song.wav.ytdl")
    write_wave(music / ".hidden.wav")
    song(music / ".staging-1234" / "staged.wav", "Staged")
    song(music / "Digital Audio Manager" / ".previous-99" / "old.wav", "Old")
    fresh = song(music / "fresh.wav", "Fresh")
    library.add_folder(music)
    now = fresh.stat().st_mtime + SETTLE_SECONDS / 2
    os.utime(music / "done.wav", (now - 60, now - 60))
    result = library.scan(now=now)
    assert [entry["title"] for entry in result["songs"]] == ["Done"]
    assert result["waiting"] == 1
    assert by_title(library.scan(now=LATER))["Fresh"]["available"]


def test_broken_tags_and_missing_artwork_fall_back(tmp_path, library):
    music = tmp_path / "Music"
    broken = music / "Broken file.mp3"
    broken.parent.mkdir(parents=True)
    broken.write_bytes(b"ID3\x04\x00\x00\x00\x00\x00\x10not really audio" * 4)
    song(music / "Plain.wav", "Plain")
    library.add_folder(music)
    songs = by_title(library.scan(now=LATER))
    assert songs["Broken file"]["tagsReadable"] is False
    assert songs["Broken file"]["thumbnail"] == "" and songs["Plain"]["thumbnail"] == ""


def test_folder_art_and_sidecars(tmp_path, library):
    music = tmp_path / "Music"
    song(music / "Album" / "one.wav", "One")
    (music / "Album" / "Cover.JPG").write_bytes(png("blue"))
    song(music / "Singles" / "two.wav", "Two")
    (music / "Singles" / "two.jpg").write_bytes(png("green"))
    song(music / "Singles" / "three.wav", "Three", picture=png("yellow"))
    library.add_folder(music)
    songs = by_title(library.scan(now=LATER))
    thumbnails = {title: songs[title]["thumbnail"] for title in ("One", "Two", "Three")}
    assert all(thumbnails.values()) and len(set(thumbnails.values())) == 3


def test_disconnected_folder_keeps_songs_and_missing_files_relink(tmp_path, library):
    drive = tmp_path / "Drive"
    song(drive / "a.wav", "A", "Artist", "Album")
    song(drive / "b.wav", "B", "Artist", "Album", seconds=2)
    library.add_folder(drive)
    ids = {entry["title"]: entry["id"] for entry in library.scan(now=LATER)["songs"]}
    unplugged = tmp_path / "Unplugged"
    drive.rename(unplugged)
    result = library.scan(now=LATER)
    assert result["offline"] == 1 and result["folders"][0]["state"] == "offline"
    assert {entry["state"] for entry in result["songs"]} == {"offline"}
    assert len(result["songs"]) == 2
    # An empty mount point is a disconnected drive, not a deleted library.
    drive.mkdir()
    result = library.scan(now=LATER)
    assert {entry["state"] for entry in result["songs"]} == {"offline"}
    drive.rmdir()
    unplugged.rename(drive)
    result = library.scan(now=LATER)
    assert {entry["state"] for entry in result["songs"]} == {"ready"}
    assert result["folders"][0]["state"] == "ready"
    # A moved file keeps its id; a deleted one is marked missing, not dropped.
    (drive / "Moved").mkdir()
    (drive / "a.wav").rename(drive / "Moved" / "a.wav")
    (drive / "b.wav").unlink()
    songs = by_title(library.scan(now=LATER))
    assert songs["A"]["id"] == ids["A"] and songs["A"]["available"] and songs["A"]["path"].endswith("a.wav")
    assert songs["B"]["state"] == "missing" and not songs["B"]["available"]
    assert library.forget_missing() == 1
    assert list(by_title(library.changes())) == ["A"]


def test_removal_only_removes_references(tmp_path, library):
    music, other = tmp_path / "Music", tmp_path / "Other"
    song(music / "keep.wav", "Keep")
    song(music / "hide.wav", "Hide")
    song(music / "Inner" / "inner.wav", "Inner")
    song(other / "x.wav", "X")
    before = snapshot(tmp_path / "Music") | snapshot(other)
    outer = library.add_folder(music)
    library.add_folder(music / "Inner")
    other_id = library.add_folder(other)
    songs = by_title(library.scan(now=LATER))
    library.remove_songs([songs["Hide"]["id"]])
    assert "Hide" not in by_title(library.scan(now=LATER))
    revision = library.revision()
    library.remove_folder(other_id)
    changes = library.changes(revision)
    assert changes["removed"] == [songs["X"]["id"]]
    library.remove_folder(outer)
    # The inner folder is still chosen, so its song stays.
    assert list(by_title(library.changes())) == ["Inner"]
    assert snapshot(tmp_path / "Music") | snapshot(other) == before


def test_folder_errors(tmp_path, library):
    with pytest.raises(LibraryError):
        library.add_folder(tmp_path / "nowhere")
    file = song(tmp_path / "file.wav")
    with pytest.raises(LibraryError):
        library.add_folder(file)
    with pytest.raises(LibraryError):
        library.add_folder(tmp_path / "data")


def test_worker_operations_need_no_account(tmp_path):
    music = tmp_path / "Music"
    song(music / "a.wav", "A")
    os.utime(music / "a.wav", (time.time() - 60, time.time() - 60))

    def forbidden(*args):
        raise AssertionError("Local music must not touch the account")
    service = SimpleNamespace(catalog=forbidden, restore=forbidden, session=None)
    resources, updates = {}, []
    data = str(tmp_path / "data")
    added = handle(service, {"operation": "local_add_folder", "payload": {"data_dir": data, "path": str(music)}}, resources)
    scanned = handle(service, {"operation": "local_scan", "payload": {"data_dir": data}}, resources, updates.append)
    assert [entry["title"] for entry in scanned["songs"]] == ["A"]
    assert updates[-1]["phase"] == "done"
    changes = handle(service, {"operation": "local_changes", "payload": {"data_dir": data, "since": scanned["revision"]}}, resources)
    assert changes["songs"] == [] and not changes["full"]
    handle(service, {"operation": "local_remove_folder", "payload": {"data_dir": data, "id": added["folder"]}}, resources)
    assert (music / "a.wav").is_file()
    resources[("local", str((tmp_path / "data").resolve()))].close()


def test_large_library_rescan_is_incremental(tmp_path, library):
    music = tmp_path / "Music"
    template = song(music / "template.wav", "Template", "Artist", "Album")
    for index in range(1500):
        shutil.copyfile(template, music / f"{index:04}.wav")
    library.add_folder(music)
    updates = []
    first = library.scan(progress=updates.append, now=LATER)
    assert first["added"] == 1501
    assert updates[-1] == {"folder": 1, "phase": "done", "scanned": 1501, "total": 1501, "revision": first["revision"]}
    started = time.monotonic()
    second = library.scan(now=LATER)
    assert (second["added"], second["updated"]) == (0, 0)
    assert time.monotonic() - started < 10


FFMPEG_FORMATS = [("flac", "FLAC"), ("mp3", "MP3"), ("m4a", "AAC"), ("ogg", "Vorbis"), ("opus", "Opus"), ("mka", "PCM_S16LE")]


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg creates the encoded fixtures")
@pytest.mark.parametrize("extension,codec", FFMPEG_FORMATS)
def test_common_formats_read_tags(tmp_path, extension, codec):
    path = tmp_path / ("tone." + extension)
    encoder = {"ogg": ["-c:a", "libvorbis"], "opus": ["-c:a", "libopus"], "mka": ["-c:a", "pcm_s16le"]}.get(extension, [])
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", *encoder,
               "-metadata", "title=Tone", "-metadata", "artist=Generator", "-metadata", "album=Signals", "-metadata", "track=4",
               "-y", str(path)]
    if subprocess.run(command, timeout=60).returncode:
        pytest.skip("this ffmpeg build lacks the encoder")
    values = tag_reader.read(path)
    assert (values["title"], values["artist"], values["album"], values["track"]) == ("Tone", "Generator", "Signals", 4)
    assert values["codec"] == codec and values["duration"] == pytest.approx(2, abs=.2)
