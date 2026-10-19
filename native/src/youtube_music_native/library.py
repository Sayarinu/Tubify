"""Library navigation and account edits; provider and disk work stay in workers."""

from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot


SECTIONS = {"Playlists": "library_playlists", "Songs": "library_songs", "Albums": "library_albums", "Artists": "library_artists", "Subscriptions": "library_subscriptions", "Liked songs": "library_liked", "History": "history"}
ORDERS = {"Recently added": "recently_added", "A to Z": "a_to_z", "Z to A": "z_to_a"}


class Library(QObject):
    changed = Signal()
    dialogRequested = Signal(str, dict)
    chooserRequested = Signal(dict)
    editFinished = Signal()

    def __init__(self, shell, account, view, player, browse, actions, cache_path, fixture=None, parent=None):
        super().__init__(parent)
        self.shell, self.account, self.view, self.player, self.browse, self.actions = shell, account, view, player, browse, actions
        self.worker, self.cache_path, self.fixture = account.worker, str(cache_path), fixture
        self._selected, self._order, self._choices, self._choices_request = "Playlists", "Recently added", [], None
        self._message, self._identity, self._pending_move = "", None, None
        self._adding = None
        shell.navigationRequested.connect(self._navigate)
        shell.actionRequested.connect(self._action)
        view.changed.connect(self._restore)
        actions.applied.connect(self._applied)
        account.connectedChanged.connect(self._connected)
        if self.worker:
            self.worker.succeeded.connect(self._result)
            self.worker.failed.connect(self._failed)

    @Property("QVariantList", constant=True)
    def sections(self):
        return [name for name in SECTIONS if name != "History"]

    @Property(str, notify=changed)
    def selectedSection(self):
        return self._selected

    @Property("QVariantList", constant=True)
    def orders(self):
        return list(ORDERS)

    @Property(str, notify=changed)
    def selectedOrder(self):
        return self._order

    @Property("QVariantList", notify=changed)
    def playlists(self):
        return self._choices

    @Property(bool, notify=changed)
    def loadingPlaylists(self):
        return self._choices_request is not None

    @Property(str, notify=changed)
    def message(self):
        return self._message

    @Slot()
    def dismiss(self):
        self._message = ""
        self.changed.emit()

    def _connected(self):
        if not self.account.connected:
            if self.worker and self._choices_request is not None:
                self.worker.cancelQueued(self._choices_request)
            self._choices, self._choices_request = [], None
            if not self.account.profile:
                self._identity = None
                self.editFinished.emit()
            self.changed.emit()
        else:
            identity = (self.account.profile.get("name"), self.account.profile.get("handle"))
            if identity != self._identity and self.shell.page == "Library":
                self.select(self._selected)
            self._identity = identity

    def _navigate(self, page):
        if page == "Library":
            self.select(self._selected)

    def _restore(self):
        if self._pending_move and not self.view.busy:
            pending, self._pending_move = self._pending_move, None
            tracks = self.view.data.get("items", [])
            if self.view.route == "playlist" and self.view.parameters.get("id") == pending[0] and pending[1] < len(tracks) and tracks[pending[1]].get("setVideoId") == pending[2] and not self.view.error:
                self.move(pending[1], 1)
        selected = next((name for name, route in SECTIONS.items() if route == self.view.route), None)
        if selected:
            self._selected = selected
            self._order = next((name for name, order in ORDERS.items() if order == self.view.parameters.get("order")), "Recently added")
            self.changed.emit()

    @Slot(str)
    def select(self, section):
        if section not in SECTIONS:
            return
        self._selected = section
        params = {"order": ORDERS[self._order]}
        if self.fixture:
            songs = [{**track, "kind": "song", "videoId": "fixture0001", "available": True} for shelf in self.fixture.get("shelves", []) for track in shelf.get("items", [])]
            kind = "playlist" if section == "Playlists" else "album" if section == "Albums" else "artist" if section in {"Artists", "Subscriptions"} else "song"
            values = [{**track, "kind": kind, "id": "PLfixture" if kind == "playlist" else "UCfixture" if kind == "artist" else "MPREfixture" if kind == "album" else track["videoId"], "owned": True} for track in songs]
            self.view.showLocal(SECTIONS[section], {"title": section, "items": values, "shelves": [], "cursor": None}, params)
        else:
            self.view.load(SECTIONS[section], params)
        self.changed.emit()

    @Slot(str)
    def sort(self, order):
        if order in ORDERS and order != self._order:
            self._order = order
            self.select(self._selected)

    @Slot()
    def history(self):
        self._selected = "History"
        self.shell.navigate("Library")

    def _action(self, action):
        if action == "newPlaylist":
            self.dialogRequested.emit("playlist_create", {})
        elif action in {"like", "dislike"} and self.player.hasTrack:
            self.rate(self.player.currentTrack, "LIKE" if action == "like" else "DISLIKE")

    @Slot(str, "QVariantMap")
    def edit(self, action, media):
        if action in {"playlist_rename", "playlist_delete"}:
            self.dialogRequested.emit(action, dict(media))

    @Slot(str)
    def create(self, name):
        self.actions.run("playlist_create", {"title": name})

    @Slot(str, str)
    def rename(self, identifier, name):
        self.actions.run("playlist_rename", {"id": identifier, "title": name})

    @Slot(str)
    def removePlaylist(self, identifier):
        self.actions.run("playlist_delete", {"id": identifier})

    @Slot("QVariantMap", str)
    def rate(self, media, rating):
        value = "INDIFFERENT" if media.get("rating") == rating else rating
        self.actions.run("song_rating", {"id": media.get("videoId") or media.get("id"), "value": value})

    @Slot("QVariantMap")
    def saveSong(self, media):
        value = not media.get("inLibrary", False)
        self.actions.run("song_library", {"id": media.get("videoId") or media.get("id"), "value": value, "token": (media.get("libraryTokens") or {}).get("add" if value else "remove"), "albumId": (media.get("album") or {}).get("id")})

    @Slot("QVariantMap")
    def choosePlaylist(self, media):
        self._choices, self._message = [], ""
        if self.fixture:
            self._choices = [{"id": "PLfixture", "title": "Fixture playlist", "owned": True}]
        elif self.account.connected and not self.account.busy:
            self._choices_request = self.worker.request("catalog", {"cache_path": self.cache_path, "route": "library_playlists", "params": {}, "page_size": 100000, "refresh": True})
        self.changed.emit()
        self.chooserRequested.emit(dict(media))

    @Slot(str, "QVariantMap")
    def add(self, playlist, media):
        if self.actions.busy:
            return
        self._adding = dict(media)
        self.actions.run("playlist_add", {"id": playlist, "videoIds": [media.get("videoId") or media.get("id")]})

    @Slot("QVariantMap")
    def removeEntry(self, media):
        self.actions.run("playlist_remove", {"id": self.view.parameters.get("id"), "videoId": media.get("videoId"), "setVideoId": media.get("setVideoId")})

    @Slot(int, int)
    def move(self, index, delta):
        tracks = self.view.data.get("items", [])
        destination = index + delta
        if delta == 1 and 0 <= index < len(tracks) and index + 2 >= len(tracks) and self.view.data.get("cursor") is not None and not self.view.busy:
            self._pending_move = (self.view.parameters.get("id"), index, tracks[index].get("setVideoId"))
            self.view.more()
            return
        if delta not in {-1, 1} or not 0 <= index < len(tracks) or not 0 <= destination < len(tracks):
            return
        successor = tracks[destination].get("setVideoId", "") if delta < 0 else tracks[index + 2].get("setVideoId", "") if index + 2 < len(tracks) else ""
        self.actions.run("playlist_move", {"id": self.view.parameters.get("id"), "setVideoId": tracks[index].get("setVideoId"), "successor": successor})

    @Slot("QVariantMap", int)
    def moveEntry(self, media, delta):
        index = next((index for index, track in enumerate(self.view.data.get("items", [])) if track.get("setVideoId") == media.get("setVideoId")), -1)
        self.move(index, delta)

    def _result(self, identifier, result):
        if identifier == self._choices_request:
            self._choices_request = None
            self._choices = [item for item in result.get("items", []) if item.get("owned")]
            self.changed.emit()

    def _failed(self, identifier, error):
        if identifier == self._choices_request:
            self._choices_request = None
            self._message = error.get("message", "Your playlists could not be loaded. Retry.")
            self.changed.emit()

    def _applied(self, result):
        action, identifier = result["action"], result["id"]
        if action in {"song_rating", "song_library"}:
            values = {"rating" if action == "song_rating" else "inLibrary": result["value"]}
            self.browse.updateTrack(identifier, values)
            self.player.updateTrack(identifier, values)
        if action.startswith("playlist_") and action != "playlist_library":
            self.browse.updatePlaylist(result, self._adding)
            playlists = [dict(item) for item in self.shell.playlists]
            if action == "playlist_create":
                playlists.insert(0, {"id": identifier, "kind": "playlist", "owned": True, "title": result["title"], "owner": self.account.profile.get("name", "Your music")})
            elif action == "playlist_delete":
                playlists = [item for item in playlists if item.get("id") != identifier]
            elif action == "playlist_rename":
                for item in playlists:
                    if item.get("id") == identifier:
                        item["title"] = result["title"]
            self.shell.setPlaylists(playlists)
            QTimer.singleShot(2000, self.browse.refreshPlaylists)
            if action == "playlist_create":
                self.browse.showCollection({"kind": "playlist", "id": identifier, "title": result["title"], "author": self.account.profile.get("name", "Your music"), "privacy": "PRIVATE", "editable": True, "items": [], "shelves": [], "trackCount": 0, "cursor": None})
            elif action == "playlist_delete":
                self.browse.forgetPlaylist(identifier)
                self.select("Playlists")
            elif self.view.route == "playlist" and self.view.parameters.get("id") == identifier:
                if action == "playlist_add" and not result.get("addedEntries") and not self.fixture:
                    QTimer.singleShot(2000, lambda: self.view.refresh() if self.view.route == "playlist" and self.view.parameters.get("id") == identifier else None)
            elif self.view.route == "library_playlists" and not self.fixture:
                QTimer.singleShot(2000, lambda: self.view.refresh() if self.view.route == "library_playlists" else None)
            self.editFinished.emit()
