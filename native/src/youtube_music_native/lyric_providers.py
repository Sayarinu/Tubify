"""Optional public lyric readers. Account sessions never reach these endpoints."""

import json
import math
from pathlib import Path
import re
import time
import unicodedata
from urllib.parse import urlparse

from . import lyric_formats as formats
from .credentials import secure_backend
from .lyric_options import PROVIDERS

KEY_SERVICE = "com.carter.youtube-music.native.lyrics"
KEY_NAME = "better-lyrics"


class ProviderUnavailable(RuntimeError):
    pass


def provider_key(action, value="", backend=None):
    try:
        backend = backend if backend is not None else secure_backend()
        if action == "save":
            if not isinstance(value, str) or not 1 <= len(value.strip()) <= 2048 or "\n" in value or "\r" in value:
                raise ProviderUnavailable("Enter a valid Better Lyrics API key.")
            backend.set_password(KEY_SERVICE, KEY_NAME, value.strip())
        elif action == "clear":
            if backend.get_password(KEY_SERVICE, KEY_NAME):
                backend.delete_password(KEY_SERVICE, KEY_NAME)
        elif action != "status":
            raise ProviderUnavailable("This lyric key action is unavailable.")
        return {"hasKey": bool(backend.get_password(KEY_SERVICE, KEY_NAME))}
    except ProviderUnavailable:
        raise
    except Exception:
        raise ProviderUnavailable("The lyric key could not be updated. Unlock the system keyring and retry.") from None


def read_key():
    try:
        return secure_backend().get_password(KEY_SERVICE, KEY_NAME) or ""
    except Exception:
        return ""


def track_identity(track):
    artists = track.get("artists") or []
    artist = artists[0].get("name", "") if artists and isinstance(artists[0], dict) else track.get("artist", "")
    album = track.get("album", "")
    album = album.get("name", "") if isinstance(album, dict) else album
    duration = track.get("duration", 0)
    duration = float(duration) if isinstance(duration, (int, float)) and math.isfinite(duration) else 0.
    return {"title": str(track.get("title") or "")[:512], "artist": str(artist or "")[:512], "album": str(album or track.get("albumName") or "")[:512], "duration": max(0., duration)}


def same_text(left, right):
    def normal(value):
        return " ".join(unicodedata.normalize("NFKC", str(value)).casefold().split())
    return bool(left and right) and normal(left) == normal(right)


def exact_match(expected, actual):
    if not all(same_text(expected.get(key), actual.get(key)) for key in ("title", "artist")):
        return False
    if expected.get("album") and not same_text(expected["album"], actual.get("album")):
        return False
    duration = actual.get("duration")
    return not expected.get("duration") or isinstance(duration, (int, float)) and math.isfinite(duration) and abs(duration - expected["duration"]) <= 2


class Providers:
    def __init__(self, http_get=None, key_reader=read_key, caption_reader=None):
        self.http_get, self.key_reader, self.caption_reader = http_get, key_reader, caption_reader
        self.retry_after = {}

    def _read(self, url, params=None, key="", raw=False):
        host = urlparse(url).hostname
        if self.retry_after.get(host, 0) > time.monotonic():
            raise ProviderUnavailable("Temporarily rate limited; retry later.")
        import requests
        headers = {"User-Agent": "YouTube-Music-Native/0.1.1 (https://github.com/Sayarinu/YouTube-Music-App)", "Accept": "text/xml" if raw else "application/json"}
        if key:
            headers["X-API-Key"] = key
        response = None
        try:
            response = (self.http_get or requests.get)(url, params=params, headers=headers, timeout=(2, 5), stream=True, allow_redirects=False)
            if response.status_code == 401:
                raise ProviderUnavailable("Uncached lyrics need an existing Better Lyrics API key; new keys are currently unavailable.")
            if response.status_code in {429, 503}:
                retry = response.headers.get("Retry-After", "60")
                retry = min(3600, max(1, int(retry))) if str(retry).isdigit() else 60
                self.retry_after[host] = time.monotonic() + retry
                raise ProviderUnavailable("Temporarily rate limited; retry later.")
            if response.status_code == 404:
                raise ProviderUnavailable("No matching lyrics available.")
            if response.status_code != 200:
                raise ProviderUnavailable("Provider is unavailable; other sources remain enabled.")
            data = bytearray()
            for chunk in response.iter_content(16384):
                data.extend(chunk)
                if len(data) > formats.MAX_DOCUMENT:
                    raise ProviderUnavailable("Provider returned lyrics that are too large.")
            return data.decode("utf-8-sig") if raw else json.loads(data)
        except ProviderUnavailable:
            raise
        except Exception:
            raise ProviderUnavailable("Provider could not be reached or returned invalid lyrics.") from None
        finally:
            if response is not None:
                response.close()

    def fetch(self, provider, video_id, track, approximate=False):
        identity = track_identity(track)
        match = "exact"
        if provider == "unison":
            result = self._read("https://unison.boidu.dev/lyrics", {"v": video_id})
            data = result.get("data") if isinstance(result, dict) and result.get("success") is True else None
            if not isinstance(data, dict) or not isinstance(data.get("lyrics"), str):
                raise ProviderUnavailable("No matching lyrics available.")
            if data.get("videoId") != video_id:
                if not approximate:
                    raise ProviderUnavailable("Provider could not confirm this recording.")
                match = "approximate"
            kind = data.get("format")
            document = formats.ttml(data["lyrics"]) if kind == "ttml" else formats.lrc(data["lyrics"], identity["duration"]) if kind == "lrc" else formats.plain(data["lyrics"]) if kind == "plain" else None
        elif provider == "lrclib":
            if not identity["title"] or not identity["artist"]:
                raise ProviderUnavailable("Song title and artist are needed for this source.")
            params = {"track_name": identity["title"], "artist_name": identity["artist"]}
            if identity["album"]:
                params["album_name"] = identity["album"]
            if identity["duration"]:
                params["duration"] = round(identity["duration"])
            result = self._read("https://lrclib.net/api/get", params)
            if not isinstance(result, dict):
                raise ProviderUnavailable("No matching lyrics available.")
            actual = {"title": result.get("trackName"), "artist": result.get("artistName"), "album": result.get("albumName"), "duration": result.get("duration")}
            if not exact_match(identity, actual):
                if not approximate:
                    raise ProviderUnavailable("Provider could not confirm this recording.")
                match = "approximate"
            document = formats.lrc(result["syncedLyrics"], result.get("duration") or identity["duration"]) if result.get("syncedLyrics") else formats.plain(result.get("plainLyrics") or "")
        elif provider == "better":
            if not identity["title"] or not identity["artist"]:
                raise ProviderUnavailable("Song title and artist are needed for this source.")
            result = self._read("https://api.betterlyrics.org/getLyrics", {"s": identity["title"], "a": identity["artist"], "al": identity["album"], "d": round(identity["duration"])}, key=self.key_reader())
            if not isinstance(result, dict) or not isinstance(result.get("ttml"), str):
                raise ProviderUnavailable("No matching lyrics available.")
            document = formats.ttml(result["ttml"])
            # Cached Better responses omit confidence and matched song metadata. Query
            # parameters alone cannot prove identity, so strict mode must fall through.
            if not exact_match(identity, document["identity"]):
                if not approximate:
                    raise ProviderUnavailable("Better Lyrics cannot confirm this recording. Approximate matches are off.")
                match = "approximate"
        else:
            raise ProviderUnavailable("This lyric source is unavailable.")
        if not document or not document["available"]:
            raise ProviderUnavailable("No matching lyrics available.")
        return {**document, "videoId": video_id, "provider": provider, "source": PROVIDERS[provider], "match": match, "trackIdentity": identity}

    def captions(self, auth, video_id, track, data_dir):
        if self.caption_reader:
            return self.caption_reader(auth, video_id, track, data_dir)
        from yt_dlp import YoutubeDL
        from .compat import extractor_options
        options = extractor_options(Path(data_dir))
        options.update(skip_download=True, noplaylist=True, writesubtitles=False, writeautomaticsub=False, socket_timeout=5, retries=0, extractor_retries=0)
        try:
            with YoutubeDL(options) as extractor:
                # An available native session stays within YouTube's extractor only.
                if auth.session is not None:
                    for cookie in auth.session.cookie_jar():
                        extractor.cookiejar.set_cookie(cookie)
                info = extractor.extract_info("https://www.youtube.com/watch?v=" + video_id, download=False)
                subtitles = (info or {}).get("subtitles") or {}
                choices = [(language, row) for language, rows in subtitles.items() if language != "live_chat" for row in rows if row.get("ext") == "ttml"]
                if not choices:
                    raise ProviderUnavailable("Human captions are unavailable for this song.")
                language, row = sorted(choices, key=lambda item: (not item[0].startswith("en"), item[0]))[0]
                # Fetch through yt-dlp so caption-specific request handling is preserved.
                with extractor.urlopen(row["url"]) as response:
                    body = response.read(formats.MAX_DOCUMENT + 1)
                document = formats.ttml(body.decode("utf-8"))
            return {**document, "videoId": video_id, "provider": "captions", "source": "YouTube human captions (" + language + ")", "match": "exact", "trackIdentity": track_identity(track)}
        except ProviderUnavailable:
            raise
        except Exception:
            raise ProviderUnavailable("Human captions are unavailable for this song.") from None
