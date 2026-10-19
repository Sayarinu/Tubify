from types import SimpleNamespace

from PySide6.QtCore import QCoreApplication, QObject, Signal

from youtube_music_native.queue_additions import QueueAdditions
from test_browse import Account, Worker
from test_local_collections import Downloads


class Player(QObject):
    manualQueueCleared = Signal()

    def __init__(self):
        super().__init__()
        self.calls = []

    def enqueue(self, tracks, next=False):
        self.calls.append((tracks, next))


def setup(tmp_path, local=False):
    app = QCoreApplication.instance() or QCoreApplication([])
    worker, player = Worker(), Player()
    account = Account(worker)
    downloads = Downloads() if local else None
    additions = QueueAdditions(account, player, tmp_path / "metadata.sqlite3", downloads)
    return SimpleNamespace(app=app, worker=worker, player=player, account=account, downloads=downloads, additions=additions)


def song(name):
    return {"kind": "song", "videoId": name, "title": name}


def test_paginated_batches_are_atomic_keep_duplicates_and_preserve_action_order(tmp_path):
    state = setup(tmp_path)
    add = state.additions
    add.add({"kind": "playlist", "id": "PLfixture"})
    add.add(song("later"))
    add.add({"kind": "album", "id": "MPREfixture"}, next=True)
    assert len(state.worker.requests) == 1 and not state.player.calls
    state.worker.succeeded.emit(1, {"items": [song("A"), song("A")], "cursor": 2})
    assert not state.player.calls
    state.worker.succeeded.emit(2, {"items": [song("B")]})
    assert state.player.calls == [([song("A"), song("A"), song("B")], False), ([song("later")], False)]
    assert state.worker.requests[2][1]["params"]["allTracks"]
    state.worker.succeeded.emit(3, {"items": [song("C"), song("D")]})
    assert state.player.calls[-1] == ([song("C"), song("D")], True)
    assert not add.jobs and not add.message


def test_failed_partial_batch_is_discarded_and_later_actions_continue(tmp_path):
    state = setup(tmp_path)
    state.additions.add({"kind": "playlist", "id": "PLfixture"})
    state.additions.add(song("later"))
    state.worker.succeeded.emit(1, {"items": [song("A")], "cursor": 1})
    state.worker.failed.emit(2, {"message": "private provider detail"})
    assert state.player.calls == [([song("later")], False)]
    assert "Could not" in state.additions.message and "private" not in state.additions.message


def test_clear_and_session_change_cancel_jobs_and_ignore_stale_callbacks(tmp_path):
    state = setup(tmp_path)
    state.additions.add({"kind": "playlist", "id": "PLfixture"})
    state.additions.add(song("cancelled"))
    state.player.manualQueueCleared.emit()
    assert state.worker.cancelled == [1]
    state.worker.succeeded.emit(1, {"items": [song("stale")]})
    assert not state.player.calls and not state.additions.jobs
    state.additions.add({"kind": "playlist", "id": "PLnew"})
    state.account.sessionChanged.emit()
    state.worker.succeeded.emit(2, {"items": [song("old account")]})
    assert not state.player.calls
    state.additions.add(song("new"))
    assert state.player.calls == [([song("new")], False)]


def test_downloaded_metadata_queues_without_account_or_provider_and_cancel_ignores_lookup(tmp_path):
    state = setup(tmp_path, local=True)
    state.account.connected = False
    state.additions.add({"kind": "playlist", "id": "PLfixture"})
    state.downloads.collectionFound.emit(1, {"items": [song("offline"), song("offline")]})
    assert state.player.calls == [([song("offline"), song("offline")], False)]
    assert not state.worker.requests
    state.additions.add({"kind": "album", "id": "MPREfixture"})
    state.player.manualQueueCleared.emit()
    state.downloads.collectionFound.emit(2, {"items": [song("stale")]})
    assert len(state.player.calls) == 1 and not state.worker.requests


def test_missing_local_collection_falls_back_to_provider_and_repeated_cursor_fails(tmp_path):
    state = setup(tmp_path, local=True)
    state.additions.add({"kind": "playlist", "id": "PLfixture"})
    state.downloads.collectionFound.emit(1, {})
    assert len(state.worker.requests) == 1
    state.worker.succeeded.emit(1, {"items": [song("A")], "cursor": 0})
    assert not state.player.calls and not state.additions.jobs and state.additions.message
