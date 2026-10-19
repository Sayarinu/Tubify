"""Normalize provider variants, page results and reuse metadata when offline."""

import hashlib
import json
import sqlite3
import time


class CatalogError(RuntimeError):
    pass


def text(value):
    return value if isinstance(value, str) else ""


def thumbnail(value):
    if isinstance(value, dict):
        value = value.get("thumbnails", [])
    if not isinstance(value, list):
        return ""
    choices = [v for v in value if isinstance(v, dict) and text(v.get("url")).startswith("https://")]
    if not choices:
        return ""
    return min(choices, key=lambda v: abs((v.get("width") or 300) - 300))["url"]


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
    elif playlist or result_type.endswith("playlist") or browse.startswith("VL"):
        kind = "playlist"
    elif result_type in {"artist", "album"}:
        kind = result_type
    elif not kind:
        kind = "artist" if browse.startswith("UC") else "album" if browse.startswith("MPRE") else "playlist"
    identifier = video or playlist or browse
    title = text(row.get("title") or row.get("name"))
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
    album = row.get("album") or {}
    return {
        "kind": kind, "id": identifier, "videoId": video, "browseId": browse,
        "label": text(row.get("type")) if kind == "album" else "",
        "setVideoId": text(row.get("setVideoId")),
        "title": title, "artist": " • ".join(a["name"] for a in artists) or text(author),
        "artists": [{"name": a["name"], "id": text(a.get("id"))} for a in artists],
        "album": {"name": text(album.get("name")), "id": text(album.get("id"))} if isinstance(album, dict) else {},
        "thumbnail": thumbnail(row.get("thumbnails") or row.get("thumbnail")),
        "duration": duration(row.get("duration_seconds") or row.get("duration")),
        "explicit": bool(row.get("isExplicit")), "rating": text(row.get("likeStatus")),
        "available": bool(identifier) and row.get("isAvailable", True) is not False,
    }


def items(rows, kind=None):
    return [value for row in rows if (value := item(row, kind)) is not None] if isinstance(rows, list) else []


def shelves(rows):
    return [{"title": text(row.get("title")), "subtitle": text(row.get("strapline")), "items": items(row.get("contents", []))}
            for row in rows if isinstance(row, dict) and row.get("contents")]


class Catalog:
    PAGE_SIZE = 40
    TTL = 300

    def __init__(self, auth, store):
        self.auth, self.store = auth, store

    def fetch(self, route, params=None, offset=0, refresh=False):
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
        page_size = 6 if route == "home" else self.PAGE_SIZE
        list_key = "shelves" if route == "home" else "items"
        target = offset + page_size
        fresh = cached and time.time() - cached["saved"] < self.TTL
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
                try:
                    self.store.write(key, data)
                except sqlite3.Error:
                    warning = "cache_unavailable"
        page = dict(data)
        all_items = data.get(list_key, [])
        page[list_key] = all_items[offset:target]
        page["cursor"] = target if len(all_items) > target or not data.get("complete", True) else None
        page["stale"], page["warning"] = stale, warning
        return page

    def _fetch(self, client, route, params, limit):
        identifier = params.get("id", "")
        data = {"title": route.title(), "items": [], "shelves": [], "complete": True}
        if route == "home":
            data["shelves"] = shelves(client.get_home(limit=limit))
            data["complete"] = len(data["shelves"]) < limit
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
            data["shelves"] = [{"title": name.title(), "subtitle": "", "items": items(value)} for name, value in raw.items() if isinstance(value, list)]
        elif route == "search":
            query = text(params.get("query")).strip()
            if not query:
                raise CatalogError("Enter a song, artist, album or playlist.")
            data["title"] = query
            data["items"] = items(client.search(query, filter=params.get("filter"), limit=limit))
            data["complete"] = len(data["items"]) < limit
        elif route in {"album", "playlist"}:
            raw = client.get_album(identifier) if route == "album" else client.get_playlist(identifier, limit=limit)
            data.update(title=text(raw.get("title")), subtitle=text(raw.get("description")), thumbnail=thumbnail(raw.get("thumbnails")), items=items(raw.get("tracks", []), "song"), editable=bool(raw.get("owned")))
            if route == "album":
                artists = raw.get("artists") or []
                for track in data["items"]:
                    track["album"] = {"name": data["title"], "id": identifier}
                    track["thumbnail"] = track["thumbnail"] or data["thumbnail"]
                    if not track["artists"]:
                        track["artists"] = artists
                        track["artist"] = " • ".join(text(a.get("name")) for a in artists)
            else:
                data["complete"] = len(data["items"]) < limit
        elif route == "artist":
            raw = client.get_artist(identifier)
            data.update(title=text(raw.get("name")), subtitle=text(raw.get("description")), thumbnail=thumbnail(raw.get("thumbnails")))
            for name in ("songs", "albums", "singles", "videos", "related"):
                section = raw.get(name) or {}
                content = items(section.get("results", []))
                if content:
                    data["shelves"].append({"title": name.title(), "subtitle": "", "items": content, "browseId": text(section.get("browseId")), "params": text(section.get("params"))})
        elif route == "artist_albums":
            data["items"] = items(client.get_artist_albums(identifier, params["params"], limit=limit), "album")
            data["complete"] = len(data["items"]) < limit
        elif route.startswith("library_"):
            methods = {"library_songs": (client.get_library_songs, "song"), "library_albums": (client.get_library_albums, "album"), "library_artists": (client.get_library_artists, "artist"), "library_playlists": (client.get_library_playlists, "playlist")}
            if route not in methods:
                raise CatalogError("This library section is unavailable.")
            method, kind = methods[route]
            data["items"] = items(method(limit=limit), kind)
            data["complete"] = len(data["items"]) < limit
        elif route == "history":
            data["items"] = items(client.get_history(), "song")
        elif route == "suggestions":
            data["suggestions"] = client.get_search_suggestions(text(params.get("query")))
        elif route == "radio":
            raw = client.get_watch_playlist(videoId=identifier or None, playlistId=params.get("playlistId"), radio=True, limit=limit)
            data.update(items=items(raw.get("tracks", []), "song"), lyricsId=raw.get("lyrics"), relatedId=raw.get("related"))
        elif route == "moods":
            data["groups"] = client.get_mood_categories()
        elif route == "mood":
            data["items"] = items(client.get_mood_playlists(params["params"]), "playlist")
        else:
            raise CatalogError("This catalog section is unavailable. Return to Home.")
        return data
