"""Normalize provider variants, page results and reuse metadata when offline."""

import hashlib
import json
import sqlite3
import time

from .artwork_sources import variants, apply_artwork, media_variants
from .playlist_ops import apply_change


class CatalogError(RuntimeError):
    pass


def text(value):
    return value if isinstance(value, str) else ""


def thumbnail(value, largest=False):
    if isinstance(value, dict):
        value = value.get("thumbnails", [])
    if not isinstance(value, list):
        return ""
    choices = [v for v in value if isinstance(v, dict) and text(v.get("url")).startswith("https://")]
    if not choices:
        return ""
    if largest:
        choice = max(choices, key=lambda v: (v.get("width") or 0) * (v.get("height") or v.get("width") or 0))
    else:
        choice = min(choices, key=lambda v: abs((v.get("width") or 300) - 300))
    return choice["url"]


def duration(value):
    try:
        if isinstance(value, str) and ":" in value:
            seconds = 0
            for part in value.split(":"):
                seconds = seconds * 60 + int(part)
            return max(0, seconds)
        return max(0, int(value or 0))
    except (ValueError, TypeError):
        return 0


def item(row, kind=None):
    if not isinstance(row, dict):
        return None
    video = text(row.get("videoId"))
    browse = text(row.get("browseId"))
    playlist = text(row.get("playlistId"))
    result_type = text(row.get("resultType") or row.get("type")).lower()
    if video:
        kind = "song"
    elif result_type in {"artist", "album"}:
        kind = result_type
    elif result_type.endswith("playlist") or browse.startswith("VL"):
        kind = "playlist"
    elif not kind:
        kind = "artist" if browse.startswith("UC") else "album" if browse.startswith("MPRE") else "playlist"
    identifier = video if kind == "song" else (browse or playlist) if kind in {"album", "artist"} else playlist or browse
    title = text(row.get("title") or row.get("name") or (row.get("artist") if kind == "artist" else ""))
    if kind == "artist" and (not title or not identifier):
        # Search's top-result artist card carries its name and channel only in artists[0].
        lead = next((a for a in row.get("artists") or [] if isinstance(a, dict) and a.get("name")), {})
        title = title or text(lead.get("name"))
        identifier = identifier or text(lead.get("id") or lead.get("browseId"))
    if not title and row.get("isAvailable") is False:
        title = "Unavailable song"
    if not title:
        return None
    artists = [a for a in (row.get("artists") or []) if isinstance(a, dict) and isinstance(a.get("name"), str)]
    author = row.get("author")
    if not artists and isinstance(author, dict):
        artists = [{"name": text(author.get("name")), "id": text(author.get("id"))}]
    elif not artists and isinstance(author, list):
        artists = [a for a in author if isinstance(a, dict) and isinstance(a.get("name"), str)]
    author_values = [author] if isinstance(author, dict) else author if isinstance(author, list) else []
    author_ids = {text(a.get("name")).casefold(): text(a.get("id") or a.get("browseId") or a.get("channelId")) for a in author_values if isinstance(a, dict)}
    raw_album = row.get("album")
    album = raw_album if isinstance(raw_album, dict) else {"name": raw_album} if isinstance(raw_album, str) else {}
    return {
        "kind": kind, "id": identifier, "videoId": video, "browseId": browse, "playlistId": playlist,
        "label": text(row.get("type")) if kind == "album" else "",
        "setVideoId": text(row.get("setVideoId")),
        "title": title, "artist": " • ".join(a["name"] for a in artists) or text(author),
        "artists": [{"name": a["name"], "id": text(a.get("id") or a.get("browseId") or a.get("channelId")) or author_ids.get(a["name"].casefold(), "")} for a in artists],
        "album": {
            "name": text(album.get("name") or row.get("albumName") or row.get("albumTitle")),
            "id": text(album.get("id") or album.get("browseId") or row.get("albumId") or row.get("albumBrowseId")),
        },
        "thumbnail": thumbnail(row.get("thumbnails") or row.get("thumbnail")),
        "largeThumbnail": thumbnail(row.get("thumbnails") or row.get("thumbnail"), largest=True),
        "artworkVariants": variants(row.get("thumbnails") or row.get("thumbnail")),
        "duration": duration(row.get("duration_seconds") or row.get("duration") or row.get("length")),
        "views": text(row.get("views")).removesuffix(" plays"), "year": text(row.get("year")),
        "inLibrary": bool(row.get("inLibrary")),
        "libraryTokens": {k: text(v) for k, v in (row.get("feedbackTokens") or {}).items() if k in {"add", "remove"}},
        "owned": bool(row.get("owned")), "count": text(row.get("count")), "played": text(row.get("played")),
        "explicit": bool(row.get("isExplicit")), "rating": text(row.get("likeStatus")),
        "available": bool(identifier) and row.get("isAvailable", True) is not False,
        "videoType": text(row.get("videoType")) or ("MUSIC_VIDEO_TYPE_UGC" if result_type == "video" else ""),
        **({"category": text(row.get("category")), "subscribers": text(row.get("subscribers"))} if row.get("category") else {}),
    }


def items(rows, kind=None):
    return [value for row in rows if (value := item(row, kind)) is not None] if isinstance(rows, list) else []


def shelves(rows):
    return [{"title": text(row.get("title")), "subtitle": text(row.get("strapline")), "items": items(row.get("contents", []))}
            for row in rows if isinstance(row, dict) and row.get("contents")]


# Known shelves render first in a fixed order with a fixed layout, so Home looks the
# same between visits even though YouTube Music reorders its personalized response.
PINNED_SHELVES = ("quick picks", "listen again", "mixed for you", "forgotten favorites", "from your library", "new releases")
SHELF_LAYOUTS = {"quick picks": "rows", "listen again": "cards", "mixed for you": "cards"}
HOME_SHELVES = 30
HOME_TTL = 6 * 60 * 60
# Routes whose content does not depend on likes, playlist edits or listening history.
STABLE_ROUTES = ("home", "explore", "charts", "moods", "mood")


def shelf_layout(section):
    known = SHELF_LAYOUTS.get(section["title"].strip().casefold())
    if known:
        return known
    kinds = {media.get("kind") for media in section["items"]}
    return "rows" if kinds == {"song"} else "cards"


def arrange_home(sections):
    def rank(indexed):
        index, section = indexed
        title = section["title"].strip().casefold()
        return (PINNED_SHELVES.index(title), 0) if title in PINNED_SHELVES else (len(PINNED_SHELVES), index)

    ordered = [section for _, section in sorted(enumerate(sections), key=rank)]
    return [{**section, "layout": shelf_layout(section)} for section in ordered]


ARTIST_TOP_SONGS = 5


def artist_songs(section, content):
    """Build an artist's Top songs list: a few rows, with Show all when there are more.

    The shelf's browseId is the artist's songs playlist (VL-prefixed), so Show all opens
    it as a playlist and playing from there queues the whole list.
    """
    playlist = text(section.get("browseId")).removeprefix("VL")
    return {"title": "Top songs", "subtitle": "", "layout": "rows", "items": content[:ARTIST_TOP_SONGS] if playlist else content,
            "browseId": playlist, "params": "", "showAll": bool(playlist) or len(content) > ARTIST_TOP_SONGS}


SEARCH_KINDS = ("song", "artist", "album", "playlist")


def arrange_search(query, results):
    """Group an unfiltered search like a music app: one top result, then each kind.

    YouTube Music sometimes ranks songs above an artist whose name is exactly the
    query; an exact artist match always becomes the top result.
    """
    wanted = query.strip().casefold()
    top = next((value for value in results if value.get("category", "").casefold() == "top result"), None)
    exact = next((value for value in results if value["kind"] == "artist" and value["title"].strip().casefold() == wanted), None)
    if exact and (top is None or top["kind"] != "artist"):
        top = exact
    top = top or (results[0] if results else None)
    seen, groups = {(top["kind"], top["id"])} if top else set(), {kind: [] for kind in SEARCH_KINDS}
    for value in results:
        key = (value["kind"], value["id"])
        if key in seen or value["kind"] not in groups:
            continue
        seen.add(key)
        groups[value["kind"]].append(value)
    ordered = ([top] if top else []) + [value for kind in SEARCH_KINDS for value in groups[kind]]
    return {"topResult": top or {}, "items": ordered, "groups": groups}


class Catalog:
    PAGE_SIZE = 40
    TTL = 300

    def __init__(self, auth, store, changes=()):
        self.auth, self.store = auth, store
        self.changes = changes

    def _apply_changes(self, data, route, params):
        for change in self.changes:
            apply_change(data, change["result"], params.get("id") if route == "playlist" else None)

    def fetch(self, route, params=None, offset=0, refresh=False, page_size=None):
        params = params or {}
        if not isinstance(params, dict) or not isinstance(offset, int) or not 0 <= offset <= 100000:
            raise CatalogError("This catalog page is invalid. Open it again.")
        # Keep accounts' disposable metadata separate without writing credentials.
        if not self.auth.profile:
            self.auth.restore()
        identity = {k: self.auth.profile.get(k, "") for k in ("name", "handle")}
        scope = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        key = json.dumps([scope, route, params], sort_keys=True)
        cached = self.store.read(key)
        if page_size is not None and (not isinstance(page_size, int) or not 1 <= page_size <= 100000):
            raise CatalogError("This catalog page size is invalid.")
        page_size = page_size or (100000 if route == "album" and params.get("allTracks") else 6 if route == "home" else self.PAGE_SIZE)
        list_key = "shelves" if route == "home" else "items"
        target = offset + page_size
        fresh = cached and time.time() - cached["saved"] < (HOME_TTL if route == "home" else self.TTL)
        complete = cached and (cached["data"].get("complete") or len(cached["data"].get(list_key, [])) > target)
        stale, warning = False, ""
        if cached and fresh and complete and not refresh:
            data = cached["data"]
        else:
            try:
                data = self._fetch(self.auth.catalog(), route, params, target + 1)
            except Exception as error:
                if not cached:
                    raise
                data, stale = cached["data"], True
                name = type(error).__name__
                warning = "reconnect" if name in {"AuthError", "YTMusicUserError"} or str(error).startswith(("Server returned HTTP 401", "Server returned HTTP 403")) else "offline"
            else:
                self._apply_changes(data, route, params)
                try:
                    self.store.write(key, data)
                except sqlite3.Error:
                    warning = "cache_unavailable"
        self._apply_changes(data, route, params)
        page = dict(data)
        all_items = data.get(list_key, [])
        page[list_key] = all_items[offset:target]
        page["cursor"] = target if route != "radio" and (len(all_items) > target or not data.get("complete", True)) else None
        page["stale"], page["warning"] = stale, warning
        return page

    def _fetch(self, client, route, params, limit):
        identifier = params.get("id", "")
        data = {"title": text(params.get("title")) or route.title(), "items": [], "shelves": [], "complete": True}
        if route == "home":
            # Fetch every shelf once; "More Music" pages through this same response
            # instead of splicing a newer, differently ordered one onto it.
            limit = max(limit, HOME_SHELVES)
            data["shelves"] = arrange_home(shelves(client.get_home(limit=limit)))
            data["complete"] = True
            for section in data["shelves"]:
                if section["title"].lower() == "listen again":
                    section["subtitle"] = self.auth.profile.get("name", "Your music").upper()
        elif route == "explore":
            raw = client.get_explore()
            for name in ("new_releases", "top_songs", "trending", "new_videos"):
                content = raw.get(name, [])
                normalized = items(content.get("items", []) if isinstance(content, dict) else content)
                if normalized:
                    title = {"new_releases": "New albums & singles", "top_songs": "Top songs", "trending": "Trending", "new_videos": "New music videos"}[name]
                    data["shelves"].append({"title": title, "subtitle": "", "items": normalized, "layout": "rows" if name in {"top_songs", "trending"} else "cards"})
            data["moods"] = raw.get("moods_and_genres", [])
        elif route == "charts":
            raw = client.get_charts(country=params.get("country", "ZZ"))
            data["shelves"] = [{**section, "layout": shelf_layout(section)} for section in
                               ({"title": name.title(), "subtitle": "", "items": items(value)} for name, value in raw.items() if isinstance(value, list))]
        elif route == "search" and not params.get("filter"):
            query = text(params.get("query")).strip()
            if not query:
                raise CatalogError("Enter a song, artist, album or playlist.")
            data["title"] = query
            raw = client.search(query, filter=None, limit=max(limit, 40))
            data.update(arrange_search(query, items([row for row in raw if row.get("resultType", "song") in {"song", "video", "album", "artist", "playlist"}])))
            data["complete"] = True
        elif route == "search":
            query = text(params.get("query")).strip()
            if not query:
                raise CatalogError("Enter a song, artist, album or playlist.")
            data["title"] = query
            raw_limit = limit
            while True:
                raw = client.search(query, filter=params.get("filter"), limit=raw_limit)
                allowed = {"song", "album", "artist", "playlist"} | ({"video"} if params.get("filter") == "videos" else set())
                data["items"] = items([row for row in raw if row.get("resultType", "song") in allowed])
                if len(data["items"]) >= limit or len(raw) < raw_limit or raw_limit >= 100000:
                    break
                raw_limit = min(100000, raw_limit * 2)
            data["complete"] = len(raw) < raw_limit or raw_limit >= 100000
        elif route in {"album", "playlist"}:
            try:
                raw = client.get_album(identifier) if route == "album" else client.get_playlist(identifier, limit=limit)
            except KeyError:
                if route != "playlist":
                    raise
                # The provider omits the song shelf for an empty owned playlist.
                candidate = next((row for row in client.get_library_playlists(limit=None) if (row.get("playlistId") or text(row.get("browseId")).removeprefix("VL")) == identifier), None)
                if not candidate or not candidate.get("owned") or str(candidate.get("count")) not in {"0", "0 songs"}:
                    raise CatalogError("This playlist could not be loaded. Refresh and retry.") from None
                raw = {**candidate, "tracks": [], "trackCount": 0, "author": {"name": self.auth.profile.get("name", "Your music")}}
            if not isinstance(raw, dict) or not raw.get("title"):
                raise CatalogError("This release is unavailable. Go back and choose another item.")
            data.update(title=text(raw.get("title")), subtitle=text(raw.get("description")), thumbnail=thumbnail(raw.get("thumbnails")), largeThumbnail=thumbnail(raw.get("thumbnails"), largest=True), items=items(raw.get("tracks", []), "song"), editable=bool(raw.get("owned")))
            apply_artwork(data, variants(raw.get("thumbnails")))
            data.update(id=identifier, kind=route, artists=raw.get("artists") or [], year=text(raw.get("year")), trackCount=duration(raw.get("trackCount")) or len(data["items"]), duration=duration(raw.get("duration_seconds")), audioPlaylistId=text(raw.get("audioPlaylistId")), saved=bool(raw.get("isSaved")) or bool(data["items"]) and all(track.get("inLibrary") for track in data["items"]))
            data.update(author=text((raw.get("author") or {}).get("name")) if isinstance(raw.get("author"), dict) else text(raw.get("author")), privacy=text(raw.get("privacy")))
            if route == "album":
                artists = raw.get("artists") or []
                for track in data["items"]:
                    track["album"] = {"name": data["title"], "id": identifier}
                    track["thumbnail"] = track["thumbnail"] or data["thumbnail"]
                    apply_artwork(track, media_variants(track) + media_variants(data))
                    if not track["artists"]:
                        track["artists"] = artists
                        track["artist"] = " • ".join(text(a.get("name")) for a in artists)
            else:
                data["complete"] = len(data["items"]) < limit
        elif route == "artist":
            raw = client.get_artist(identifier)
            if not isinstance(raw, dict) or not raw.get("name"):
                raise CatalogError("This artist is unavailable. Go back and choose another artist.")
            data.update(title=text(raw.get("name")), subtitle=text(raw.get("description")), thumbnail=thumbnail(raw.get("thumbnails")))
            wide = [photo for photo in (raw.get("thumbnails") or []) if isinstance(photo, dict) and (photo.get("width") or 0) >= (photo.get("height") or 1) * 1.4 and text(photo.get("url")).startswith("https://")]
            data.update(id=identifier, kind="artist", subscriptionId=text(raw.get("channelId")), subscribed=bool(raw.get("subscribed")), subscribers=text(raw.get("subscribers")), monthlyListeners=text(raw.get("monthlyListeners")), shuffleId=text(raw.get("shuffleId")), radioId=text(raw.get("radioId")), hero=wide[-1]["url"] if wide else "")
            for name in ("songs", "albums", "singles", "related"):
                section = raw.get(name) or {}
                content = items(section.get("results", []))
                for value in content:
                    if value["kind"] == "song" and not value["artist"]:
                        value["artist"] = data["title"]
                        value["artists"] = [{"id": identifier, "name": data["title"]}]
                if content and name == "songs":
                    data["shelves"].append(artist_songs(section, content))
                elif content:
                    data["shelves"].append({"title": name.title(), "subtitle": "", "items": content, "browseId": text(section.get("browseId")), "params": text(section.get("params"))})
        elif route == "artist_albums":
            data["items"] = items(client.get_artist_albums(identifier, params["params"], limit=limit), "album")
            data["complete"] = len(data["items"]) < limit
        elif route.startswith("library_"):
            methods = {"library_songs": ("get_library_songs", "song"), "library_albums": ("get_library_albums", "album"), "library_artists": ("get_library_artists", "artist"), "library_playlists": ("get_library_playlists", "playlist"), "library_subscriptions": ("get_library_subscriptions", "artist"), "library_liked": ("get_liked_songs", "song")}
            if route not in methods:
                raise CatalogError("This library section is unavailable.")
            method, kind = methods[route]
            kwargs = {"order": params["order"]} if params.get("order") in {"a_to_z", "z_to_a", "recently_added"} and route not in {"library_playlists", "library_liked"} else {}
            raw = getattr(client, method)(limit=limit, **kwargs)
            data["items"] = items(raw.get("tracks", []) if isinstance(raw, dict) else raw, kind)
            data["title"] = "Liked songs" if route == "library_liked" else route.removeprefix("library_").title()
            data["complete"] = len(data["items"]) < limit
        elif route == "history":
            data["items"] = items(client.get_history(), "song")
        elif route == "suggestions":
            data["suggestions"] = client.get_search_suggestions(text(params.get("query")))
        elif route == "radio":
            raw = client.get_watch_playlist(videoId=identifier or None, playlistId=params.get("playlistId"), radio=bool(params.get("radio", True)), shuffle=bool(params.get("shuffle")), limit=limit)
            data.update(items=items(raw.get("tracks", []), "song"), lyricsId=raw.get("lyrics"), relatedId=raw.get("related"))
        elif route == "moods":
            data["groups"] = client.get_mood_categories()
        elif route == "mood":
            data["items"] = items(client.get_mood_playlists(params["params"]), "playlist")
        else:
            raise CatalogError("This catalog section is unavailable. Return to Home.")
        return data
