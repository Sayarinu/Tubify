from types import SimpleNamespace

import pytest

from youtube_music_native.playlist_ops import PlaylistError, perform


def test_playlist_occurrences_are_distinct_and_add_preserves_requested_duplicates():
    calls = []
    def called(name, *args, **kwargs):
        calls.append((name, args, kwargs))
        return "STATUS_SUCCEEDED"
    client = SimpleNamespace(
        add_playlist_items=lambda *a, **k: called("add", *a, **k),
        remove_playlist_items=lambda *a, **k: called("remove", *a, **k),
        edit_playlist=lambda *a, **k: called("edit", *a, **k),
    )
    perform(client, "playlist_add", {"id": "PLfixture", "videoIds": ["abcdefghijk", "abcdefghijk"]})
    perform(client, "playlist_remove", {"id": "PLfixture", "videoId": "abcdefghijk", "setVideoId": "second-occurrence=="})
    perform(client, "playlist_move", {"id": "PLfixture", "setVideoId": "second-occurrence==", "successor": "first-occurrence=="})
    perform(client, "playlist_move", {"id": "PLfixture", "setVideoId": "first-occurrence==", "successor": ""})
    assert calls == [
        ("add", ("PLfixture", ["abcdefghijk", "abcdefghijk"]), {"duplicates": True}),
        ("remove", ("PLfixture", [{"videoId": "abcdefghijk", "setVideoId": "second-occurrence=="}]), {}),
        ("edit", ("PLfixture",), {"moveItem": ("second-occurrence==", "first-occurrence==")}),
        ("edit", ("PLfixture",), {"moveItem": "first-occurrence=="}),
    ]


def test_create_is_private_and_mutation_failures_are_not_reported_as_success():
    created = []
    client = SimpleNamespace(create_playlist=lambda *a, **k: (created.append((a, k)) or "PLcreated"), edit_playlist=lambda *a, **k: {"status": "STATUS_FAILED"})
    result = perform(client, "playlist_create", {"title": "  Test playlist  "})
    assert result == {"action": "playlist_create", "id": "PLcreated", "title": "Test playlist"}
    assert created == [(("Test playlist", ""), {"privacy_status": "PRIVATE"})]
    with pytest.raises(PlaylistError, match="Refresh and retry"):
        perform(client, "playlist_rename", {"id": "PLcreated", "title": "Updated"})
    for name in ("\nInvalid", "<Invalid>"):
        with pytest.raises(PlaylistError, match="name"):
            perform(client, "playlist_create", {"title": name})
    with pytest.raises(PlaylistError, match="entry"):
        perform(client, "playlist_remove", {"id": "PLcreated", "videoId": "abcdefghijk", "setVideoId": ""})


def test_delete_without_status_is_verified_against_the_account_library():
    client = SimpleNamespace(delete_playlist=lambda identifier: {"responseContext": {}}, get_library_playlists=lambda limit: [{"playlistId": "PLother"}])
    assert perform(client, "playlist_delete", {"id": "PLfixture"})["id"] == "PLfixture"
    client.get_library_playlists = lambda limit: [{"playlistId": "PLfixture"}]
    with pytest.raises(PlaylistError):
        perform(client, "playlist_delete", {"id": "PLfixture"})
