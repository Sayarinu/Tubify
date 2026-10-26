"""Last.fm desktop authentication and durable delivery, used only in its worker."""

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .credentials import SERVICE, secure_backend

VAULT = SERVICE + ".lastfm"
ENDPOINT = "https://ws.audioscrobbler.com/2.0/"
MAX_PENDING = 1000


class LastFmError(RuntimeError):
    def __init__(self, code, message, retry=False):
        super().__init__(message)
        self.code, self.retry = code, retry


def request(credentials, method, values=None, opener=urlopen):
    params = {"api_key": credentials["api_key"], "method": method, **(values or {})}
    if method.startswith("track."):
        params["sk"] = credentials["session"]
    signature = "".join(key + str(params[key]) for key in sorted(params)) + credentials["secret"]
    params["api_sig"] = hashlib.md5(signature.encode("utf-8"), usedforsecurity=False).hexdigest()
    params["format"] = "json"
    req = Request(ENDPOINT, data=urlencode(params).encode("utf-8"), headers={"User-Agent": "YouTubeMusicNative/0.1", "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with opener(req, timeout=10) as response:
            raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError()
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError()
    except Exception as error:
        # Last.fm can send useful protocol errors with non-200 HTTP statuses.
        if hasattr(error, "read"):
            try:
                result = json.loads(error.read(1024 * 1024))
                if not isinstance(result, dict) or not result.get("error"):
                    raise ValueError()
            except Exception:
                raise LastFmError("offline", "Last.fm could not be reached. Saved listens will retry.", True) from None
        else:
            raise LastFmError("offline", "Last.fm could not be reached. Saved listens will retry.", True) from None
    if result.get("error"):
        code = str(result["error"])
        if code == "9":
            raise LastFmError("auth", "Sign in to Last.fm again to send saved listens.")
        if code in {"4", "10", "13", "26"}:
            raise LastFmError("setup", "Last.fm rejected the app credentials. Check the API key and shared secret.")
        if code in {"11", "16", "29"}:
            raise LastFmError("offline", "Last.fm is temporarily unavailable. Saved listens will retry.", True)
        if code == "14":
            raise LastFmError("approval", "Approve access in your browser, then complete sign-in.")
        if code == "15":
            raise LastFmError("approval", "The sign-in token expired. Start sign-in again.")
        raise LastFmError("rejected", "Last.fm rejected this request. Check the song metadata or retry sign-in.")
    return result


class LastFmService:
    def __init__(self, data_dir, backend=None, api=request, clock=time.time):
        self.root = Path(data_dir)
        self.backend, self.api, self.clock = backend, api, clock

    def _vault(self):
        if self.backend is None:
            self.backend = secure_backend()
        return self.backend

    def _load(self):
        try:
            raw = self._vault().get_password(VAULT, "credentials")
            value = json.loads(raw) if raw else {}
            if not isinstance(value, dict) or any(not isinstance(v, str) for v in value.values()):
                raise ValueError()
            return value
        except Exception:
            raise LastFmError("keyring", "Unlock your system keyring to use Last.fm.") from None

    def _save(self, value):
        try:
            self._vault().set_password(VAULT, "credentials", json.dumps(value))
        except Exception:
            raise LastFmError("keyring", "Last.fm credentials could not be saved. Unlock your system keyring and retry.") from None

    @contextmanager
    def _db(self):
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        db = sqlite3.connect(self.root / "lastfm.sqlite3")
        db.execute("CREATE TABLE IF NOT EXISTS listens (id TEXT PRIMARY KEY, owner TEXT NOT NULL, body TEXT NOT NULL, created INTEGER NOT NULL, done INTEGER NOT NULL DEFAULT 0)")
        try:
            with db:
                yield db
        finally:
            db.close()

    def _clear_queue(self):
        with self._db() as db:
            db.execute("DELETE FROM listens")

    def _status(self, value):
        with self._db() as db:
            queued = db.execute("SELECT count(*) FROM listens WHERE done = 0").fetchone()[0]
        return {"configured": bool(value.get("api_key") and value.get("secret")), "connected": bool(value.get("session")), "username": value.get("username", ""), "awaitingApproval": bool(value.get("token")), "pendingCount": queued}

    def _send(self, value, method, values=None):
        try:
            return self.api(value, method, values)
        except LastFmError as error:
            if error.code == "auth":
                value.pop("session", None)
                self._save(value)
            raise

    def perform(self, action, payload):
        value = {} if action in {"configure", "logout"} else self._load()
        if action == "configure":
            key, secret = str(payload.get("api_key", "")).strip(), str(payload.get("secret", "")).strip()
            if not all(re.fullmatch(r"[a-fA-F0-9]{32}", part) for part in (key, secret)):
                raise LastFmError("setup", "Enter the 32-character API key and shared secret supplied by Last.fm.")
            value = {"api_key": key, "secret": secret}
            self._save(value)
            self._clear_queue()
        elif action == "authorize":
            if not value.get("api_key") or not value.get("secret"):
                raise LastFmError("setup", "Save your Last.fm app credentials first.")
            result = self._send(value, "auth.getToken")
            token = result.get("token", "")
            if not isinstance(token, str) or not re.fullmatch(r"[a-zA-Z0-9]{16,128}", token):
                raise LastFmError("response", "Last.fm returned an invalid sign-in token. Retry sign-in.")
            value["token"] = token
            self._save(value)
            return {**self._status(value), "authUrl": "https://www.last.fm/api/auth/?" + urlencode({"api_key": value["api_key"], "token": token})}
        elif action == "complete":
            if not value.get("token"):
                raise LastFmError("approval", "Start sign-in and approve access in your browser first.")
            result = self._send(value, "auth.getSession", {"token": value["token"]}).get("session", {})
            if not isinstance(result, dict) or not all(isinstance(result.get(key), str) and 0 < len(result[key]) <= 128 for key in ("name", "key")):
                raise LastFmError("response", "Last.fm returned an invalid session. Retry sign-in.")
            if value.get("username") and value["username"].casefold() != result["name"].casefold():
                self._clear_queue()
            value.update(session=result["key"], username=result["name"])
            value.pop("token", None)
            self._save(value)
        elif action == "logout":
            if self._vault().get_password(VAULT, "credentials") is not None:
                try:
                    self._vault().delete_password(VAULT, "credentials")
                except Exception:
                    raise LastFmError("keyring", "Sign-out could not clear Last.fm credentials. Unlock the keyring and retry.") from None
            self._clear_queue()
            value = {}
        elif action in {"now_playing", "listen", "flush"}:
            if not value.get("session"):
                raise LastFmError("auth", "Sign in to Last.fm to enable listening updates.")
            if action == "now_playing":
                body = metadata(payload.get("track", {}))
                if body:
                    self._send(value, "track.updateNowPlaying", body)
            else:
                if action == "listen":
                    body = metadata(payload.get("track", {}))
                    identifier, timestamp = payload.get("id"), payload.get("timestamp")
                    if not body or not isinstance(identifier, str) or not re.fullmatch(r"[a-f0-9]{32}", identifier) or not isinstance(timestamp, int) or not 0 < timestamp <= self.clock() + 60:
                        raise LastFmError("metadata", "This listen has incomplete metadata and was not saved.")
                    body["timestamp"] = timestamp
                    with self._db() as db:
                        db.execute("INSERT OR IGNORE INTO listens (id, owner, body, created) VALUES (?, ?, ?, ?)", (identifier, value["username"].casefold(), json.dumps(body), timestamp))
                        # Bound local storage, retaining the most recent offline listens.
                        db.execute("DELETE FROM listens WHERE done = 0 AND id NOT IN (SELECT id FROM listens WHERE done = 0 ORDER BY created DESC, rowid DESC LIMIT ?)", (MAX_PENDING,))
                result = self._flush(value)
                return {**self._status(value), **result}
        elif action != "status":
            raise LastFmError("operation", "This Last.fm operation is unavailable.")
        return self._status(value)

    def _flush(self, value):
        with self._db() as db:
            row = db.execute("SELECT id, body FROM listens WHERE done = 0 AND owner = ? ORDER BY created, rowid LIMIT 1", (value["username"].casefold(),)).fetchone()
        if not row:
            return {}
        try:
            response = self._send(value, "track.scrobble", json.loads(row[1]))
            scrobbles = response.get("scrobbles")
            if not isinstance(scrobbles, dict):
                raise LastFmError("offline", "Last.fm did not confirm this listen. It will retry.", True)
            attributes = scrobbles.get("@attr", {})
            if str(attributes.get("accepted", "")) not in {"0", "1"} or str(attributes.get("ignored", "")) not in {"0", "1"} or int(attributes["accepted"]) + int(attributes["ignored"]) != 1:
                raise LastFmError("offline", "Last.fm did not confirm this listen. It will retry.", True)
            message = "Last.fm filtered a listen with unsupported metadata." if str(attributes["ignored"]) == "1" else ""
        except LastFmError as error:
            if error.retry or error.code in {"auth", "setup", "keyring"}:
                return {"message": str(error), "retry": error.retry, "reconnect": error.code in {"auth", "setup"}}
            message = str(error)
        with self._db() as db:
            db.execute("UPDATE listens SET done = 1, body = '{}' WHERE id = ?", (row[0],))
            db.execute("DELETE FROM listens WHERE done = 1 AND id NOT IN (SELECT id FROM listens WHERE done = 1 ORDER BY created DESC, rowid DESC LIMIT ?)", (MAX_PENDING,))
        return {"message": message}


def metadata(track):
    if not isinstance(track, dict):
        return {}
    artists = track.get("artists")
    artist = next((row.get("name", "") for row in artists if isinstance(row, dict) and row.get("name")), "") if isinstance(artists, list) else ""
    artist = artist or track.get("artist", "")
    album = track.get("album")
    album = album.get("name", "") if isinstance(album, dict) else album or track.get("albumName", "")
    title = track.get("title", "")
    if not all(isinstance(part, str) and part.strip() for part in (artist, title)):
        return {}
    result = {"artist": artist.strip()[:512], "track": title.strip()[:512]}
    if isinstance(album, str) and album.strip():
        result["album"] = album.strip()[:512]
    duration = track.get("duration", 0)
    if isinstance(duration, (int, float)) and 0 < duration < 86400:
        result["duration"] = int(duration)
    return result
