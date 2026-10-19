import time
from types import SimpleNamespace

from youtube_music_native.catalog import Catalog, item
from youtube_music_native.store import MetadataStore


def track(index):
    return {"videoId": f"song{index:07}", "title": f"Song {index}", "artists": [{"name": "Artist", "id": "artist"}], "duration": "3:42"}


def test_normalizes_provider_variants_and_unavailable_tracks():
    value = item({**track(1), "isAvailable": False, "setVideoId": "duplicate-entry", "thumbnails": [{"url": "https://example.com/a.jpg", "width": 300}]})
    assert value["duration"] == 222
    assert not value["available"]
    assert value["setVideoId"] == "duplicate-entry"
    assert value["thumbnail"] == "https://example.com/a.jpg"
    assert item({"title": "Album", "browseId": "MPREfixture"})["kind"] == "album"
    assert item({"title": "Artist", "browseId": "UCfixture"})["kind"] == "artist"
    assert item({"title": "List", "playlistId": "PLfixture"})["kind"] == "playlist"
    assert item({"isAvailable": False})["title"] == "Unavailable song"
    album = item({"title": "Album", "browseId": "MPREfixture", "playlistId": "OLAKfixture"}, "album")
    assert album["kind"] == "album" and album["id"] == "MPREfixture"
    assert album["playlistId"] == "OLAKfixture"


def test_pages_provider_continuations_and_restores_cache_offline(tmp_path):
    calls = []

    def search(query, filter, limit):
        calls.append(limit)
        return [track(i) for i in range(min(limit, 85))]

    provider = SimpleNamespace(search=search)
    auth = SimpleNamespace(profile={"name": "Fixture", "handle": "@fixture"}, catalog=lambda: provider)
    store = MetadataStore(tmp_path / "metadata.sqlite3")
    catalog = Catalog(auth, store)
    first = catalog.fetch("search", {"query": "song"})
    second = catalog.fetch("search", {"query": "song"}, offset=first["cursor"])
    third = catalog.fetch("search", {"query": "song"}, offset=second["cursor"])
    assert [len(p["items"]) for p in (first, second, third)] == [40, 40, 5]
    assert third["cursor"] is None and calls == [41, 81, 121]
    store.close()

    def offline():
        raise ConnectionError("private raw provider detail")

    auth.catalog = offline
    restarted = Catalog(auth, MetadataStore(tmp_path / "metadata.sqlite3"))
    cached = restarted.fetch("search", {"query": "song"}, refresh=True)
    assert cached["stale"] and cached["warning"] == "offline"
    assert len(cached["items"]) == 40
    assert "private raw" not in str(cached)


def test_album_inherits_artwork_and_artist_and_cache_is_account_scoped(tmp_path):
    provider = SimpleNamespace(get_album=lambda _: {"title": "Record", "artists": [{"name": "Artist", "id": "artist"}], "thumbnails": [{"url": "https://example.com/art"}], "tracks": [{"videoId": "song", "title": "Track"}]})
    auth = SimpleNamespace(profile={"name": "One"}, catalog=lambda: provider)
    catalog = Catalog(auth, MetadataStore(tmp_path / "metadata.sqlite3"))
    album = catalog.fetch("album", {"id": "MPREfixture"})
    assert album["items"][0]["album"]["name"] == "Record"
    assert album["items"][0]["thumbnail"].startswith("https://")
    assert album["items"][0]["artist"] == "Artist"
    auth.profile = {"name": "Two"}
    assert catalog.store.db.execute("SELECT count(*) FROM views").fetchone()[0] == 1
    catalog.fetch("album", {"id": "MPREfixture"})
    assert catalog.store.db.execute("SELECT count(*) FROM views").fetchone()[0] == 2


def test_cache_is_bounded_and_corrupt_rows_are_disposable(tmp_path):
    store = MetadataStore(tmp_path / "metadata.sqlite3")
    for index in range(205):
        store.write(str(index), {"items": [track(index)]})
    assert store.db.execute("SELECT count(*) FROM views").fetchone()[0] == 200
    store.db.execute("INSERT INTO views VALUES (?, ?, ?)", ("corrupt", time.time(), b"invalid"))
    store.db.commit()
    assert store.read("corrupt") is None


def test_explore_and_charts_use_their_distinct_provider_shapes(tmp_path):
    provider = SimpleNamespace(
        get_explore=lambda: {"new_releases": [{"title": "Record", "browseId": "MPREfixture"}], "top_songs": {"items": [track(1)]}, "moods_and_genres": [{"title": "Chill", "params": "fixture"}]},
        get_charts=lambda country: {"countries": {}, "daily": [{"title": "Daily", "playlistId": "PLfixture"}]},
    )
    auth = SimpleNamespace(profile={"name": "Fixture"}, catalog=lambda: provider)
    catalog = Catalog(auth, MetadataStore(tmp_path / "metadata.sqlite3"))
    explore = catalog.fetch("explore")
    assert len(explore["shelves"]) == 2
    assert explore["moods"][0]["title"] == "Chill"
    assert catalog.fetch("charts")["shelves"][0]["items"][0]["kind"] == "playlist"


def test_home_pages_shelves_and_personalizes_listen_again(tmp_path):
    calls = []

    def home(limit):
        calls.append(limit)
        return [{"title": "Listen again" if index == 0 else f"Shelf {index}", "contents": [track(index)]} for index in range(min(limit, 10))]

    auth = SimpleNamespace(profile={"name": "Fixture"}, catalog=lambda: SimpleNamespace(get_home=home))
    catalog = Catalog(auth, MetadataStore(tmp_path / "metadata.sqlite3"))
    first = catalog.fetch("home")
    second = catalog.fetch("home", offset=first["cursor"])
    assert len(first["shelves"]) == 6 and len(second["shelves"]) == 4
    assert first["shelves"][0]["subtitle"] == "FIXTURE"
    assert second["cursor"] is None and calls == [7, 13]


def test_artist_subscription_uses_its_channel_id_and_unavailable_release_is_actionable(tmp_path):
    import pytest
    from youtube_music_native.catalog import CatalogError

    provider = SimpleNamespace(get_artist=lambda identifier: {"name": "Artist", "channelId": "UCsubscription", "subscribed": True, "songs": {"results": [track(1)]}}, get_album=lambda identifier: None)
    catalog = Catalog(SimpleNamespace(profile={"name": "Fixture"}, catalog=lambda: provider), MetadataStore(tmp_path / "metadata.sqlite3"))
    artist = catalog.fetch("artist", {"id": "UCbrowse"})
    assert artist["subscriptionId"] == "UCsubscription" and artist["subscribed"]
    with pytest.raises(CatalogError, match="unavailable"):
        catalog.fetch("album", {"id": "MPREunavailable"})


def test_music_search_filters_deferred_types_without_skipping_between_pages(tmp_path):
    rows = [{**track(i), "resultType": "video" if i % 3 == 0 else "song"} for i in range(100)]
    provider = SimpleNamespace(search=lambda query, filter, limit: rows[:limit])
    catalog = Catalog(SimpleNamespace(profile={"name": "Fixture"}, catalog=lambda: provider), MetadataStore(tmp_path / "cache.sqlite3"))
    first = catalog.fetch("search", {"query": "music"})
    second = catalog.fetch("search", {"query": "music"}, offset=first["cursor"])
    assert [row["videoId"] for row in first["items"] + second["items"]] == [row["videoId"] for row in rows if row["resultType"] == "song"]
    assert second["cursor"] is None
