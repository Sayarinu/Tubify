import time
from types import SimpleNamespace

import pytest

from tubify.catalog.catalog import Catalog, CatalogError, item
from tubify.catalog.store import MetadataStore


def track(index):
    return {"videoId": f"song{index:07}", "title": f"Song {index}", "artists": [{"name": "Artist", "id": "artist"}], "duration": "3:42"}


def test_normalizes_provider_variants_and_unavailable_tracks():
    value = item({**track(1), "isAvailable": False, "setVideoId": "duplicate-entry", "thumbnails": [
        {"url": "https://example.com/small.jpg", "width": 120, "height": 120},
        {"url": "https://example.com/a.jpg", "width": 300, "height": 300},
        {"url": "https://example.com/large.jpg", "width": 900, "height": 900},
    ]})
    assert value["duration"] == 222
    # Radio (watch playlist) rows label their length instead of a duration.
    assert item({"videoId": "radio000001", "title": "Radio", "length": "3:07"})["duration"] == 187
    assert not value["available"]
    assert value["setVideoId"] == "duplicate-entry"
    assert value["thumbnail"] == "https://example.com/a.jpg"
    assert value["largeThumbnail"] == "https://example.com/large.jpg"
    assert item({"title": "Album", "browseId": "MPREfixture"})["kind"] == "album"
    assert item({"title": "Artist", "browseId": "UCfixture"})["kind"] == "artist"
    assert item({"title": "List", "playlistId": "PLfixture"})["kind"] == "playlist"
    assert item({"isAvailable": False})["title"] == "Unavailable song"
    album = item({"title": "Album", "browseId": "MPREfixture", "playlistId": "OLAKfixture"}, "album")
    assert album["kind"] == "album" and album["id"] == "MPREfixture"
    assert album["playlistId"] == "OLAKfixture"
    assert item({"artist": "Subscribed artist", "browseId": "UCfixture"}, "artist")["title"] == "Subscribed artist"


def test_library_sections_use_their_provider_methods_and_preserve_edit_identifiers(tmp_path):
    provider = SimpleNamespace(
        get_library_playlists=lambda limit: [{"playlistId": "PLfixture", "title": "Owned", "owned": True}],
        get_library_subscriptions=lambda limit, **kwargs: [{"browseId": "UCfixture", "artist": "Subscribed"}],
        get_liked_songs=lambda limit: {"tracks": [{**track(1), "likeStatus": "LIKE", "setVideoId": "occurrence-one"}]},
    )
    catalog = Catalog(SimpleNamespace(profile={"name": "Fixture"}, catalog=lambda: provider), MetadataStore(tmp_path / "cache.sqlite3"))
    assert catalog.fetch("library_playlists")["items"][0]["owned"]
    assert catalog.fetch("library_subscriptions", {"order": "a_to_z"})["items"][0]["title"] == "Subscribed"
    liked = catalog.fetch("library_liked")["items"][0]
    assert liked["rating"] == "LIKE" and liked["setVideoId"] == "occurrence-one"


def test_empty_playlist_without_provider_song_shelf_uses_verified_library_metadata(tmp_path):
    def empty(identifier, limit):
        raise KeyError("contents")
    provider = SimpleNamespace(get_playlist=empty, get_library_playlists=lambda limit: [{"playlistId": "PLempty", "title": "Empty", "owned": True, "count": "0"}])
    catalog = Catalog(SimpleNamespace(profile={"name": "Fixture"}, catalog=lambda: provider), MetadataStore(tmp_path / "cache.sqlite3"))
    value = catalog.fetch("playlist", {"id": "PLempty"})
    assert value["title"] == "Empty" and value["editable"] and value["items"] == []


def test_delayed_provider_reads_do_not_restore_removed_entries_or_skip_the_next_page(tmp_path):
    rows = [{**track(index), "setVideoId": str(index)} for index in range(80)]
    provider = SimpleNamespace(get_playlist=lambda identifier, limit: {"title": "Playlist", "owned": True, "tracks": rows[:limit], "trackCount": 80})
    change = {"result": {"action": "playlist_remove", "id": "PLfixture", "removedSetVideoId": "10"}}
    catalog = Catalog(SimpleNamespace(profile={"name": "Fixture"}, catalog=lambda: provider), MetadataStore(tmp_path / "cache.sqlite3"), [change])
    first = catalog.fetch("playlist", {"id": "PLfixture"}, page_size=39)
    second = catalog.fetch("playlist", {"id": "PLfixture"}, offset=39)
    keys = [item["setVideoId"] for item in first["items"] + second["items"]]
    assert keys == [str(index) for index in range(80) if index != 10]


def test_pages_provider_continuations_and_restores_cache_offline(tmp_path):
    calls = []

    def search(query, filter, limit):
        calls.append(limit)
        return [track(i) for i in range(min(limit, 85))]

    provider = SimpleNamespace(search=search)
    auth = SimpleNamespace(profile={"name": "Fixture", "handle": "@fixture"}, catalog=lambda: provider)
    store = MetadataStore(tmp_path / "metadata.sqlite3")
    catalog = Catalog(auth, store)
    first = catalog.fetch("search", {"query": "song", "filter": "songs"})
    second = catalog.fetch("search", {"query": "song", "filter": "songs"}, offset=first["cursor"])
    third = catalog.fetch("search", {"query": "song", "filter": "songs"}, offset=second["cursor"])
    assert [len(p["items"]) for p in (first, second, third)] == [40, 40, 5]
    assert third["cursor"] is None and calls == [41, 81, 121]
    store.close()

    def offline():
        raise ConnectionError("private raw provider detail")

    auth.catalog = offline
    restarted = Catalog(auth, MetadataStore(tmp_path / "metadata.sqlite3"))
    cached = restarted.fetch("search", {"query": "song", "filter": "songs"}, refresh=True)
    assert cached["stale"] and cached["warning"] == "offline"
    assert len(cached["items"]) == 40
    assert "private raw" not in str(cached)
    restarted.store.close()


def test_rejected_session_marks_the_cached_page_for_reconnecting(tmp_path):
    from ytmusicapi.exceptions import YTMusicServerError, YTMusicUserError

    provider = SimpleNamespace(search=lambda query, filter, limit: [track(0)])
    auth = SimpleNamespace(profile={"name": "Fixture"}, catalog=lambda: provider)
    catalog = Catalog(auth, MetadataStore(tmp_path / "metadata.sqlite3"))
    catalog.fetch("search", {"query": "song", "filter": "songs"})
    for error, warning in ((YTMusicServerError("Server returned HTTP 401: Unauthorized.\nprivate"), "reconnect"),
                           (YTMusicUserError("private"), "reconnect"),
                           (YTMusicServerError("Server returned HTTP 500: Error.\nprivate"), "offline"),
                           (RuntimeError("Server returned HTTP 403"), "offline")):
        def failing(error=error):
            raise error
        auth.catalog = failing
        page = catalog.fetch("search", {"query": "song", "filter": "songs"}, refresh=True)
        assert page["stale"] and page["warning"] == warning
    catalog.store.close()


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
    # One full fetch backs every page, so later pages never come from a reshuffled response.
    assert second["cursor"] is None and calls == [30]


def test_home_songs_without_an_artist_take_their_album_artists(tmp_path):
    lookups = []

    def album(identifier):
        lookups.append(identifier)
        if identifier == "MPREbroken":
            raise RuntimeError("album unavailable")
        return {"artists": [{"name": "Lotus Juice", "id": None}, {"name": "ATLUS Sound Team", "id": "UCatlus"}]}

    # ytmusicapi drops an unlinked artist that is followed only by a play count.
    unlinked = {"videoId": "remix000001", "title": "Remix", "views": "2.5M", "album": {"name": "Soundtrack", "id": "MPREsoundtrack"}}
    home = lambda limit: [{"title": "Covers and remixes", "contents": [
        unlinked, {**unlinked, "videoId": "remix000002"}, track(1),
        {"videoId": "broken00001", "title": "Broken", "album": {"name": "Gone", "id": "MPREbroken"}},
    ]}]
    auth = SimpleNamespace(profile={"name": "Fixture"}, catalog=lambda: SimpleNamespace(get_home=home, get_album=album))
    songs = Catalog(auth, MetadataStore(tmp_path / "metadata.sqlite3")).fetch("home")["shelves"][0]["items"]
    assert [song["artist"] for song in songs] == ["Lotus Juice • ATLUS Sound Team"] * 2 + ["Artist", ""]
    assert songs[0]["artists"][1] == {"name": "ATLUS Sound Team", "id": "UCatlus"}
    assert lookups == ["MPREsoundtrack", "MPREbroken"]


def test_home_pins_known_shelves_and_chooses_layout_by_content(tmp_path):
    from tubify.catalog.catalog import arrange_home

    song = {"kind": "song", "title": "Song"}
    album = {"kind": "album", "title": "Album"}
    sections = arrange_home([
        {"title": "Fall vibes", "items": [album]},
        {"title": "Listen again", "items": [song, album]},
        {"title": "Long listening", "items": [song, {"title": "Untyped"}]},
        {"title": "Quick picks", "items": [album]},
    ])
    assert [section["title"] for section in sections] == ["Quick picks", "Listen again", "Fall vibes", "Long listening"]
    assert [section["layout"] for section in sections] == ["grid", "mixed", "cards", "rows"]


def test_listening_history_keeps_cached_home_and_actions_keep_stable_routes(tmp_path):
    from tubify.catalog.store import MetadataStore as Store

    store = Store(tmp_path / "metadata.sqlite3")
    store.write('["scope", "home", {}]', {"shelves": []})
    store.write('["scope", "library_playlists", {}]', {"items": []})
    store.invalidate(("home",))
    assert store.read('["scope", "home", {}]') and not store.read('["scope", "library_playlists", {}]')
    store.close()


def test_artist_subscription_uses_its_channel_id_and_unavailable_release_is_actionable(tmp_path):
    import pytest
    from tubify.catalog.catalog import CatalogError

    provider = SimpleNamespace(get_artist=lambda identifier: {"name": "Artist", "channelId": "UCsubscription", "subscribed": True, "songs": {"results": [track(1)]}}, get_album=lambda identifier: None)
    catalog = Catalog(SimpleNamespace(profile={"name": "Fixture"}, catalog=lambda: provider), MetadataStore(tmp_path / "metadata.sqlite3"))
    artist = catalog.fetch("artist", {"id": "UCbrowse"})
    assert artist["subscriptionId"] == "UCsubscription" and artist["subscribed"]
    with pytest.raises(CatalogError, match="unavailable"):
        catalog.fetch("album", {"id": "MPREunavailable"})


def test_artist_top_songs_are_five_rows_with_show_all_for_the_songs_playlist(tmp_path):
    raw = {"name": "Artist", "songs": {"browseId": "VLOLAKsongs", "results": [track(i) for i in range(7)]},
           "albums": {"browseId": "UCartist", "params": "albums", "results": [{"title": "Record", "browseId": "MPRErecord"}]}}
    provider = SimpleNamespace(get_artist=lambda identifier: raw)
    catalog = Catalog(SimpleNamespace(profile={"name": "Fixture"}, catalog=lambda: provider), MetadataStore(tmp_path / "metadata.sqlite3"))
    songs, albums = catalog.fetch("artist", {"id": "UCartist"})["shelves"]
    assert songs["title"] == "Top songs" and songs["layout"] == "rows" and songs["showAll"]
    assert songs["browseId"] == "OLAKsongs" and not songs["params"]
    assert [value["videoId"] for value in songs["items"]] == [track(i)["videoId"] for i in range(5)]
    assert albums["browseId"] == "UCartist" and albums["params"] == "albums" and "layout" not in albums


def test_artist_top_songs_without_a_playlist_show_all_only_when_more_than_five():
    from tubify.catalog.catalog import artist_songs, items

    few = artist_songs({"results": []}, items([track(i) for i in range(5)]))
    assert few["layout"] == "rows" and not few["browseId"] and not few["showAll"] and len(few["items"]) == 5
    many = artist_songs({"browseId": None}, items([track(i) for i in range(8)]))
    assert many["showAll"] and len(many["items"]) == 8


def test_music_search_filters_deferred_types_without_skipping_between_pages(tmp_path):
    rows = [{**track(i), "resultType": "video" if i % 3 == 0 else "song"} for i in range(100)]
    provider = SimpleNamespace(search=lambda query, filter, limit: rows[:limit])
    catalog = Catalog(SimpleNamespace(profile={"name": "Fixture"}, catalog=lambda: provider), MetadataStore(tmp_path / "cache.sqlite3"))
    first = catalog.fetch("search", {"query": "music", "filter": "songs"})
    second = catalog.fetch("search", {"query": "music", "filter": "songs"}, offset=first["cursor"])
    assert [row["videoId"] for row in first["items"] + second["items"]] == [row["videoId"] for row in rows if row["resultType"] == "song"]
    assert second["cursor"] is None


def test_unfiltered_search_puts_exact_artist_first_and_groups_results(tmp_path):
    # Shape of ytmusicapi's response for "aespa": a top-result artist card without
    # title/browseId, its songs, then the Songs shelf. Names here are fixtures.
    rows = [
        {"category": "Top result", "resultType": "artist", "artists": [{"name": "aespa", "id": "UCaespa"}], "subscribers": "8M", "thumbnails": []},
        *[{**track(i), "category": "Songs", "resultType": "song"} for i in range(6)],
        {"category": "Albums", "resultType": "album", "title": "Armageddon", "browseId": "MPREalbum", "artists": [{"name": "aespa", "id": "UCaespa"}]},
        {"category": "Artists", "resultType": "artist", "artist": "aespa", "browseId": "UCaespa"},
        {"category": "Community playlists", "resultType": "playlist", "title": "aespa mix", "browseId": "VLPLmix"},
    ]
    provider = SimpleNamespace(search=lambda query, filter, limit: rows)
    catalog = Catalog(SimpleNamespace(profile={"name": "Fixture"}, catalog=lambda: provider), MetadataStore(tmp_path / "cache.sqlite3"))
    result = catalog.fetch("search", {"query": "aespa"}, page_size=100)
    assert result["topResult"]["kind"] == "artist" and result["topResult"]["id"] == "UCaespa" and result["topResult"]["title"] == "aespa"
    assert [value["kind"] for value in result["items"]][:2] == ["artist", "song"]
    assert len(result["groups"]["song"]) == 6 and not result["groups"]["artist"]
    assert result["groups"]["album"][0]["title"] == "Armageddon" and result["groups"]["playlist"][0]["kind"] == "playlist"


def test_exact_artist_match_outranks_a_song_top_result():
    from tubify.catalog.catalog import arrange_search

    song = {"kind": "song", "id": "abcdefghijk", "title": "Supernova", "category": "Top result"}
    artist = {"kind": "artist", "id": "UCaespa", "title": "aespa", "category": "Artists"}
    arranged = arrange_search("Aespa", [song, artist])
    assert arranged["topResult"] is artist and arranged["groups"]["song"] == [song]


def test_each_simple_route_reaches_its_provider_method(tmp_path):
    provider = SimpleNamespace(
        get_history=lambda: [track(1)],
        get_search_suggestions=lambda query: ["suggested " + query],
        get_mood_categories=lambda: {"Moods": [{"title": "Chill", "params": "p"}]},
        get_mood_playlists=lambda params: [{"playlistId": "PLmood", "title": "Mood " + params}],
        get_watch_playlist=lambda **kwargs: {"tracks": [track(2)], "lyrics": "MPLY", "related": "MPTR"},
        get_artist_albums=lambda identifier, params, limit: [{"browseId": "MPREb", "title": "Album"}],
    )
    catalog = Catalog(SimpleNamespace(profile={"name": "Fixture"}, catalog=lambda: provider), MetadataStore(tmp_path / "cache.sqlite3"))
    assert catalog.fetch("history")["items"][0]["videoId"] == track(1)["videoId"]
    assert catalog.fetch("suggestions", {"query": "so"})["suggestions"] == ["suggested so"]
    assert catalog.fetch("moods")["groups"]["Moods"][0]["title"] == "Chill"
    assert catalog.fetch("mood", {"params": "x"})["items"][0]["title"] == "Mood x"
    radio = catalog.fetch("radio", {"id": track(2)["videoId"]})
    assert radio["lyricsId"] == "MPLY" and radio["items"][0]["videoId"] == track(2)["videoId"]
    assert catalog.fetch("artist_albums", {"id": "UCartist", "params": "p"})["items"][0]["kind"] == "album"
    for route in ("unknown", "library_unknown"):
        with pytest.raises(CatalogError, match="unavailable"):
            catalog.fetch(route)
    catalog.store.close()


def test_an_artist_page_ytmusicapi_cannot_read_names_the_artist_page_not_the_session(tmp_path):
    def unreadable(identifier):
        raise KeyError("header")

    provider = SimpleNamespace(get_artist=unreadable)
    catalog = Catalog(SimpleNamespace(profile={"name": "Fixture"}, catalog=lambda: provider), MetadataStore(tmp_path / "metadata.sqlite3"))
    with pytest.raises(CatalogError, match="artist page in a layout"):
        catalog.fetch("artist", {"id": "UCartist"})


def test_cached_home_takes_the_current_shelf_layouts(tmp_path):
    song = {**track(1), "kind": "song"}
    store = MetadataStore(tmp_path / "metadata.sqlite3")
    provider = SimpleNamespace(get_home=lambda limit: [{"title": "Quick picks", "contents": [track(1)]}])
    catalog = Catalog(SimpleNamespace(profile={"name": "Fixture"}, catalog=lambda: provider), store)
    catalog.fetch("home")
    # A Home saved by an earlier version, when Quick picks paged as rows.
    key = next(row[0] for row in store.db.execute("SELECT key FROM views"))
    store.write(key, {"shelves": [{"title": "Quick picks", "items": [song], "layout": "rows"}], "items": [], "complete": True})
    provider.get_home = None
    assert catalog.fetch("home")["shelves"][0]["layout"] == "grid"
