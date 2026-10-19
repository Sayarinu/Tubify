from types import SimpleNamespace
import pytest

from PySide6.QtCore import QObject, Signal

from youtube_music_native.downloads import DownloadStore
from youtube_music_native.worker import handle
from test_browse import setup
from test_downloads import IDS, body, write_wave
from test_playback import FakeAudio, FakeWorker
from youtube_music_native.playback import Playback
from youtube_music_native.media import MediaFiles
from youtube_music_native.sources import Sources


def test_download_lookup_and_repair_states_work_without_authentication(tmp_path):
    store = DownloadStore(tmp_path)
    key = store.schedule(body("PLfixture", [IDS[0], IDS[0]]))
    folder = store.root / "audio"
    folder.mkdir()
    audio = folder / (IDS[0] + ".wav")
    write_wave(audio)
    store.media.publish(IDS[0], audio)
    store.progress(key, 2, 2, state="complete")
    store.close()
    def forbidden():
        raise AssertionError("Local collection browsing must not touch authentication or HTTP")
    resources = {}
    service = SimpleNamespace(catalog=forbidden)
    request = {"operation": "downloads_lookup", "payload": {"data_dir": str(tmp_path), "kind": "playlist", "id": "PLfixture"}}
    result = handle(service, request, resources)
    assert result["downloadKey"] == key and len(result["items"]) == 2
    assert all(track["downloadState"] == "ready" for track in result["items"])
    downloads = resources[("downloads", str(tmp_path.resolve()))]
    assert downloads.store.status()["trackStates"][IDS[0]] == "ready"
    audio.unlink()
    assert downloads.store.status()["collections"][0]["state"] == "damaged"
    assert downloads.store.lookup("playlist", "PLfixture")["items"][0]["downloadState"] == "missing"
    assert downloads.store.lookup("album", "missing") == {}
    downloads.close()


class Downloads(QObject):
    collectionFound = Signal(int, dict)
    collectionReady = Signal(dict)
    playRequested = Signal(dict, bool)

    def __init__(self):
        super().__init__()
        self.requests = []

    def lookup(self, kind, identifier):
        self.requests.append((kind, identifier))
        return len(self.requests)

    def cancelLookup(self, request):
        pass

    def cancelOpen(self):
        pass

    def refresh(self):
        pass


def test_downloaded_collection_play_and_open_bypass_provider_pages_and_stale_results(tmp_path):
    app, browse, worker, account, view, played, queued, resets = setup(tmp_path)
    downloads = Downloads()
    browse.downloads = downloads
    downloads.collectionFound.connect(browse._download_result)
    tracks = [{"kind": "song", "videoId": IDS[0], "title": "Offline fixture"}]
    collection = {"kind": "playlist", "id": "PLfixture", "items": tracks, "downloadKey": "playlist:PLfixture", "cursor": None}
    account.connected = False
    browse.play({"kind": "playlist", "id": "PLfixture"})
    downloads.collectionFound.emit(1, collection)
    assert played == [tracks] and not worker.requests
    browse.open({"kind": "playlist", "id": "PLfixture"})
    downloads.collectionFound.emit(2, collection)
    assert view.data["downloadKey"] == collection["downloadKey"] and not worker.requests
    browse.playView()
    assert played == [tracks, tracks] and not worker.requests
    browse.play({"kind": "album", "id": "MPREfixture"})
    browse.play({"kind": "song", "videoId": IDS[1], "title": "New selection"})
    downloads.collectionFound.emit(3, collection)
    assert played[-1]["videoId"] == IDS[1] and len(played) == 3
    browse.open({"kind": "playlist", "id": "PLfixture"})
    browse.shell.navigate("Downloads")
    downloads.collectionFound.emit(4, collection)
    assert view.route == "downloads"


@pytest.mark.parametrize("entry_point", ["home", "search", "album", "playlist", "queue"])
def test_every_playback_entry_point_selects_disk_with_expired_credentials(tmp_path, entry_point):
    app, browse, catalog_worker, account, view, played, queued, resets = setup(tmp_path)
    store = DownloadStore(tmp_path)
    key = store.schedule(body("PLfixture", [IDS[0]]))
    audio = store.root / "audio" / (IDS[0] + ".wav")
    audio.parent.mkdir()
    write_wave(audio)
    store.media.publish(IDS[0], audio)
    store.progress(key, 1, 1, state="complete")
    tracks = store.view(key)["items"]
    store.close()
    def forbidden(*args):
        raise AssertionError("A downloaded song must not access credentials or resolve/fetch an audio stream")
    source = Sources(SimpleNamespace(session=None, restore=forbidden), MediaFiles(tmp_path / "media"), forbidden)
    worker = FakeWorker()
    player = Playback(tmp_path, worker, audio_factory=FakeAudio)
    browse.player = player
    account.connected = False
    if entry_point in {"album", "playlist"}:
        view.showLocal(entry_point, {"items": tracks, "downloadKey": entry_point + ":fixture", "cursor": None})
        browse.playView()
    elif entry_point == "queue":
        player.enqueue(tracks)
        player.select(0)
    else:
        view.showLocal(entry_point, {"items": tracks})
        browse.play(tracks[0])
    operation, payload = worker.requests[-1]
    result = source.resolve(payload["videoId"], available=False)
    worker.succeeded.emit(len(worker.requests), result)
    assert player.playing and player.sourceKind == "local" and not catalog_worker.requests
    player.seek(0.5)
    player.close()
    restarted = Playback(tmp_path, FakeWorker(), audio_factory=FakeAudio)
    assert restarted.position == 0.5 and not restarted.playing
    restarted.close()
    source.media.close()
