"""Connect native catalog views to navigation and playback, without network work."""

from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot


class Browse(QObject):
    changed = Signal()

    def __init__(self, shell, account, view, player, cache_path, fixture=None, parent=None):
        super().__init__(parent)
        self.shell, self.account, self.view, self.player = shell, account, view, player
        self.worker, self.cache_path, self.fixture = account.worker, str(cache_path), fixture
        self._play_request, self._play_route, self._play_params = None, "", {}
        self._mood_request, self._mood_title = None, ""
        self._playlist_request = None
        self._identity = None
        self._message = ""
        self._history, self._play_shuffle = [], False
        shell.navigationRequested.connect(self.navigate)
        shell.actionRequested.connect(self._action)
        account.connectedChanged.connect(self._account_changed)
        account.sessionChanged.connect(player.resetSession)
        if self.worker:
            self.worker.succeeded.connect(self._result)
            self.worker.failed.connect(self._failed)
        if fixture:
            QTimer.singleShot(0, lambda: self.navigate("Home"))

    @Property(str, notify=changed)
    def message(self):
        return self._message

    def _cancel_play_pages(self):
        if self.worker and self._play_request is not None:
            self.worker.cancelQueued(self._play_request)
        self._play_request = None
        self._message = ""
        self.changed.emit()

    def _cancel_mood(self):
        if self.worker and self._mood_request is not None:
            self.worker.cancelQueued(self._mood_request)
        self._mood_request = None

    def _remember(self):
        if self.view.data:
            self._history.append({**self.view.snapshot(), "page": self.shell.page, "query": self.shell.query})
            self._history = self._history[-20:]

    def _load(self, route, params):
        self._remember()
        self.view.load(route, params)

    @Slot()
    def back(self):
        self._cancel_mood()
        if not self._history:
            self.navigate(self.shell.page)
            return
        previous = self._history.pop()
        self.shell.restoreNavigation(previous["page"], previous["query"])
        self.view.showLocal(previous["route"], previous["data"], previous["params"], previous["scroll"])

    def _account_changed(self):
        identity = (self.account.profile.get("name"), self.account.profile.get("handle"))
        if not self.account.profile:
            self._identity = None
            self._cancel_play_pages()
            self._cancel_mood()
            if self.worker and self._playlist_request is not None:
                self.worker.cancelQueued(self._playlist_request)
            self._playlist_request = None
            self.view.showLocal("home", {"items": [], "shelves": []})
            self.shell.setPlaylists([])
            return
        if self.account.connected and identity != self._identity:
            self._identity = identity
            self.navigate(self.shell.page)
            self._playlist_request = self.worker.request("catalog", {"cache_path": self.cache_path, "route": "library_playlists", "params": {}})

    def _action(self, action):
        if action.startswith("playlist:"):
            if self.shell.page not in {"Home", "Explore"}:
                self.shell.navigate("Home")
            if self.fixture:
                title = next((value["title"] for value in self.shell.playlists if value["id"] == action.split(":", 1)[1]), "Playlist")
                self.showShelf({"title": title, "items": self.fixture.get("shelves", [{}])[0].get("items", [])})
            else:
                self.view.load("playlist", {"id": action.split(":", 1)[1]})

    @Slot(str)
    def navigate(self, page):
        self._history = []
        if page not in {"Home", "Explore"}:
            return
        self._cancel_mood()
        if self.fixture:
            sections = self.fixture.get("shelves", [])
            if page == "Explore":
                sections = [{**section, "title": "New albums & singles" if index == 0 else "Top songs", "items": [{**media, "kind": "album" if index == 0 else "song"} for media in section.get("items", [])]} for index, section in enumerate(sections)]
            self.view.showLocal(page.lower(), {"title": page, "shelves": sections, "items": [], "moods": [{"title": title, "params": title} for title in ("Chill", "Focus", "Workout", "Party")]})
        else:
            self.view.load(page.lower(), {})

    @Slot("QVariantMap")
    def open(self, media):
        self._cancel_mood()
        kind = media.get("kind", "song")
        if kind == "song":
            self.play(media)
        elif not self.fixture:
            self._load(kind, {"id": media.get("id", "")})
        else:
            self._remember()
            songs = [{**value, "kind": "song", "duration": 180} for value in self.fixture.get("shelves", [{}])[0].get("items", [])]
            if kind == "artist":
                data = {"title": media.get("title", "Fixture artist"), "subtitle": "A fixture artist and their music, created for native layout verification.", "monthlyListeners": "2.7M", "subscribers": "41K", "subscriptionId": "UCfixture", "shuffleId": "fixture", "radioId": "fixture", "shelves": [{"title": "Top songs", "items": songs}, {"title": "Albums", "items": [{**value, "kind": "album", "id": "MPREfixture"} for value in songs]}]}
            else:
                data = {"title": media.get("title", "Fixture album"), "items": songs, "artists": [{"id": "UCfixture", "name": "Fixture artist"}], "year": "2026", "trackCount": len(songs), "audioPlaylistId": "OLAKfixture", "shelves": []}
            self.view.showLocal(kind, data, {"id": media.get("id", "fixture")})

    @Slot("QVariantMap")
    def play(self, media):
        self._cancel_play_pages()
        self._play_shuffle = False
        kind = media.get("kind", "song")
        if kind == "song" or self.fixture:
            self.player.play(media)
        elif kind in {"album", "playlist"}:
            self._play_route, self._play_params = kind, {"id": media.get("id", "")}
            self._request_play_page()
        else:
            self._load("artist", {"id": media.get("id", "")})

    def _request_play_page(self, offset=0):
        params = {**self._play_params, **({"allTracks": True} if self._play_route == "album" else {})}
        self._play_request = self.worker.request("catalog", {"cache_path": self.cache_path, "route": self._play_route, "params": params, "offset": offset})
        self._play_offset = offset

    def _result(self, identifier, result):
        if identifier == self._playlist_request:
            self._playlist_request = None
            self.shell.setPlaylists([{**media, "owner": self.account.profile.get("name", "Your music")} for media in result.get("items", [])])
        elif identifier == self._play_request:
            self._play_request = None
            tracks = [track for track in result.get("items", []) if track.get("kind") == "song"]
            if self._play_offset:
                self.player.enqueue(tracks)
            elif tracks:
                self.player.playShuffledTracks(tracks) if self._play_shuffle else self.player.playTracks(tracks)
            if result.get("cursor") is not None:
                self._request_play_page(result["cursor"])
        elif identifier == self._mood_request:
            self._mood_request = None
            groups = result.get("groups", {})
            for values in groups.values():
                for value in values:
                    if value.get("title", "").casefold() == self._mood_title.casefold():
                        self.mood(value)
                        return
            self.view.showLocal("moods", result)

    def _failed(self, identifier, error):
        if identifier == self._play_request:
            self._play_request = None
            self._message = error.get("message", "This collection could not be played. Retry.")
            self.changed.emit()
        if identifier == self._mood_request:
            self._mood_request = None
            self.view.load("moods", {})

    @Slot("QVariantList")
    def playItems(self, values):
        self._cancel_play_pages()
        songs = [dict(value) for value in values if value.get("kind", "song") == "song"]
        if songs:
            self.player.playTracks(songs)

    @Slot()
    def playView(self):
        if self.view.route in {"album", "playlist"} and not self.fixture:
            self.play({"kind": self.view.route, "id": self.view.parameters.get("id", "")})
        else:
            self.playItems(self.view.data.get("items", []))

    @Slot()
    def shuffleView(self):
        if self.view.route in {"album", "playlist"} and not self.fixture:
            self.play({"kind": self.view.route, "id": self.view.parameters.get("id", "")})
            self._play_shuffle = True
        else:
            self._cancel_play_pages()
            self.player.playShuffledTracks(self.view.data.get("items", []))

    @Slot(str, bool)
    def startRadio(self, identifier, shuffle):
        self._cancel_play_pages()
        if self.fixture:
            self.player.playTracks(self.fixture.get("shelves", [{}])[0].get("items", []))
            return
        self._play_shuffle = False
        self._play_route, self._play_params = "radio", {"playlistId": identifier, "shuffle": shuffle}
        self._request_play_page()

    @Slot("QVariantMap")
    def openSection(self, section):
        if section.get("params") and section.get("browseId"):
            self._load("artist_albums", {"id": section["browseId"], "params": section["params"], "title": section.get("title", "Albums")})
        elif section.get("browseId"):
            self._load("playlist", {"id": section["browseId"]})
        else:
            self.showShelf(section)

    def applyAction(self, result):
        field = "subscribed" if result["action"] == "artist_subscription" else "saved"
        context = result.get("contextId")
        if self.view.parameters.get("id") == context:
            self.view.patch({field: result["value"]})
        for page in self._history:
            if page["params"].get("id") == context:
                page["data"][field] = result["value"]

    @Slot(int)
    def playAt(self, index):
        self._cancel_play_pages()
        self.player.playTracks(self.view.data.get("items", []), index)
        cursor = self.view.data.get("cursor")
        if cursor is not None and self.view.route in {"album", "playlist"}:
            self._play_route, self._play_params = self.view.route, self.view.parameters
            self._request_play_page(cursor)

    @Slot("QVariantMap")
    def showShelf(self, section):
        self._cancel_mood()
        self._remember()
        self.view.showLocal("shelf", {"title": section.get("title", ""), "items": section.get("items", []), "shelves": [], "cursor": None})

    @Slot(str)
    def shortcut(self, action):
        self._cancel_mood()
        if self.fixture and action == "charts":
            sections = self.fixture.get("shelves", [])
            self.view.showLocal("charts", {"title": "Charts", "shelves": [{**sections[-1], "title": "Top songs"}], "items": []})
            return
        if self.fixture and action == "moods":
            self.view.showLocal("moods", {"title": "Moods & genres", "groups": {"Moods": [{"title": title, "params": title} for title in ("Chill", "Focus", "Workout", "Party")]}})
            return
        if action == "charts":
            self._load("charts", {})
        elif action == "moods":
            self._load("moods", {})
        elif action == "releases":
            sections = self.view.data.get("shelves", [])
            if sections:
                self.showShelf(sections[0])

    @Slot(str)
    def homeMood(self, title):
        if self.fixture:
            self.showShelf({"title": title, "items": self.fixture.get("shelves", [{}])[0].get("items", [])})
        elif self.worker:
            self._mood_title = title
            self._mood_request = self.worker.request("catalog", {"cache_path": self.cache_path, "route": "moods", "params": {}})

    @Slot("QVariantMap")
    def mood(self, value):
        if self.fixture:
            self.homeMood(value.get("title", ""))
        else:
            self._load("mood", {"params": value.get("params", ""), "title": value.get("title", "Mood")})
