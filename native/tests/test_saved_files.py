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
    # Downloads stay inside Tubify by default; the chosen style and folder are remembered.
    assert view.downloadStyle == "tubify" and view.filesFolder.endswith("Tubify")
    view.setFilesFolder(folder.as_uri())
    view.setDownloadStyle("files")
    remembered = DownloadView(tmp_path / "other", fixture=True, settings_path=tmp_path / "settings.ini")
    assert remembered.filesFolder == str(folder) and remembered.downloadStyle == "files"
    saved, loop = [], QEventLoop()
    view.filesSaved.connect(lambda path: (saved.append(path), loop.quit()))
    view.setAccountAvailable(True)
    QTimer.singleShot(20000, loop.quit)
    loop.exec()
    assert saved == [str(folder)], view.message
    assert (folder / "Artist One" / "Album Name" / "01 Song 1.opus").is_file()
    # Switching to audio files moved the existing download out of Tubify instead of copying it.
    assert not list((tmp_path / "media" / "data" / "media" / "audio").iterdir())
    view.close()


def files(downloads):
    return sorted(path.name for path in (downloads.store.root / "audio").iterdir())


def test_audio_files_style_keeps_one_copy_and_plays_it(tmp_path):
    folder = tmp_path / "Music" / "Tubify"
    downloads, body = downloads_with(tmp_path, {IDS[0]: OPUS, IDS[1]: AAC})
    key = downloads.store.schedule(body, str(folder), move=True)
    downloads._drain()
    saved = folder / "Artist One" / "Album Name" / "01 Song 1.opus"
    assert saved.is_file() and files(downloads) == []
    assert downloads.store.media.ready(IDS[0]) == saved
    status = downloads.store.status()
    assert status["collectionStates"][key] == "complete" and status["bytes"] == 0 and status["fileBytes"] > 0
    # Retagging by another app changes the size; the file still plays.
    with saved.open("ab") as handle:
        handle.write(b"\0")
    assert downloads.store.media.ready(IDS[0]) == saved
    # A moved file needs repair, and is never deleted by cleanup or removal.
    other = folder / "Artist One" / "Album Name" / "02 Song 2.m4a"
    moved = other.rename(tmp_path / "moved.m4a")
    assert downloads.store.status()["collectionStates"][key] == "damaged"
    # A drive that comes back plays again without downloading anything.
    moved.rename(other)
    assert downloads.store.status()["collectionStates"][key] == "complete"
    moved = other.rename(tmp_path / "moved.m4a")
    downloads.store.remove(key)
    downloads.store._collect_garbage()
    assert saved.is_file() and moved.is_file()
    downloads.close()


def test_switching_styles_converts_existing_downloads(tmp_path):
    folder = tmp_path / "Music" / "Tubify"
    downloads, body = downloads_with(tmp_path, {IDS[0]: OPUS, IDS[1]: AAC})
    key = downloads.store.schedule(body)
    downloads._drain()
    private = files(downloads)
    assert len(private) == 2 and downloads.store.status()["fileBytes"] == 0
    # To audio files: the private copies become files, with nothing downloaded again.
    downloads.store.convert("files", str(folder))
    assert downloads.store.status()["next"] == "save"
    downloads._drain()
    saved = sorted(path.name for path in folder.rglob("*") if path.is_file())
    assert saved == ["01 Song 1.opus", "02 Song 2.m4a"] and files(downloads) == []
    assert downloads.store.status()["collectionStates"][key] == "complete"
    # Back into Tubify: each file is copied in, and the person's files stay.
    downloads.store.convert("tubify")
    assert downloads.store.status()["next"] == "internalize"
    downloads._drain()
    status = downloads.store.status()
    assert len(files(downloads)) == 2 and status["fileBytes"] == 0 and status["bytes"] > 0 and status["next"] is None
    assert sorted(path.name for path in folder.rglob("*") if path.is_file()) == saved
    assert downloads.store.media.ready(IDS[0]).is_relative_to(downloads.store.root)
    assert status["collectionStates"][key] == "complete"
    downloads.close()


def test_saving_one_item_as_files_in_tubify_style_keeps_its_offline_copy(tmp_path):
    folder = tmp_path / "Saved"
    downloads, body = downloads_with(tmp_path, {IDS[0]: OPUS})
    key = downloads.store.schedule(body)
    downloads._drain()
    downloads.store.request_files(key, str(folder))
    downloads._drain()
    assert len(files(downloads)) == 1 and len([path for path in folder.rglob("*") if path.is_file()]) == 1
    assert downloads.store.media.ready(IDS[0]).is_relative_to(downloads.store.root)
    downloads.close()


def test_switching_back_while_a_file_is_being_kept_keeps_tubifys_copy(tmp_path):
    folder = tmp_path / "Music" / "Tubify"
    downloads, body = downloads_with(tmp_path, {IDS[0]: OPUS})
    key = downloads.store.schedule(body, str(folder), move=True)
    saved = folder / "song.opus"
    saved.parent.mkdir(parents=True)
    saved.write_bytes((downloads.store.root / "audio" / f"{IDS[0]}.webm").read_bytes())
    # Switched back to Tubify between saving the file and switching to it: nothing changes hands.
    downloads.store.convert("tubify")
    assert not downloads.store.adopt(key, IDS[0], saved)
    assert files(downloads) == [f"{IDS[0]}.webm"] and downloads.store.media.ready(IDS[0]).is_relative_to(downloads.store.root)
    downloads.close()


def test_a_file_that_cannot_be_copied_back_keeps_playing_from_its_folder(tmp_path, monkeypatch):
    folder = tmp_path / "Music" / "Tubify"
    downloads, body = downloads_with(tmp_path, {IDS[0]: OPUS})
    key = downloads.store.schedule(body, str(folder), move=True)
    downloads._drain()
    downloads.store.convert("tubify")

    def unreadable(*args):
        raise PermissionError("unreadable")

    monkeypatch.setattr(shutil, "copyfile", unreadable)
    downloads._drain()
    status = downloads.store.status()
    assert status["collectionStates"][key] == "complete" and status["next"] is None
    assert not downloads.store.media.ready(IDS[0]).is_relative_to(downloads.store.root)


def saved_names(folder):
    return sorted(str(path.relative_to(folder)).replace("\\", "/") for path in folder.rglob("*") if path.is_file())


def test_deleting_one_downloads_audio_files_keeps_everything_else(tmp_path):
    folder = tmp_path / "Music" / "Tubify"
    downloads, body = downloads_with(tmp_path, {IDS[0]: OPUS, IDS[1]: AAC})
    key = downloads.store.schedule(body, str(folder))
    downloads._drain()
    mine = folder / "Notes.txt"
    mine.write_text("not Tubify's")
    assert downloads.store.status()["savedFiles"] == 2
    assert downloads.store.delete_files(key) == 2
    # Only Tubify's files and the folders they left empty go; the download stays in Tubify.
    assert saved_names(folder) == ["Notes.txt"] and folder.is_dir()
    status = downloads.store.status()
    assert status["savedFiles"] == 0 and status["collectionStates"][key] == "complete" and len(files(downloads)) == 2
    downloads.close()


def test_deleting_files_of_a_download_kept_as_files_removes_it_but_keeps_shared_songs(tmp_path):
    folder = tmp_path / "Music" / "Tubify"
    downloads, body = downloads_with(tmp_path, {IDS[0]: OPUS, IDS[1]: AAC}, kind="playlist")
    first = downloads.store.schedule(body, str(folder), move=True)
    second = downloads.store.schedule({**body, "id": "PLb", "title": "Second", "items": body["items"][:1]}, str(folder), move=True)
    downloads._drain()
    assert len(saved_names(folder)) == 2 and files(downloads) == []
    downloads.store.delete_files(first)
    # The first playlist is gone; the song the second still plays from stays.
    status = downloads.store.status()
    assert first not in status["collectionStates"] and status["collectionStates"][second] == "complete"
    assert len(saved_names(folder)) == 1 and downloads.store.media.ready(IDS[0]) is not None
    downloads.close()


def test_removing_a_download_can_delete_its_files_too(tmp_path):
    folder = tmp_path / "Saved"
    downloads, body = downloads_with(tmp_path, {IDS[0]: OPUS})
    key = downloads.store.schedule(body, str(folder))
    downloads._drain()
    downloads.store.remove(key)
    assert len(saved_names(folder)) == 1  # Removing alone leaves the files.
    key = downloads.store.schedule(body, str(folder))
    downloads._drain()
    downloads.store.remove(key, files=True)
    assert saved_names(folder) == [] and files(downloads) == []
    downloads.close()


def test_deleting_every_saved_file(tmp_path):
    folder = tmp_path / "Music" / "Tubify"
    downloads, body = downloads_with(tmp_path, {IDS[0]: OPUS, IDS[1]: AAC}, kind="playlist")
    kept = downloads.store.schedule(body, str(folder))
    moved = downloads.store.schedule({**body, "id": "PLb", "title": "Second", "items": body["items"][:1]}, str(folder), move=True)
    downloads._drain()
    mine = folder / "Mine" / "song.mp3"
    mine.parent.mkdir(parents=True)
    mine.write_bytes(b"mine")
    # The first song plays from the second playlist's file, which the playlist kept in Tubify still needs.
    assert downloads.store.delete_all_files() == 1
    status = downloads.store.status()
    assert saved_names(folder) == ["Artist One/Album Name/Song 1.opus", "Mine/song.mp3"] and status["savedFiles"] == 1
    # The download kept only as files is removed; the one in Tubify stays whole.
    assert moved not in status["collectionStates"] and status["collectionStates"][kept] == "complete"
    downloads.close()


def test_deleting_files_never_deletes_a_song_tubify_has_not_copied_back(tmp_path):
    folder = tmp_path / "Music" / "Tubify"
    downloads, body = downloads_with(tmp_path, {IDS[0]: OPUS})
    key = downloads.store.schedule(body, str(folder), move=True)
    downloads._drain()
    # Back in Tubify, but the copy back hasn't run yet: the file is the song's only copy.
    downloads.store.convert("tubify")
    assert downloads.store.delete_files(key) == 0
    assert downloads.store.delete_all_files() == 0
    assert len(saved_names(folder)) == 1 and downloads.store.media.ready(IDS[0]) is not None
    assert downloads.store.status()["collectionStates"][key] == "complete"
    # Once copied back, the file can go.
    downloads._drain()
    assert downloads.store.delete_all_files() == 1 and saved_names(folder) == []
    assert downloads.store.status()["collectionStates"][key] == "complete"
    downloads.close()
