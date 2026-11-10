"""Choose verified local files first; authenticated extraction runs in a worker."""

from pathlib import Path
import re
import sys
import time
from urllib.parse import parse_qs, urlparse

from ..compat import VIDEO_FORMAT, extractor_options


class SourceError(RuntimeError):
    pass


class SessionExpired(SourceError):
    """YouTube signed this session out; renewing it from the browser lets songs play again."""


EXPIRED = "Your session needs reconnecting. Downloaded music remains available."


# Song resolves skip the HLS manifest request: audio-only formats never come from it.
# The extractor without the skip stays separate, for the rare song that needs it.
AUDIO = "audio", {"extractor_args": {"youtube": {"skip": ["hls"]}}}
AUDIO_FALLBACK = "audio-full", {}


class Sources:
    def __init__(self, auth, media, extractor_factory=None):
        self.auth, self.media = auth, media
        self.extractor_factory = extractor_factory
        self._cache = {}
        # One extractor per format for the worker's lifetime keeps yt-dlp's player and
        # connection caches warm; the worker restarts whenever the account changes.
        self._extractors = {}

    def warm(self, platform=None):
        """Pay imports and the credential read before the first song is chosen."""
        try:
            if self.auth.session is None:
                if (platform or sys.platform) == "darwin":
                    # A keychain read can ask for approval, so each worker waits until a song needs it.
                    import yt_dlp  # noqa: F401
                else:
                    self.auth.restore()
            if self.auth.session is not None:
                self._extractor(*AUDIO)
        except Exception:
            # The first real request reports any problem with a user-facing message.
            pass
        return {"ready": self.auth.session is not None}

    def _extractor(self, kind, extra):
        extractor = self._extractors.get(kind)
        if extractor is None:
            from yt_dlp import YoutubeDL

            factory = self.extractor_factory or YoutubeDL
            options = extractor_options(Path(self.media.root))
            options.update(skip_download=True, noplaylist=True, **extra)
            extractor = self._extractors[kind] = factory(options).__enter__()
        return extractor

    def _extract(self, kind, extra, video_id):
        extractor = self._extractor(kind, extra)
        cookies = list(self.auth.session.cookie_jar())
        signed_in = any(cookie.name == "LOGIN_INFO" for cookie in cookies)
        try:
            # Only the current session's cookies; nothing from earlier responses persists.
            extractor.cookiejar.clear()
            for cookie in cookies:
                extractor.cookiejar.set_cookie(cookie)
            info = extractor.extract_info("https://www.youtube.com/watch?v=" + video_id, download=False)
        except Exception as error:
            self._discard(kind)
            if signed_in and not self._signed_in(extractor):
                raise SessionExpired(EXPIRED) from error
            raise
        if signed_in and not self._signed_in(extractor):
            raise SessionExpired(EXPIRED)
        return info

    @staticmethod
    def _signed_in(extractor):
        # YouTube clears LOGIN_INFO when it stops accepting rotated-out cookies.
        return any(cookie.name == "LOGIN_INFO" for cookie in extractor.cookiejar)

    def _discard(self, kind):
        extractor = self._extractors.pop(kind, None)
        if extractor is not None:
            try:
                extractor.__exit__(None, None, None)
            except Exception:
                pass

    def resolve(self, video_id, force=False, prepared=None, available=True, video=False):
        if not isinstance(video_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
            raise SourceError("This song has no playable music identifier.")
        local = self.media.ready(video_id)
        if local:
            return {"kind": "local", "source": str(local), "headers": [], "videoId": video_id}
        if not available:
            raise SourceError("This song is unavailable. Choose another song or repair its download.")
        if video:
            return self._resolve_video(video_id)
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
        try:
            try:
                info = self._extract(*AUDIO, video_id)
            except Exception as error:
                if "requested format" not in str(error).lower():
                    raise
                info = None
            if not self._audio_only(info):
                # Retry once with every format before reporting that none can play.
                info = self._extract(*AUDIO_FALLBACK, video_id)
            if not self._audio_only(info):
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

    @staticmethod
    def _audio_only(info):
        return bool(info) and info.get("vcodec") == "none" and str(info.get("url", "")).startswith("https://")

    def _resolve_video(self, video_id):
        """Resolve a music video's picture stream, which plays alongside the song's audio."""
        if self.auth.session is None:
            self.auth.restore()
        if self.auth.session is None:
            raise SourceError("Reconnect YouTube Music to watch this video.")
        try:
            info = self._extract("video", {"format": VIDEO_FORMAT}, video_id)
            formats = (info or {}).get("requested_formats") or [info or {}]
            stream = next((value for value in formats if value.get("vcodec") not in {None, "none"}), {})
            url = str(stream.get("url", ""))
            if not url.startswith("https://"):
                raise SourceError("No video format is available. Playing audio instead.")
            expires = float(parse_qs(urlparse(url).query).get("expire", [time.time() + 300])[0])
            headers = stream.get("http_headers") or info.get("http_headers") or {}
            return {"kind": "remote", "video": True, "source": url,
                    "headers": [f"{k}: {v}" for k, v in headers.items() if "\n" not in str(k) + str(v) and "\r" not in str(k) + str(v)],
                    "expires": expires, "videoId": video_id}
        except SourceError:
            raise
        except Exception:
            raise SourceError("This video could not be loaded. Playing audio instead.") from None
