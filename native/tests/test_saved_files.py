import shutil
import subprocess
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QCoreApplication

from tubify.downloads import saved_files
from tubify.downloads.downloads import Downloads, clean_track
from tubify.local import tags as tag_reader
from test_downloads import IDS
from test_local_library import png

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg creates the downloaded audio")


def encode(path, codec_options, extension_format):
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", *codec_options,
               "-f", extension_format, "-y", str(path)]
    if subprocess.run(command, timeout=60).returncode:
        pytest.skip("this ffmpeg build lacks the encoder")
    return path


def track(video_id, title, number=0):
    return clean_track({"videoId": video_id, "title": title, "artists": [{"id": "UCa", "name": "Artist: One"}, {"id": "UCb", "name": "Guest"}],
                        "artist": "Artist: One • Guest", "album": {"id": "MPREa", "name": "Album/Name"}, "duration": 1})


def downloads_with(tmp_path, sources, kind="album"):
    app = QCoreApplication.instance() or QCoreApplication([])
    downloads = Downloads(SimpleNamespace(session=None), tmp_path / "data", artwork_fetch=lambda url, folder: "")
    store = downloads.store
    audio = store.root / "audio"
    audio.mkdir(exist_ok=True)
    items = []
    for index, (video_id, (codec_options, container, extension)) in enumerate(sources.items()):
        path = encode(audio / f"{video_id}.{extension}", codec_options, container)
        store.media.publish(video_id, path)
        items.append(track(video_id, f"Song {index + 1}"))
    body = {"kind": kind, "id": "MPREa" if kind == "album" else "PLa", "title": "Album/Name", "thumbnail": "", "items": items}
    return downloads, body


OPUS = (["-c:a", "libopus"], "webm", "webm")
AAC = (["-c:a", "aac"], "ipod", "m4a")


def test_saving_copies_tagged_files_without_re_encoding(tmp_path):
    folder = tmp_path / "Music" / "Tubify"
    downloads, body = downloads_with(tmp_path, {IDS[0]: OPUS, IDS[1]: AAC})
    # Artwork cached by the download is embedded as the cover.
    art = downloads.store.root / "artwork" / "cover.image"
    art.parent.mkdir(exist_ok=True)
    art.write_bytes(png("purple", 64))
    body["items"][0]["localThumbnail"] = art.as_uri()
    key = downloads.store.schedule(body, str(folder))
    progress = []
    downloads.notify = progress.append
    downloads._drain()
    status = downloads.store.status()
    entry = status["collections"][0]
    assert entry["files"]["state"] == "saved" and entry["files"]["saved"] == 2 and entry["files"]["total"] == 2
    assert progress[-1] == {"collection": key, "filesSaved": str(folder), "done": True}
    first = folder / "Artist One" / "Album Name" / "01 Song 1.opus"
    second = folder / "Artist One" / "Album Name" / "02 Song 2.m4a"
    assert first.is_file() and second.is_file()
    values = tag_reader.read(first)
    assert (values["title"], values["artist"], values["album"], values["track"], values["codec"]) == ("Song 1", "Artist: One • Guest", "Album/Name", 1, "Opus")
    assert values["picture"] and tag_reader.read(second)["codec"] == "AAC"
    assert not any(path.name.startswith(".") for path in folder.rglob("*"))
    # Saving again finds the files already there and copies nothing twice.
    downloads.store.request_files(key, str(folder))
    downloads._drain()
    assert sorted(path.name for path in folder.rglob("*.*")) == ["01 Song 1.opus", "02 Song 2.m4a"]
    # Removing the download deletes only Tubify's offline copies; saved files stay.
    downloads.store.remove(key)
    assert first.is_file() and second.is_file()
    assert not list((downloads.store.root / "audio").iterdir())
    downloads.close()


def test_existing_files_are_never_overwritten(tmp_path):
    folder = tmp_path / "Saved"
    downloads, body = downloads_with(tmp_path, {IDS[0]: OPUS}, kind="playlist")
    existing = folder / "Artist One" / "Album Name" / "Song 1.opus"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"someone else's file")
    downloads.store.schedule(body, str(folder))
    downloads._drain()
    # Playlist songs have no album track number.
    assert existing.read_bytes() == b"someone else's file"
    assert (folder / "Artist One" / "Album Name" / "Song 1 (2).opus").is_file()
    downloads.close()


def test_a_folder_that_cannot_be_written_fails_with_a_retry(tmp_path):
    blocked = tmp_path / "blocked"
    blocked.write_text("a file where the folder should be")
    downloads, body = downloads_with(tmp_path, {IDS[0]: OPUS})
    key = downloads.store.schedule(body, str(blocked))
    downloads._drain()
    files = downloads.store.status()["collections"][0]["files"]
    assert files["state"] == "failed" and "Choose another folder" in files["error"]
    downloads.store.request_files(key, str(tmp_path / "ok"))
    downloads._drain()
    assert downloads.store.status()["collections"][0]["files"]["state"] == "saved"
    downloads.close()


def test_cancel_and_retry_include_saving(tmp_path):
    downloads, body = downloads_with(tmp_path, {IDS[0]: OPUS})
    key = downloads.store.schedule(body, str(tmp_path / "Saved"))
    downloads.store.cancel(key)
    assert downloads.store.export(key)["state"] == "cancelled"
    assert downloads.store.next_export() is None
    downloads.store.retry(key)
    assert downloads.store.export(key)["state"] == "pending"
    # The queue first finishes the collection (its cover), then saves its files.
    assert downloads.store.status()["next"] in {"finish", "save"}
    downloads._drain()
    assert downloads.store.export(key)["state"] == "saved" and downloads.store.status()["next"] is None
    downloads.close()


def test_names_are_valid_everywhere():
    assert saved_files.safe_name('A/B\\C:D*E?F"G<H>I|J', "x") == "A B C D E F G H I J"
    assert saved_files.safe_name("CON", "Song") == "Song CON"
    assert saved_files.safe_name("  trailing dots... ", "x") == "trailing dots"
    assert saved_files.safe_name("", "Unknown artist") == "Unknown artist"
    single = clean_track({"videoId": IDS[0], "title": "Single", "artist": "Solo"})
    assert str(saved_files.relative_path(single, 0, "opus")).replace("\\", "/") == "Solo/Single.opus"


def test_view_saves_files_through_the_worker_and_announces_the_folder(tmp_path):
    from PySide6.QtCore import QEventLoop, QTimer
    from tubify.downloads.download_view import DownloadView

    app = QCoreApplication.instance() or QCoreApplication([])
    folder = tmp_path / "Saved"
    downloads, body = downloads_with(tmp_path / "media", {IDS[0]: OPUS})
    downloads.store.schedule(body, str(folder))
    downloads.close()
    view = DownloadView(tmp_path / "media" / "data", settings_path=tmp_path / "settings.ini")
    # The option is off by default and remembered once chosen.
    assert not view.filesEnabled and view.filesFolder.endswith("Tubify")
    view.setFilesEnabled(True)
    view.setFilesFolder(folder.as_uri())
    assert DownloadView(tmp_path / "other", fixture=True, settings_path=tmp_path / "settings.ini").filesFolder == str(folder)
    saved, loop = [], QEventLoop()
    view.filesSaved.connect(lambda path: (saved.append(path), loop.quit()))
    view.setAccountAvailable(True)
    QTimer.singleShot(20000, loop.quit)
    loop.exec()
    assert saved == [str(folder)], view.message
    assert (folder / "Artist One" / "Album Name" / "01 Song 1.opus").is_file()
    view.close()
