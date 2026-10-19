"""Connect native catalog views to navigation and playback, without network work."""

from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot

from .playlist_ops import apply_change
from .queue_additions import QueueAdditions


class Browse(QObject):
    changed = Signal()

    def __init__(self, shell, account, view, player, cache_path, fixture=None, parent=None, downloads=None):
        super().__init__(parent)
        self.shell, self.account, self.view, self.player = shell, account, view, player
        self.worker, self.cache_path, self.fixture = account.worker, str(cache_path), fixture
        self._play_request, self._play_route, self._play_params = None, "", {}
        self._play_title = ""
        self._artist_request, self._artist_name = None, ""
        self._metadata_request, self._metadata_video_id, self._metadata_fallback_query = None, "", ""
        self._metadata_fallback_attempted = False
        self._metadata_track_id = ""
        self._mood_request, self._mood_title = None, ""
        self._playlist_request = None
        self._identity = None
        self._message = ""
        self._history, self._play_shuffle = [], False
        self.downloads, self._download_request = downloads, None
        self._download_open_request = None
        self.additions = QueueAdditions(account, player, cache_path, downloads, fixture, self)
        self.additions.changed.connect(self.changed)
        if downloads:
            downloads.collectionFound.connect(self._download_result)
            downloads.collectionReady.connect(self.openDownloaded)
            downloads.playRequested.connect(self.playCollection)
        shell.navigationRequested.connect(self.navigate)
        shell.pageChanged.connect(self._cancel_local_navigation)
        view.navigationStarted.connect(self._cancel_local_navigation)
        shell.actionRequested.connect(self._action)
        player_changed = getattr(player, "changed", None)
        if player_changed:
            player_changed.connect(self._player_changed)
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

    @Property(bool, notify=changed)
    def queueBusy(self):
        return bool(self.additions.jobs)

    @Property(str, notify=changed)
    def queueMessage(self):
        return "Adding to queue…" if self.queueBusy and not self.additions.message else self.additions.message

    @Slot("QVariantMap", bool)
    def enqueue(self, media, next=False):
        self.additions.add(media, next)

    def _cancel_play_pages(self):
        if self.downloads:
            self.downloads.cancelLookup(self._download_request)
        self._download_request = None
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
        self._history.append({**self.view.snapshot(), "page": self.shell.page, "query": self.shell.query})
        self._history = self._history[-20:]

    def _load(self, route, params):
        self._remember()
        self.view.load(route, params)

    def showCollection(self, collection):
        self.shell.setExpanded(False)
        self._remember()
        self.view.showLocal(collection["kind"], collection, {"id": collection["id"]})

    def openDownloaded(self, collection):
        if collection["kind"] == "song":
            self.playItems(collection["items"])
        else:
            self.showCollection(collection)

    def _cancel_local_navigation(self):
        if self.downloads:
            self.downloads.cancelOpen()
            self.downloads.cancelLookup(self._download_open_request)
        self._download_open_request = None
        if self.worker and self._artist_request is not None:
            self.worker.cancelQueued(self._artist_request)
        self._artist_request = None

    @Slot()
    def back(self):
        if not self._history:
            return
        self.shell.setExpanded(False)
        self._cancel_local_navigation()
        self._cancel_mood()
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
            if not self.view.data.get("downloadKey") and self.view.route != "downloads":
                self.view.showLocal("home", {"items": [], "shelves": []})
            self.shell.setPlaylists([])
            return
        if self.account.connected and identity != self._identity:
            self._identity = identity
            self.navigate(self.shell.page)
            self.refreshPlaylists()

    def refreshPlaylists(self):
        if self.worker and self.account.connected:
            self._playlist_request = self.worker.request("catalog", {"cache_path": self.cache_path, "route": "library_playlists", "params": {}, "page_size": 100000})

    def _action(self, action):
        if action.startswith("playlist:"):
            self._cancel_local_navigation()
            if self.shell.page == "Downloads":
                self.shell.restoreNavigation("Library", self.shell.query)
            if self.fixture:
                media = next((value for value in self.shell.playlists if value["id"] == action.split(":", 1)[1]), {})
                self.open({**media, "id": action.split(":", 1)[1], "kind": "playlist"})
            else:
                self.open({"kind": "playlist", "id": action.split(":", 1)[1]})

    @Slot(str)
    def navigate(self, page):
        self._cancel_local_navigation()
        self._history = []
        if page == "Downloads":
            self.view.showLocal("downloads", {})
            if self.downloads:
                self.downloads.refresh()
            return
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
        self.shell.setExpanded(False)
        self._cancel_local_navigation()
        self._cancel_mood()
        kind = media.get("kind", "song")
        if kind == "song":
            self.play(media)
        elif not self.fixture:
            if self.downloads and kind in {"album", "playlist"}:
                self._open_media = dict(media)
                self._download_open_request = self.downloads.lookup(kind, media.get("id", ""))
            else:
                self._load(kind, {"id": media.get("id", "")})
        else:
            self._remember()
            songs = [{**value, "kind": "song", "duration": 180} for value in self.fixture.get("shelves", [{}])[0].get("items", [])]
            if kind == "artist":
                data = {"title": media.get("title", "Fixture artist"), "subtitle": "A fixture artist and their music, created for native layout verification.", "monthlyListeners": "2.7M", "subscribers": "41K", "subscriptionId": "UCfixture", "shuffleId": "fixture", "radioId": "fixture", "shelves": [{"title": "Top songs", "items": songs}, {"title": "Albums", "items": [{**value, "kind": "album", "id": "MPREfixture"} for value in songs]}]}
            else:
                data = {"title": media.get("title", "Fixture album"), "thumbnail": media.get("thumbnail") or (songs[0].get("thumbnail", "") if songs else ""), "subtitle": "A collection for quiet mornings and late nights.", "duration": len(songs) * 180, "items": [{**song, "album": {"name": "Evening sessions", "id": "MPREfixture"}} for song in songs], "artists": [{"id": "UCfixture", "name": "Fixture artist"}], "year": "2026", "trackCount": len(songs), "audioPlaylistId": "OLAKfixture", "shelves": []}
                if kind == "playlist":
                    data.update(editable=True, author="Your music", privacy="PRIVATE", items=[{**song, "setVideoId": "entry-" + str(index)} for index, song in enumerate(data["items"])])
            self.view.showLocal(kind, data, {"id": media.get("id", "fixture")})

    @Slot("QVariantMap")
    def openArtist(self, artist):
        identifier = artist.get("id") or artist.get("browseId") or artist.get("channelId")
        name = str(artist.get("name") or "").strip()
        if identifier:
            self.open({"kind": "artist", "id": identifier, "title": name})
        elif name and self.fixture:
            self.open({"kind": "artist", "id": "UCfixture", "title": name})
        elif name and self.worker:
            if self._artist_request is not None:
                self.worker.cancelQueued(self._artist_request)
            self._artist_name = name
            self._artist_request = self.worker.request("catalog", {"cache_path": self.cache_path, "route": "search", "params": {"query": name, "filter": "artists"}})

    @Slot("QVariantMap")
    def play(self, media):
        self.playCollection(media, False)

    @Slot("QVariantMap", bool)
    def playCollection(self, media, shuffle):
        self._cancel_play_pages()
        self._play_shuffle = shuffle
        self._play_title = media.get("title", "")
        kind = media.get("kind", "song")
        if kind == "song":
            self.player.play(media)
        elif self.fixture:
            if kind in {"album", "playlist"}:
                tracks = [{**track, "kind": "song", "duration": 180} for track in self.fixture.get("shelves", [{}])[0].get("items", [])]
                self.player.playShuffledTracks(tracks, source_label=self._play_title) if shuffle else self.player.playTracks(tracks, source_label=self._play_title)
        elif kind in {"album", "playlist"}:
            self._play_route, self._play_params = kind, {"id": media.get("id", "")}
            if self.downloads:
                self._download_request = self.downloads.lookup(kind, media.get("id", ""))
            else:
                self._request_play_page()
        else:
            self._load("artist", {"id": media.get("id", "")})

    def _download_result(self, identifier, collection):
        if identifier == self._download_open_request:
            self._download_open_request = None
            if collection:
                self.showCollection(collection)
            else:
                self._load(self._open_media["kind"], {"id": self._open_media.get("id", "")})
        elif identifier == self._download_request:
            self._download_request = None
            if collection:
                tracks = collection.get("items", [])
                if tracks:
                    title = collection.get("title") or self._play_title
                    self.player.playShuffledTracks(tracks, source_label=title) if self._play_shuffle else self.player.playTracks(tracks, source_label=title)
            else:
                self._request_play_page()

    def _request_play_page(self, offset=0):
        params = {**self._play_params, **({"allTracks": True} if self._play_route == "album" else {})}
        self._play_request = self.worker.request("catalog", {"cache_path": self.cache_path, "route": self._play_route, "params": params, "offset": offset})
        self._play_offset = offset

    def _lookup_track_metadata(self, media):
        track_id = media.get("videoId") or media.get("id", "")
        album = media.get("album")
        if not self.worker or not track_id or (
            isinstance(album, dict) and album.get("name")
            or isinstance(album, str) and album.strip()
        ):
            return
        if self._metadata_request is not None:
            self.worker.cancelQueued(self._metadata_request)
        query = str(media.get("title", "")).strip()
        if not query:
            return
        self._metadata_video_id = track_id
        self._metadata_fallback_attempted = False
        artist_names = " ".join(artist.get("name", "") for artist in media.get("artists", []) if isinstance(artist, dict))
        self._metadata_fallback_query = " ".join((query, artist_names)).strip() if artist_names else ""
        self._metadata_request = self.worker.request("catalog", {"cache_path": self.cache_path, "route": "search", "params": {"query": query, "filter": "songs"}})

    def _player_changed(self):
        track = self.player.currentTrack
        track_id = track.get("videoId") or track.get("id", "")
        if track_id != self._metadata_track_id:
            self._metadata_track_id = track_id
            self._lookup_track_metadata(track)

    def _result(self, identifier, result):
        if identifier == self._metadata_request:
            self._metadata_request = None
            track = next((item for item in result.get("items", []) if item.get("videoId") == self._metadata_video_id), None)
            album = track.get("album") if track else None
            if (not track or not (isinstance(album, dict) and album.get("name"))) and self._metadata_fallback_query and not self._metadata_fallback_attempted:
                self._metadata_fallback_attempted = True
                self._metadata_request = self.worker.request("catalog", {"cache_path": self.cache_path, "route": "search", "params": {"query": self._metadata_fallback_query, "filter": "songs"}})
                return
            if track:
                values = {}
                if isinstance(album, dict) and album.get("name"):
                    values["album"] = album
                if track.get("artists"):
                    values["artists"] = track["artists"]
                if track.get("thumbnail"):
                    values["thumbnail"] = track["thumbnail"]
                if track.get("largeThumbnail"):
                    values["largeThumbnail"] = track["largeThumbnail"]
                if not values:
                    return
                self.player.updateTrack(self._metadata_video_id, values)
                self.updateTrack(self._metadata_video_id, values)
        elif identifier == self._artist_request:
            self._artist_request = None
            artist = next((item for item in result.get("items", []) if item.get("kind") == "artist" and item.get("title", "").casefold() == self._artist_name.casefold()), None)
            if artist and artist.get("id"):
                self.open(artist)
            else:
                self._load("search", {"query": self._artist_name, "filter": "artists"})
        elif identifier == self._playlist_request:
            self._playlist_request = None
            self.shell.setPlaylists([{**media, "owner": self.account.profile.get("name", "Your music")} for media in result.get("items", [])])
        elif identifier == self._play_request:
            self._play_request = None
            tracks = [track for track in result.get("items", []) if track.get("kind") == "song"]
            if self._play_offset:
                self.player.appendContext(tracks)
            elif tracks:
                title = result.get("title") or self._play_title
                self.player.playShuffledTracks(tracks, source_label=title) if self._play_shuffle else self.player.playTracks(tracks, source_label=title)
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
        if identifier == self._metadata_request:
            self._metadata_request = None
        if identifier == self._artist_request:
            self._artist_request = None
            self._load("search", {"query": self._artist_name, "filter": "artists"})
        if identifier == self._play_request:
            self._play_request = None
            self._message = error.get("message", "This collection could not be played. Retry.")
            self.changed.emit()
        if identifier == self._mood_request:
            self._mood_request = None
            self.view.load("moods", {})

    @Slot("QVariantList")
    def playItems(self, values, source_label=""):
        self._cancel_play_pages()
        songs = [dict(value) for value in values if value.get("kind", "song") == "song"]
        if songs:
            self.player.playTracks(songs, source_label=source_label)

    @Slot()
    def playView(self):
        if self.view.data.get("downloadKey"):
            self.playItems(self.view.data.get("items", []), self.view.data.get("title", ""))
        elif self.view.route in {"album", "playlist"} and not self.fixture:
            self.play({"kind": self.view.route, "id": self.view.parameters.get("id", ""), "title": self.view.data.get("title", "")})
        else:
            self.playItems(self.view.data.get("items", []), self.view.data.get("title", ""))

    @Slot()
    def shuffleView(self):
        if self.view.route in {"album", "playlist"} and not self.fixture and not self.view.data.get("downloadKey"):
            self.playCollection({"kind": self.view.route, "id": self.view.parameters.get("id", ""), "title": self.view.data.get("title", "")}, True)
        else:
            self._cancel_play_pages()
            self.player.playShuffledTracks(self.view.data.get("items", []), source_label=self.view.data.get("title", ""))

    @Slot(str, bool)
    def startRadio(self, identifier, shuffle):
        self._cancel_play_pages()
        self._play_title = (self.view.data.get("title", "") + " radio").strip()
        if self.fixture:
            self.player.playTracks(self.fixture.get("shelves", [{}])[0].get("items", []), source_label=self._play_title)
            return
        self._play_shuffle = False
        self._play_route, self._play_params = "radio", {"playlistId": identifier, "shuffle": shuffle}
        self._request_play_page()

    @Slot(str)
    def startRadioForSong(self, identifier):
        self._cancel_play_pages()
        self._play_title = "Radio"
        self._play_shuffle = False
        self._play_route, self._play_params = "radio", {"id": identifier, "radio": True}
        if self.fixture:
            self.player.playTracks(self.fixture.get("shelves", [{}])[0].get("items", []), source_label=self._play_title)
        else:
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
        if result["action"] not in {"artist_subscription", "album_library", "playlist_library"}:
            return
        field = "subscribed" if result["action"] == "artist_subscription" else "saved"
        context = result.get("contextId")
        if self.view.parameters.get("id") == context:
            self.view.patch({field: result["value"]})
        for page in self._history:
            if page["params"].get("id") == context:
                page["data"][field] = result["value"]

    def updateTrack(self, identifier, values):
        for data in [self.view.data] + [page["data"] for page in self._history]:
            tracks = list(data.get("items", []))
            tracks.extend(track for section in data.get("shelves", []) for track in section.get("items", []))
            for track in tracks:
                if track.get("videoId") == identifier:
                    track.update(values)
        self.view.patch({})

    def forgetPlaylist(self, identifier):
        self._history = [page for page in self._history if not (page["route"] == "playlist" and page["params"].get("id") == identifier)]
        for page in self._history:
            if page["route"] == "library_playlists":
                page["data"]["items"] = [item for item in page["data"].get("items", []) if item.get("id") != identifier]

    def updatePlaylist(self, result, added=None):
        for page in [self.view.snapshot()] + self._history:
            collection_id = page["params"].get("id") if page["route"] == "playlist" else None
            apply_change(page["data"], result, collection_id, added)
        self.view.patch({})

    @Slot(int)
    def playAt(self, index):
        self._cancel_play_pages()
        self.player.playTracks(self.view.data.get("items", []), index, source_label=self.view.data.get("title", ""))
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
