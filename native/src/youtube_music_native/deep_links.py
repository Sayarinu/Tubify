"""Validated music links and preview actions using the existing player commands."""

import re
import time
from urllib.parse import parse_qs, urlencode, urlsplit

from PySide6.QtCore import QObject, Property, Signal, Slot

SCHEME = "ytmusic-native"
HOSTS = {"music.youtube.com", "www.youtube.com", "youtube.com", "m.youtube.com", "youtu.be"}


class LinkError(ValueError):
    pass


def parse_link(value):
    if not isinstance(value, str) or len(value) > 4096 or any(ord(char) <= 32 or ord(char) == 127 for char in value):
        raise LinkError("Use a valid YouTube Music song, playlist, album or artist link.")
    action = "open"
    try:
        outer = urlsplit(value)
        if outer.scheme == SCHEME:
            query = parse_qs(outer.query, keep_blank_values=True, max_num_fields=8)
            if outer.netloc not in {"open", "play", "queue"} or outer.path not in {"", "/"} or outer.fragment or set(query) != {"url"} or len(query["url"]) != 1:
                raise ValueError()
            action, value = outer.netloc, query["url"][0]
        parts = urlsplit(value)
        if len(value) > 4096 or any(ord(char) <= 32 or ord(char) == 127 for char in value) or parts.scheme != "https" or parts.hostname not in HOSTS or parts.username or parts.password or parts.port not in {None, 443} or parts.fragment:
            raise ValueError()
        query = parse_qs(parts.query, keep_blank_values=True, max_num_fields=30)
        if parts.hostname == "youtu.be":
            kind, identifier = "song", parts.path.lstrip("/")
        elif parts.path == "/watch":
            kind, identifier = "song", query.get("v", [""])[0]
            if len(query.get("v", [])) != 1:
                raise ValueError()
        elif parts.path == "/playlist":
            kind, identifier = "playlist", query.get("list", [""])[0]
            if len(query.get("list", [])) != 1:
                raise ValueError()
        elif parts.path.startswith(("/channel/", "/browse/")):
            identifier = parts.path.rsplit("/", 1)[-1]
            if parts.path not in {"/channel/" + identifier, "/browse/" + identifier}:
                raise ValueError()
            kind = "artist" if identifier.startswith("UC") else "album" if identifier.startswith("MPRE") and parts.path.startswith("/browse/") else ""
        else:
            raise ValueError()
        pattern = {"song": r"[A-Za-z0-9_-]{11}", "playlist": r"[A-Za-z0-9_-]{2,200}", "artist": r"UC[A-Za-z0-9_-]{22}", "album": r"MPRE[A-Za-z0-9_-]{1,196}"}.get(kind)
        if not pattern or not re.fullmatch(pattern, identifier):
            raise ValueError()
    except (ValueError, TypeError, KeyError):
        raise LinkError("Use a valid YouTube Music song, playlist, album or artist link.") from None
    suffix = "/watch?" + urlencode({"v": identifier}) if kind == "song" else "/playlist?" + urlencode({"list": identifier}) if kind == "playlist" else "/channel/" + identifier if kind == "artist" else "/browse/" + identifier
    return {"action": action, "kind": kind, "id": identifier, "url": "https://music.youtube.com" + suffix}


class DeepLinks(QObject):
    changed = Signal()
    previewRequested = Signal()
    activateRequested = Signal()

    def __init__(self, browse, account, downloads, cache_path, parent=None, clock=time.monotonic, fixture=False):
        super().__init__(parent)
        self.browse, self.account, self.downloads = browse, account, downloads
        self.worker, self.cache_path, self.clock, self.fixture = account.worker, str(cache_path), clock, fixture
        self._link, self._media, self._message, self._busy = {}, {}, "", False
        self._lookup, self._request, self._recent = None, None, {}
        self._action = "open"
        self._loaded = False
        if downloads:
            downloads.collectionFound.connect(self._local)
        if self.worker:
            self.worker.succeeded.connect(self._result)
            self.worker.failed.connect(self._failed)

    @Property("QVariantMap", notify=changed)
    def media(self):
        return self._media

    @Property(str, notify=changed)
    def url(self):
        return self._link.get("url", "")

    @Property(str, notify=changed)
    def message(self):
        return self._message

    @Property(bool, notify=changed)
    def busy(self):
        return self._busy

    @Property(bool, notify=changed)
    def canPlay(self):
        return self._loaded and bool(self._media) and self._media.get("kind") != "artist"

    @Slot(str)
    def receive(self, url):
        self.activateRequested.emit()
        try:
            link = parse_link(url)
        except LinkError as error:
            self._message, self._link, self._media, self._busy = str(error), {}, {}, False
            self._cancel()
            self.changed.emit()
            self.previewRequested.emit()
            return
        now = self.clock()
        key = (link["action"], link["url"])
        self._recent = {key: stamp for key, stamp in self._recent.items() if now - stamp < 2}
        if key in self._recent:
            return
        self._recent[key] = now
        if len(self._recent) > 32:
            self._recent.pop(next(iter(self._recent)))
        self._cancel()
        self._loaded = False
        self._link, self._action = link, link["action"]
        self._media = {"kind": link["kind"], "id": link["id"], "title": link["kind"].title() + " link"}
        if link["kind"] == "song":
            self._media["videoId"] = link["id"]
        self._message, self._busy = "Loading details…", True
        self.changed.emit()
        self.previewRequested.emit()
        if self.downloads and link["kind"] in {"song", "album", "playlist"}:
            self._lookup = self.downloads.lookup(link["kind"], link["id"])
            if self._lookup is None:
                self._fetch()
        else:
            self._fetch()

    def _cancel(self):
        if self._lookup is not None and self.downloads:
            self.downloads.cancelLookup(self._lookup)
        if self._request is not None and self.worker:
            self.worker.cancelQueued(self._request)
        self._lookup, self._request = None, None

    def _local(self, identifier, collection):
        if identifier != self._lookup or self._lookup is None:
            return
        self._lookup = None
        if collection:
            if self._link["kind"] == "song":
                track = next((row for row in collection.get("items", []) if row.get("videoId") == self._link["id"]), None)
                if track:
                    self._accept(track)
                    return
            else:
                self._accept({**collection, "kind": self._link["kind"], "id": self._link["id"]})
                return
        self._fetch()

    def _fetch(self):
        if self.fixture:
            self._accept({**self._media, "title": "Shared fixture " + self._link["kind"], "artist": "Fixture artist", "duration": 180})
        elif self.worker:
            route = "radio" if self._link["kind"] == "song" else self._link["kind"]
            self._request = self.worker.request("catalog", {"cache_path": self.cache_path, "route": route, "params": {"id": self._link["id"], **({"radio": False} if route == "radio" else {})}})
        else:
            self._failed(None, {})

    def _result(self, identifier, result):
        if identifier != self._request or self._request is None:
            return
        self._request = None
        if self._link["kind"] == "song":
            track = next((row for row in result.get("items", []) if row.get("videoId") == self._link["id"]), None)
            if track is None:
                self._failed(None, {})
                return
            self._accept(track)
        else:
            self._accept({**self._media, **result, "kind": self._link["kind"], "id": self._link["id"]})

    def _accept(self, media):
        self._media, self._busy, self._message = dict(media), False, ""
        self._loaded = True
        self.changed.emit()
        action, self._action = self._action, "open"
        if action != "open":
            self.perform(action)

    def _failed(self, identifier, error):
        if identifier is not None and identifier != self._request:
            return
        self._request, self._busy = None, False
        self._message = "Details are unavailable. Connect your account or retry. Downloaded music remains available."
        # Failure never turns an external preview into an unintended playback request.
        self._action = "open"
        self.changed.emit()

    @Slot()
    def retry(self):
        if self._link and not self._busy:
            self._busy, self._message = True, "Loading details…"
            self.changed.emit()
            self._fetch()

    @Slot(str)
    def perform(self, action):
        if action not in {"open", "play", "queue"} or not self._media or self._busy:
            return
        if action == "open":
            if self._media["kind"] != "song":
                self.browse.open(self._media)
        elif self._media["kind"] == "artist":
            self._message = "Open this artist to choose a song or collection to play or queue."
        elif not self.canPlay:
            return
        elif action == "play":
            self.browse.play(self._media)
            self._message = "Playback requested."
        else:
            self.browse.enqueue(self._media)
            self._message = "Adding collection to queue…" if self.browse.queueBusy else "Added to your queue."
        self.changed.emit()

    def close(self):
        self._cancel()
