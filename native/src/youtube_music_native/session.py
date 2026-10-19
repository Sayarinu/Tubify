"""Read explicitly selected session exports without changing browser profiles."""

from copy import copy
from dataclasses import dataclass, field
from http.cookiejar import Cookie, CookieJar
from http.cookies import SimpleCookie
import json
from pathlib import Path
import time


class SessionError(ValueError):
    """An actionable import error that never includes credential contents."""


def make_cookie(name, value, domain=".youtube.com", path="/", secure=True, expires=None):
    return Cookie(
        0, name, value, None, False, domain, True, domain.startswith("."),
        path, True, secure, expires, expires is None, None, None, {}, False,
    )


@dataclass(repr=False)
class Session:
    headers: dict = field(repr=False)
    cookies: list[Cookie] = field(repr=False)

    def __repr__(self):
        return "Session(<redacted>)"

    def cookie_jar(self):
        jar = CookieJar()
        for cookie in self.cookies:
            jar.set_cookie(copy(cookie))
        return jar


def from_headers(value):
    if not isinstance(value, dict) or not all(isinstance(k, str) for k in value):
        raise SessionError("Select a browser.json request-header export.")
    values = {key.lower(): item for key, item in value.items()}
    allowed = {"cookie", "user-agent", "accept-language", "x-goog-authuser"}
    for key in allowed & values.keys():
        item = values[key]
        if not isinstance(item, str) or "\r" in item or "\n" in item:
            raise SessionError("The session contains invalid request headers.")
    cookie = SimpleCookie()
    try:
        cookie.load(values.get("cookie", ""))
    except Exception:
        raise SessionError("The session cookie header is invalid.") from None
    if "__Secure-3PAPISID" not in cookie:
        raise SessionError("The session has no signed-in YouTube Music cookie. Reconnect first.")
    from ytmusicapi.helpers import initialize_headers

    headers = initialize_headers()
    headers.update({key: values[key] for key in allowed if key in values})
    headers.update({
        "authorization": "SAPISIDHASH",
        "x-origin": "https://music.youtube.com",
        "origin": "https://music.youtube.com",
        "x-goog-authuser": values.get("x-goog-authuser", "0"),
    })
    return Session(headers, [make_cookie(m.key, m.value) for m in cookie.values()])


def read_browser_session(path):
    try:
        path = Path(path)
        if path.stat().st_size > 1024 * 1024:
            raise SessionError("The selected session export is too large.")
        return from_headers(json.loads(path.read_text(encoding="utf-8")))
    except SessionError:
        raise
    except (OSError, ValueError, TypeError):
        raise SessionError("Could not read the selected browser.json export.") from None


def read_tauri_session(path):
    """Linux WebKit migration is optional; the ordinary JSON import is portable."""
    path = Path(path)
    if not path.is_file():
        raise SessionError("The selected Tauri cookie file does not exist.")
    try:
        import gi

        gi.require_version("Soup", "3.0")
        from gi.repository import Soup
    except (ImportError, ValueError):
        raise SessionError("Tauri migration requires Linux PyGObject and libsoup 3.") from None
    jar = Soup.CookieJarText.new(str(path), True)
    cookies = []
    for cookie in jar.all_cookies():
        domain = cookie.get_domain()
        if domain.lstrip(".") not in {"youtube.com", "music.youtube.com"}:
            continue
        expiry = cookie.get_expires()
        expires = expiry.to_unix() if expiry else None
        if expires is not None and expires <= time.time():
            continue
        cookies.append(make_cookie(
            cookie.get_name(), cookie.get_value(), domain,
            cookie.get_path() or "/", cookie.get_secure(), expires,
        ))
    session = from_headers({"cookie": "; ".join(f"{c.name}={c.value}" for c in cookies)})
    session.cookies = cookies
    return session
