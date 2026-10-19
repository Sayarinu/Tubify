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
