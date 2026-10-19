"""Choose verified local files first; authenticated extraction runs in a worker."""

from pathlib import Path
import re
import time
from urllib.parse import parse_qs, urlparse

from .compat import extractor_options


class SourceError(RuntimeError):
    pass


class Sources:
    def __init__(self, auth, media, extractor_factory=None):
        self.auth, self.media = auth, media
        self.extractor_factory = extractor_factory
        self._cache = {}

    def resolve(self, video_id, force=False, prepared=None, available=True):
        if not isinstance(video_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
            raise SourceError("This song has no playable music identifier.")
        local = self.media.ready(video_id)
        if local:
            return {"kind": "local", "source": str(local), "headers": [], "videoId": video_id}
        if not available:
            raise SourceError("This song is unavailable. Choose another song or repair its download.")
        if (not force and isinstance(prepared, dict) and prepared.get("kind") == "remote"
                and prepared.get("videoId") == video_id and isinstance(prepared.get("expires"), (int, float))
                and prepared["expires"] > time.time() + 60 and str(prepared.get("source", "")).startswith("https://")
                and isinstance(prepared.get("headers"), list)
                and all(isinstance(header, str) and "\n" not in header and "\r" not in header for header in prepared["headers"])):
            return prepared
        cached = self._cache.get(video_id)
        if cached and cached["expires"] > time.time() + 60 and not force:
            return cached
        if self.auth.session is None:
            self.auth.restore()
        if self.auth.session is None:
            raise SourceError("Reconnect YouTube Music to stream this song. Downloaded songs remain available.")
        from yt_dlp import YoutubeDL

        factory = self.extractor_factory or YoutubeDL
        options = extractor_options(Path(self.media.root))
        options.update(skip_download=True, noplaylist=True)
        try:
            with factory(options) as extractor:
                for cookie in self.auth.session.cookie_jar():
                    extractor.cookiejar.set_cookie(cookie)
                info = extractor.extract_info("https://www.youtube.com/watch?v=" + video_id, download=False)
            if not info or info.get("vcodec") != "none" or not str(info.get("url", "")).startswith("https://"):
                raise SourceError("No audio-only format is available for this song.")
            expires = parse_qs(urlparse(info["url"]).query).get("expire", [None])[0]
            try:
                expiry = float(expires) if expires else time.time() + 300
            except (ValueError, TypeError):
                expiry = time.time() + 300
            source = {"kind": "remote", "source": info["url"], "headers": [f"{k}: {v}" for k, v in info.get("http_headers", {}).items() if "\n" not in str(k) + str(v) and "\r" not in str(k) + str(v)], "expires": expiry, "videoId": video_id}
            self._cache[video_id] = source
            return source
        except SourceError:
            raise
        except Exception:
            raise SourceError("This song could not be resolved. Check your connection, reconnect, or update the extractor.") from None
