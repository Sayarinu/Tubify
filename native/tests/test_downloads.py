import errno
from http.cookiejar import CookieJar
from pathlib import Path
from types import SimpleNamespace
import wave

import pytest

from youtube_music_native import downloads
from youtube_music_native.downloads import DownloadError, Downloads, DownloadStore, clean_track


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
    service.store.progress(identifier, 1, 2)
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
