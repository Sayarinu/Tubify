from PySide6.QtCore import QCoreApplication, QObject, Signal

from tubify.catalog.artist_preview import ArtistPreview


class Player(QObject):
    changed = Signal()
    currentTrack = {}


class Shell(QObject):
    panelChanged = Signal()
    nowPlayingOpen = True


class Worker(QObject):
    succeeded = Signal(int, "QVariantMap")
    failed = Signal(int, "QVariantMap")

    def __init__(self):
        super().__init__()
        self.requests = []

    def request(self, operation, payload):
        self.requests.append((operation, payload))
        return len(self.requests)


def build():
    QCoreApplication.instance() or QCoreApplication([])
    player, shell, worker = Player(), Shell(), Worker()
    return player, shell, worker, ArtistPreview(player, shell, worker, "cache.sqlite3")


def play(player, identifier, name):
    player.currentTrack = {"artists": [{"id": identifier, "name": name}]}
    player.changed.emit()


def test_shows_the_name_at_once_and_details_once_loaded():
    player, _shell, worker, preview = build()
    play(player, "UCone", "One")
    assert preview.name == "One" and preview.image == "" and not worker.requests
    preview._load()
    assert worker.requests[0][1]["route"] == "artist" and worker.requests[0][1]["params"] == {"id": "UCone"}
    worker.succeeded.emit(1, {"title": "One Band", "hero": "wide.jpg", "thumbnail": "square.jpg", "monthlyListeners": "9M", "subtitle": "About"})
    assert (preview.name, preview.image, preview.audience, preview.description) == ("One Band", "wide.jpg", "9M", "About")


def test_skipping_songs_settles_on_the_last_artist_and_ignores_late_results():
    player, _shell, worker, preview = build()
    play(player, "UCone", "One")
    preview._load()
    play(player, "UCtwo", "Two")
    worker.succeeded.emit(1, {"title": "One Band", "hero": "wide.jpg"})
    assert preview.name == "Two" and preview.image == ""


def test_returning_to_an_artist_uses_the_cache():
    player, _shell, worker, preview = build()
    play(player, "UCone", "One")
    preview._load()
    worker.succeeded.emit(1, {"title": "One Band", "thumbnail": "square.jpg"})
    play(player, "UCtwo", "Two")
    play(player, "UCone", "One")
    assert preview.name == "One Band" and preview.image == "square.jpg" and not preview.settle.isActive() and len(worker.requests) == 1


def test_nothing_is_looked_up_while_the_view_is_hidden():
    player, shell, worker, preview = build()
    shell.nowPlayingOpen = False
    play(player, "UCone", "One")
    assert not preview.settle.isActive() and not worker.requests and preview.name == ""
    shell.nowPlayingOpen = True
    shell.panelChanged.emit()
    assert preview.name == "One" and preview.settle.isActive()


def test_a_failed_lookup_keeps_the_name():
    player, _shell, worker, preview = build()
    play(player, "UCone", "One")
    preview._load()
    worker.failed.emit(1, {"message": "Unavailable"})
    assert preview.name == "One" and preview.image == ""


def test_an_artist_without_an_id_is_shown_by_name_without_a_lookup():
    player, _shell, worker, preview = build()
    player.currentTrack = {"artist": "Loose Name"}
    player.changed.emit()
    assert preview.name == "Loose Name" and not preview.settle.isActive() and not worker.requests
