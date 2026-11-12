import errno
from http.cookiejar import CookieJar
from pathlib import Path
from types import SimpleNamespace
import wave

import pytest

from tubify.downloads import downloads
from tubify.downloads.downloads import DownloadBlocked, DownloadError, Downloads, DownloadStore, clean_track


IDS = ["abcdefghijk", "lmnopqrstuv", "zyxwvutsrqp"]


def song(video_id, **extra):
    return clean_track({"videoId": video_id, "kind": "song", "title": "Fixture song", "duration": 1, **extra})


def body(identifier, videos):
    return {"kind": "playlist", "id": identifier, "title": "Fixture playlist", "items": [song(video_id) for video_id in videos], "thumbnail": ""}


def write_wave(path, seconds=1):
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"\0\0" * 16000 * seconds)


class Extractor:
    def __init__(self, options, owner):
        self.options, self.owner = options, owner
        self.cookiejar = CookieJar()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def extract_info(self, url, download):
        video_id = url.rsplit("=", 1)[1]
        self.owner.calls.append(video_id)
        if self.owner.error:
            raise self.owner.error
        path = Path(self.options["outtmpl"].replace("%(id)s", video_id).replace("%(ext)s", "wav"))
        self.owner.saw_partial |= path.with_suffix(".wav.part").is_file()
        if self.owner.invalid:
            path.write_bytes(b"invalid audio")
        else:
            write_wave(path)
        for hook in self.options["progress_hooks"]:
            hook({"downloaded_bytes": path.stat().st_size, "total_bytes": path.stat().st_size})
        return {"id": video_id, "ext": "wav", "vcodec": "none"}


class ExtractorFactory:
    def __init__(self):
        self.calls, self.error, self.invalid, self.saw_partial = [], None, False, False

    def __call__(self, options):
        assert options["continuedl"]
        return Extractor(options, self)


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.setattr(downloads, "extractor_options", lambda directory: {})
    factory = ExtractorFactory()
    auth = SimpleNamespace(session=SimpleNamespace(cookie_jar=CookieJar))
    service = Downloads(auth, tmp_path, extractor_factory=factory, artwork_fetch=lambda url, folder: "")
    yield service, factory
    service.close()


def test_duplicates_share_audio_and_removal_retains_other_collections(service):
    service, factory = service
    first = service.store.schedule(body("PLfirst", [IDS[0], IDS[0]]))
    service.run(first)
    shared = service.store.media.ready(IDS[0])
    assert len(service.store.collection(first)["items"]) == 2
    assert factory.calls == [IDS[0]]
    second = service.store.schedule(body("PLsecond", [IDS[0], IDS[1]]))
    service.run(second)
    assert factory.calls == IDS[:2]
    service.store.remove(first)
    assert shared.is_file() and service.store.media.ready(IDS[0])
    service.store.remove(second)
    assert not shared.exists()
    assert service.store.status()["bytes"] == 0


def test_interrupted_job_recovers_and_keeps_completed_files_and_partial_media(service, tmp_path):
    service, factory = service
    identifier = service.store.schedule(body("PLresume", IDS[:2]))
    first_audio = service.store.root / "audio" / (IDS[0] + ".wav")
    first_audio.parent.mkdir()
    write_wave(first_audio)
    service.store.media.publish(IDS[0], first_audio)
    staging = service.store.root / "staging"
    staging.mkdir()
    partial = staging / (IDS[1] + ".wav.part")
    partial.write_bytes(b"partial")
    assert service.store.start_song(IDS[1])
    restarted = DownloadStore(tmp_path)
    restarted.recover()
    assert restarted.state(identifier) == "queued" and first_audio.is_file() and partial.is_file()
    restarted.close()
    service.run(identifier)
    assert factory.calls == [IDS[1]] and factory.saw_partial
    assert service.store.status()["collections"][0]["state"] == "complete"


def test_failed_refresh_retains_previous_snapshot_until_replacement_completes(service):
    service, factory = service
    identifier = service.store.schedule(body("PLrefresh", IDS[:1]))
    service.run(identifier)
    old_file = service.store.media.ready(IDS[0])
    service.store.schedule(body("PLrefresh", IDS[1:2]))
    factory.error = OSError(errno.ENOSPC, "private provider detail")
    with pytest.raises(DownloadError, match="disk is full"):
        service.run(identifier)
    assert old_file.is_file()
    factory.error = None
    service.store.retry(identifier)
    service.run(identifier)
    assert not old_file.exists() and service.store.media.ready(IDS[1])


def test_invalid_audio_is_not_published_and_retry_redownloads_it(service):
    service, factory = service
    identifier = service.store.schedule(body("PLinvalid", IDS[:1]))
    factory.invalid = True
    with pytest.raises(DownloadError, match="validation"):
        service.run(identifier)
    assert not service.store.media.ready(IDS[0])
    assert not list((service.store.root / "staging").glob("*.wav"))
    factory.invalid = False
    service.store.retry(identifier)
    service.run(identifier)
    assert service.store.media.ready(IDS[0])


def test_cancelled_job_and_corrupt_asset_preserve_other_completed_media(service):
    service, factory = service
    identifier = service.store.schedule(body("PLcancel", IDS[:2]))
    service.store.cancel(identifier)
    with pytest.raises(DownloadError, match="cancelled"):
        service.run(identifier)
    assert not factory.calls
    service.store.retry(identifier)
    service.run(identifier)
    service.store.media.ready(IDS[1]).write_bytes(b"corrupt")
    status = service.store.status()["collections"][0]
    assert status["state"] == "damaged" and status["ready"] == 1
    assert service.store.media.ready(IDS[0])


def test_private_source_fields_are_never_saved_and_stale_deletion_cannot_remove_new_audio(service):
    service, factory = service
    raw = {"kind": "song", "id": IDS[0], "title": "Fixture", "source": "https://private.invalid/signed", "headers": {"Cookie": "private-cookie"}}
    identifier = service.schedule(raw)
    service.run(identifier)
    assert "private.invalid" not in str(service.store.collection(identifier))
    assert "private-cookie" not in str(service.store.collection(identifier))
    path = service.store.media.ready(IDS[0])
    service.store.db.execute("INSERT INTO pending_delete VALUES (?)", (str(path),))
    service.store.db.commit()
    service.store.recover()
    assert path.is_file() and service.store.media.ready(IDS[0])


def test_collection_snapshots_preserve_order_and_duplicate_mutation_ids(service):
    service, factory = service
    original = [{"videoId": IDS[0], "title": "First", "setVideoId": "entry-one"}, {"videoId": IDS[0], "title": "Duplicate", "setVideoId": "entry-two"}]
    client = SimpleNamespace(get_playlist=lambda identifier, limit: {"title": "Snapshot", "tracks": list(original)})
    service.auth.catalog = lambda: client
    identifier = service.schedule({"kind": "playlist", "id": "PLsnapshot"})
    original.reverse()
    snapshot = service.store.collection(identifier)
    assert [track["setVideoId"] for track in snapshot["items"]] == ["entry-one", "entry-two"]
    service.run(identifier)
    assert factory.calls == IDS[:1]


def test_format_change_removes_obsolete_parts_and_downloads_survive_provider_removal(service):
    service, factory = service
    identifier = service.store.schedule(body("PLformat", IDS[:1]))
    staging = service.store.root / "staging"
    staging.mkdir()
    obsolete = staging / (IDS[0] + ".webm.part")
    obsolete.write_bytes(b"old format")
    service.run(identifier)
    assert not obsolete.exists()
    snapshot = service.store.collection(identifier)
    snapshot["items"][0]["available"] = False
    service.store.update_body(identifier, snapshot)
    assert service.store.view(identifier)["items"][0]["available"]
    service.store.retry(identifier)
    service.run(identifier)
    assert factory.calls == IDS[:1]


def test_download_saves_largest_original_and_variants_for_offline_covers(service):
    from PySide6.QtGui import QImage
    service, factory = service
    variants = [{"url": f"https://fixture.invalid/{size}.png", "width": size, "height": size} for size in (60, 300, 1200)]
    fetched = []
    def artwork(url, folder):
        fetched.append(url)
        folder.mkdir(exist_ok=True)
        path = folder / "original.png"
        image = QImage(1200, 1200, QImage.Format.Format_RGB32)
        image.fill(0xFF223344)
        assert image.save(str(path))
        return path.as_uri()
    service.artwork_fetch = artwork
    identifier = service.schedule({"kind": "song", "id": IDS[0], "title": "Fixture", "thumbnail": variants[1]["url"], "artworkVariants": variants})
    service.run(identifier)
    snapshot = service.store.view(identifier)
    assert snapshot["items"][0]["artworkVariants"] == variants
    assert snapshot["items"][0]["largeThumbnail"] == variants[-1]["url"]
    assert snapshot["items"][0]["thumbnail"].startswith("file:")
    assert fetched and set(fetched) == {variants[-1]["url"]}
    assert factory.calls == [IDS[0]]


def test_run_queue_downloads_every_queued_collection_in_one_call(service):
    service, factory = service
    notified = []
    service.notify = notified.append
    first = service.store.schedule(body("PLfirst", IDS[:1]))
    broken = service.store.schedule(body("PLbroken", IDS[1:2]))
    last = service.store.schedule(body("PLlast", IDS[2:]))

    class Failing(Extractor):
        def extract_info(self, url, download):
            if url.endswith(IDS[1]):
                self.owner.calls.append(IDS[1])
                raise RuntimeError("provider detail")
            return super().extract_info(url, download)

    service.extractor_factory = lambda options: Failing(options, factory)
    service.run_queue(first)
    states = {entry["key"]: entry["state"] for entry in service.store.status()["collections"]}
    # One failing collection is marked and the queue carries on to the next one.
    assert states == {first: "complete", broken: "failed", last: "complete"}
    assert factory.calls == IDS
    # Each finished song is announced so the view can refresh the collections that hold it.
    assert [value["videoId"] for value in notified if value.get("done") and "videoId" in value] == [IDS[0], IDS[2]]


def test_run_queue_stops_when_the_disk_is_full(service):
    service, factory = service
    first = service.store.schedule(body("PLfirst", IDS[:1]))
    second = service.store.schedule(body("PLsecond", IDS[1:2]))
    factory.error = OSError(errno.ENOSPC, "private provider detail")
    with pytest.raises(DownloadError, match="disk is full"):
        service.run_queue(first)
    assert service.store.state(second) == "queued" and factory.calls == [IDS[0]]


def test_run_queue_stops_when_the_account_needs_reconnecting(service):
    service, factory = service
    first = service.store.schedule(body("PLfirst", IDS[:1]))
    second = service.store.schedule(body("PLsecond", IDS[1:2]))
    service.auth.session, service.auth.restore = None, lambda: None
    with pytest.raises(DownloadBlocked, match="Reconnect"):
        service.run_queue(first)
    assert service.store.state(first) == "failed" and service.store.state(second) == "queued"


def test_run_queue_continues_after_an_ordinary_download_error_whatever_its_wording(service, monkeypatch):
    service, factory = service
    first = service.store.schedule(body("PLfirst", IDS[:1]))
    second = service.store.schedule(body("PLsecond", IDS[1:2]))
    real_download = service._download

    def download(video_id, track):
        if video_id == IDS[0]:
            service.store.start_song(video_id)
            service.store.song_failed(video_id, "Reconnect wording from an ordinary failure.")
            raise DownloadError("Reconnect wording from an ordinary failure.")
        return real_download(video_id, track)

    monkeypatch.setattr(service, "_download", download)
    service.run_queue()
    assert service.store.state(first) == "failed" and service.store.state(second) == "complete"


def test_failed_artwork_write_leaves_no_temporary_file(tmp_path, monkeypatch):
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    from PySide6.QtGui import QImage
    import requests

    image = QImage(2, 2, QImage.Format_RGB32)
    image.fill(0)
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "PNG")

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def raise_for_status(self):
            pass

        def iter_content(self, size):
            yield bytes(data)

    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: Response())
    monkeypatch.setattr("os.replace", lambda *args: (_ for _ in ()).throw(OSError(errno.EACCES, "denied")))
    folder = tmp_path / "artwork"
    assert downloads.cache_artwork("https://example.invalid/art.png", folder) == ""
    assert not list(folder.iterdir())


def test_schedule_all_queues_new_playlists_once_and_skips_failures(service):
    service, factory = service
    done = service.store.schedule(body("PLdone", IDS[:1]))
    service.run(done)
    requested = []

    def get_playlist(identifier, limit=None):
        requested.append(identifier)
        if identifier == "PLbroken":
            raise KeyError("private provider detail")
        return {"title": "Fixture " + identifier, "thumbnails": [], "tracks": [{"videoId": IDS[1], "title": "Song", "duration_seconds": 1}]}

    service.auth.catalog = lambda: SimpleNamespace(get_playlist=get_playlist)
    notified = []
    service.notify = notified.append
    playlists = [{"id": "PLdone"}, {"id": "PLnew", "title": "New"}, {"id": "PLbroken"}, "invalid"]
    assert service.schedule_all(playlists) == {"scheduled": 1, "failed": 1}
    assert requested == ["PLnew", "PLbroken"] and notified[-1] == {"scheduled": 1, "failed": 1}
    assert service.store.state("playlist:PLnew") == "queued"
    # Running it again does not plan the queued playlist a second time.
    requested.clear()
    assert service.schedule_all(playlists) == {"scheduled": 0, "failed": 1} and requested == ["PLbroken"]


def test_a_song_shared_by_playlists_is_queued_and_downloaded_once(service):
    service, factory = service
    first = service.store.schedule(body("PLfirst", IDS[:2]))
    second = service.store.schedule(body("PLsecond", IDS[1:]))
    assert service.store.db.execute("SELECT count(*) FROM song_jobs").fetchone()[0] == 3
    service.run_queue()
    assert sorted(factory.calls) == sorted(IDS) and len(factory.calls) == 3
    status = service.store.status()
    assert status["collectionStates"] == {first: "complete", second: "complete"}
    assert sorted(song["videoId"] for song in status["songs"]) == sorted(IDS)
    assert all(song["downloadState"] == "ready" for song in status["songs"])


def test_a_collection_counts_as_downloaded_without_its_unavailable_songs(service):
    service, factory = service
    value = body("PLgaps", IDS[:2])
    value["items"][1]["available"] = False
    identifier = service.store.schedule(value)
    service.run_queue()
    entry = service.store.status()["collections"][0]
    assert entry["state"] == "complete" and entry["ready"] == 1 and "1 unavailable" in entry["error"]
    assert factory.calls == IDS[:1]
    assert [song["videoId"] for song in service.store.status()["songs"]] == IDS[:1]


def test_a_collection_with_every_song_already_downloaded_is_downloaded(service):
    service, factory = service
    service.store.schedule(body("PLfirst", IDS[:2]))
    service.run_queue()
    second = service.store.schedule(body("PLsecond", IDS[:2]))
    assert service.store.state(second) == "complete"
    service.run_queue()
    assert len(factory.calls) == 2


def test_cancelling_one_playlist_keeps_songs_another_still_wants(service):
    service, factory = service
    first = service.store.schedule(body("PLfirst", IDS[:2]))
    second = service.store.schedule(body("PLsecond", IDS[1:2]))
    service.store.cancel(first)
    assert service.store.state(first) == "cancelled" and service.store.state(second) == "queued"
    service.run_queue()
    assert factory.calls == [IDS[1]]
    assert service.store.state(second) == "complete" and service.store.state(first) == "cancelled"
    service.store.retry(first)
    service.run_queue()
    assert factory.calls == [IDS[1], IDS[0]] and service.store.state(first) == "complete"


def test_old_collection_jobs_become_song_jobs(tmp_path, service):
    import json
    import sqlite3
    import time

    service, factory = service
    service.close()
    db = sqlite3.connect(tmp_path / "media" / "media.sqlite3")
    db.executescript("""DROP TABLE collection_jobs; DROP TABLE song_jobs;
        CREATE TABLE download_jobs (collection_id TEXT PRIMARY KEY REFERENCES collections(id) ON DELETE CASCADE,
            state TEXT NOT NULL, completed INTEGER NOT NULL, total INTEGER NOT NULL,
            fraction REAL NOT NULL, error TEXT NOT NULL, created REAL NOT NULL);""")
    for name, state in (("PLqueued", "queued"), ("PLfailed", "failed"), ("PLcancelled", "cancelled")):
        value = body(name, IDS[:1] if name == "PLqueued" else IDS[1:2] if name == "PLfailed" else IDS[2:])
        db.execute("INSERT INTO collections VALUES (?, ?)", ("playlist:" + name, json.dumps(value)))
        db.execute("INSERT INTO download_jobs VALUES (?, ?, 0, 1, 0, ?, ?)", ("playlist:" + name, state, "Old failure" if state == "failed" else "", time.time()))
        db.execute("INSERT INTO media_refs VALUES (?, ?)", ("playlist:" + name, value["items"][0]["videoId"]))
    db.commit()
    db.close()
    migrated = Downloads(service.auth, tmp_path, extractor_factory=factory, artwork_fetch=lambda url, folder: "")
    try:
        states = migrated.store.status()["collectionStates"]
        assert states == {"playlist:PLqueued": "queued", "playlist:PLfailed": "failed", "playlist:PLcancelled": "cancelled"}
        migrated.run_queue()
        assert factory.calls == IDS[:1] and migrated.store.state("playlist:PLqueued") == "complete"
    finally:
        migrated.close()
