from types import SimpleNamespace

import pytest

from youtube_music_native.mutations import ActionError, perform


def test_album_save_and_artist_subscription_use_provider_mutation_identifiers():
    calls = []
    client = SimpleNamespace(
        rate_playlist=lambda identifier, rating: calls.append((identifier, rating.value)),
        subscribe_artist=lambda identifier: calls.append(("subscribe", identifier)),
        unsubscribe_artists=lambda identifiers: calls.append(("unsubscribe", identifiers)),
    )
    assert perform(client, "album_library", "OLAKfixture", True)["value"]
    perform(client, "album_library", "OLAKfixture", False)
    perform(client, "artist_subscription", "UCsubscription", True)
    perform(client, "artist_subscription", "UCsubscription", False)
    assert calls == [("OLAKfixture", "LIKE"), ("OLAKfixture", "INDIFFERENT"), ("subscribe", "UCsubscription"), ("unsubscribe", ["UCsubscription"])]
    with pytest.raises(ActionError):
        perform(client, "artist_subscription", "invalid channel", True)


def test_account_change_prevents_queuing_a_library_mutation(tmp_path):
    from PySide6.QtCore import QCoreApplication
    from youtube_music_native.actions import Actions

    app = QCoreApplication.instance() or QCoreApplication([])
    account = SimpleNamespace(worker=None, busy=True, connected=True)
    actions = Actions(account, tmp_path / "cache.sqlite3", fixture=True)
    changed = []
    actions.applied.connect(changed.append)
    actions.set("album_library", "OLAKfixture", True, "MPREfixture")
    assert not changed


def test_rating_and_song_library_changes_use_current_provider_values():
    calls = []
    client = SimpleNamespace(
        rate_song=lambda identifier, rating: calls.append((identifier, rating.value)),
        get_album=lambda identifier: {"tracks": [{"videoId": "abcdefghijk", "feedbackTokens": {"remove": "fixture-remove-token"}}]},
        edit_song_library_status=lambda tokens: calls.append(tokens),
    )
    assert perform(client, "song_rating", "abcdefghijk", "DISLIKE")["value"] == "DISLIKE"
    perform(client, "song_library", "abcdefghijk", False, {"albumId": "MPREfixture"})
    assert calls == [("abcdefghijk", "DISLIKE"), ["fixture-remove-token"]]
    client.rate_song = lambda *args: {"status": "STATUS_FAILED"}
    with pytest.raises(ActionError, match="retry"):
        perform(client, "song_rating", "abcdefghijk", "LIKE")


def test_history_uses_one_provider_instance_and_keeps_tracking_urls_out_of_results(tmp_path):
    from youtube_music_native.worker import handle

    calls = []
    song = {"playbackTracking": {"videostatsPlaybackUrl": {"baseUrl": "https://tracking.invalid/private-fixture"}}}
    client = SimpleNamespace(get_song=lambda identifier: (calls.append(identifier) or song), add_history_item=lambda value: (calls.append(value is song) or SimpleNamespace(status_code=204)))
    service = SimpleNamespace(catalog=lambda: client)
    result = handle(service, {"operation": "account_history", "payload": {"videoId": "abcdefghijk", "cache_path": str(tmp_path / "cache.sqlite3")}})
    assert calls == ["abcdefghijk", True] and result["recorded"]
    assert "tracking.invalid" not in str(result)
