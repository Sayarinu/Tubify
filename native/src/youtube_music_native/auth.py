"""Session validation and lifecycle, called only from the provider process."""

from functools import partial

from .credentials import Credentials
from .session import read_browser_session, read_tauri_session


class AuthError(RuntimeError):
    pass


def make_catalog(session):
    import requests
    from ytmusicapi import YTMusic

    http = requests.Session()
    http.request = partial(http.request, timeout=30)
    try:
        return YTMusic(auth=session.headers, requests_session=http)
    except Exception:
        http.close()
        raise


def profile_from_account(account):
    if not isinstance(account, dict) or not isinstance(account.get("accountName"), str) or not account["accountName"]:
        raise AuthError("The session did not return a signed-in account. Reconnect YouTube Music.")
    avatar = account.get("accountPhotoUrl") or ""
    handle = account.get("channelHandle") or ""
    return {
        "name": account["accountName"],
        "handle": handle if isinstance(handle, str) else "",
        "avatar": avatar if isinstance(avatar, str) and avatar.startswith("https://") else "",
    }


class AuthService:
    def __init__(self, credentials=None, catalog_factory=make_catalog):
        self._credentials = credentials
        self.catalog_factory = catalog_factory
        self.session = None
        self.client = None
        self.profile = {}

    @property
    def credentials(self):
        # Local source selection must work even if the OS vault is unavailable.
        if self._credentials is None:
            self._credentials = Credentials()
        return self._credentials

    def restore(self):
        stored = self.credentials.load()
        if stored:
            self.session = stored.session
            self.profile = stored.profile
        else:
            self.session = None
            self.profile = {}
        self.client = None
        return {"connected": self.session is not None, "profile": self.profile}

    def import_session(self, path, tauri=False):
        session = read_tauri_session(path) if tauri else read_browser_session(path)
        client = self.catalog_factory(session)
        profile = profile_from_account(client.get_account_info())
        visitor = client.base_headers.get("X-Goog-Visitor-Id")
        if visitor:
            session.headers["x-goog-visitor-id"] = visitor
        self.credentials.save(session, profile)
        self.session, self.client, self.profile = session, client, profile
        return {"connected": True, "profile": profile}

    def catalog(self):
        if self.session is None:
            self.restore()
        if self.session is None:
            raise AuthError("Connect YouTube Music to browse your account.")
        if self.client is None:
            self.client = self.catalog_factory(self.session)
        return self.client

    def sign_out(self):
        self.credentials.clear()
        self.session, self.client, self.profile = None, None, {}
        return {"connected": False, "profile": {}}
