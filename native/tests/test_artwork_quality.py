from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QImage

from youtube_music_native.artwork_sources import choose, media_variants, variants
from youtube_music_native.catalog import Catalog
from youtube_music_native.downloads import DownloadStore, clean_track
from youtube_music_native.large_artwork import resolve
from youtube_music_native.store import MetadataStore


VIDEO = "abcdefghijk"
VARIANTS = [{"url": f"https://fixture.invalid/{size}.png", "width": size, "height": size} for size in (60, 300, 1200)]


def image(folder, size, name="art.png"):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    art = QImage(size, size, QImage.Format.Format_RGB32)
    art.fill(0xFF112233)
    assert art.save(str(path))
    return path.as_uri()


def saved(tmp_path):
    store = DownloadStore(tmp_path)
    small = image(store.root / "artwork", 60)
    body = {"kind": "song", "id": VIDEO, "title": "Fixture", "items": [clean_track({"videoId": VIDEO, "title": "Fixture"})]}
    body["items"][0]["localThumbnail"] = small
    identifier = store.schedule(body)
    return store, identifier, small


@pytest.mark.parametrize("pixels,expected", [(60, 60), (61, 300), (300, 300), (450, 1200), (1200, 1200), (1500, 1200)])
def test_smallest_adequate_physical_cover_or_largest_fallback(pixels, expected):
    assert choose(VARIANTS, pixels)["width"] == expected


def test_normalization_bounds_untrusted_dimensions_and_preserves_best_duplicate():
    values = variants([*VARIANTS, {"url": VARIANTS[-1]["url"]}, {"url": "file:///private", "width": 5000}, {"url": "https://fixture.invalid/bad", "width": float("nan"), "height": "1200"}])
    assert len(values) == 4 and values[2]["width"] == 1200 and values[3]["width"] == 0
    track = clean_track({"videoId": VIDEO, "title": "Fixture", "artworkVariants": VARIANTS, "private": "must not persist"})
    assert track["largeThumbnail"] == VARIANTS[-1]["url"] and track["artworkVariants"] == VARIANTS
    assert "private" not in track


def test_album_larger_artwork_is_retained_even_with_small_track_cover(tmp_path):
    client = SimpleNamespace(get_album=lambda _: {"title": "Fixture", "thumbnails": VARIANTS, "tracks": [{"videoId": VIDEO, "title": "Track", "thumbnails": VARIANTS[:1]}]})
    provider = Catalog(SimpleNamespace(profile={"name": "fixture"}, catalog=lambda: client), MetadataStore(tmp_path / "metadata.sqlite3"))
    track = provider.fetch("album", {"id": "MPREfixture"})["items"][0]
    assert track["largeThumbnail"] == VARIANTS[-1]["url"]
    assert choose(media_variants(track), 600)["width"] == 1200
    provider.store.close()


def test_download_upgrade_is_atomic_offline_and_resists_stale_transfer(tmp_path):
    store, identifier, small = saved(tmp_path)
    stale_body = store.collection(identifier)
    requests = []
    def fetch(url, folder):
        requests.append(url)
        return image(folder, 1200)
    def forbidden():
        raise AssertionError("Known artwork must not access account or audio")
    result = resolve(SimpleNamespace(catalog=forbidden), tmp_path, {"videoId": VIDEO, "artworkVariants": VARIANTS}, 600, True, fetch)
    assert result["upgraded"] and result["width"] == 1200 and requests == [VARIANTS[-1]["url"]]
    store.update_body(identifier, stale_body)
    assert store.collection(identifier)["items"][0]["localThumbnail"] == result["url"]
    store.close()
    reopened = resolve(SimpleNamespace(catalog=forbidden), tmp_path, {"videoId": VIDEO}, 1200, False, lambda *_: forbidden())
    assert reopened["url"] == result["url"] and reopened["width"] == 1200
    store = DownloadStore(tmp_path)
    store.remove(identifier)
    assert not Path(result["url"].removeprefix("file://")).exists()
    store.close()


def test_download_failed_or_lower_resolution_upgrade_keeps_existing_image(tmp_path):
    store, _, small = saved(tmp_path)
    for fetch in (lambda *_: "", lambda _, folder: image(folder, 30)):
        result = resolve(SimpleNamespace(), tmp_path, {"videoId": VIDEO, "artworkVariants": VARIANTS}, 600, True, fetch)
        assert result["url"] == small and result["width"] == 60
    store.close()


def test_removed_download_is_not_recreated_by_completed_artwork_request(tmp_path):
    store, identifier, _ = saved(tmp_path)
    def fetch(url, folder):
        store.remove(identifier)
        return image(folder, 1200)
    result = resolve(SimpleNamespace(), tmp_path, {"videoId": VIDEO, "artworkVariants": VARIANTS}, 600, True, fetch)
    assert not result.get("url") and not store.status()["collections"]
    store.close()


def test_authoritative_album_enrichment_and_wrong_song_results(tmp_path):
    calls = []
    client = SimpleNamespace(get_album=lambda key: (calls.append(key) or {"thumbnails": VARIANTS}))
    result = resolve(SimpleNamespace(catalog=lambda: client), tmp_path, {"videoId": VIDEO, "album": {"id": "MPREfixture"}, "artworkVariants": VARIANTS[:1]}, 600, True)
    assert result["url"] == VARIANTS[-1]["url"] and calls == ["MPREfixture"]
    client = SimpleNamespace(get_song=lambda key: {"videoDetails": {"videoId": "wrongtrack1", "thumbnail": {"thumbnails": VARIANTS}}})
    result = resolve(SimpleNamespace(catalog=lambda: client), tmp_path, {"videoId": VIDEO, "artworkVariants": VARIANTS[:1]}, 600, True)
    assert result["url"] == VARIANTS[0]["url"]


def test_offline_or_failed_enrichment_preserves_legacy_download(tmp_path):
    store, _, small = saved(tmp_path)
    def forbidden():
        raise AssertionError("Offline artwork must not refresh credentials")
    assert resolve(SimpleNamespace(catalog=forbidden), tmp_path, {"videoId": VIDEO}, 600, False)["url"] == small
    assert resolve(SimpleNamespace(catalog=forbidden), tmp_path, {"videoId": VIDEO}, 600, True)["url"] == small
    store.close()


def test_artwork_view_ignores_stale_and_lower_quality_results(tmp_path, monkeypatch):
    from youtube_music_native import download_view
    from test_playback import FakeWorker
    app = QCoreApplication.instance() or QCoreApplication([])
    worker = FakeWorker()
    monkeypatch.setattr(download_view, "Worker", lambda *args, **kwargs: worker)
    view = download_view.DownloadView(tmp_path, fixture=True)
    view.fixture = False
    media = {"videoId": VIDEO, "artworkVariants": VARIANTS}
    view.ensureArtwork(media, 300)
    view.ensureArtwork(media, 600)
    worker.succeeded.emit(1, {"videoId": VIDEO, "url": "old", "width": 300, "height": 300})
    assert not view.largeArtwork
    worker.succeeded.emit(2, {"videoId": VIDEO, "url": "large", "width": 1200, "height": 1200})
    assert view.largeArtwork[VIDEO]["url"] == "large"
    view.ensureArtwork(media, 200)
    worker.succeeded.emit(3, {"videoId": VIDEO, "url": "smaller", "width": 300, "height": 300})
    assert view.largeArtwork[VIDEO]["url"] == "large"
    view.close()


def test_artwork_failure_retries_only_on_explicit_reopen_after_cooldown(tmp_path, monkeypatch):
    from youtube_music_native import download_view
    from test_playback import FakeWorker
    app = QCoreApplication.instance() or QCoreApplication([])
    worker, now = FakeWorker(), [10.0]
    monkeypatch.setattr(download_view, "Worker", lambda *args, **kwargs: worker)
    monkeypatch.setattr(download_view.time, "monotonic", lambda: now[0])
    view = download_view.DownloadView(tmp_path, fixture=True)
    view.fixture = False
    media = {"videoId": VIDEO}
    view.ensureArtwork(media, 600)
    worker.failed.emit(1, {"message": "offline"})
    view.ensureArtwork(media, 600, True)
    assert len(worker.requests) == 1
    now[0] = 50
    view.ensureArtwork(media, 600)
    assert len(worker.requests) == 1  # Download progress does not trigger retries.
    view.ensureArtwork(media, 600, True)
    assert len(worker.requests) == 2
    view.close()
