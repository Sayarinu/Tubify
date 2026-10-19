"""Durable collection snapshots and resumable, deduplicated audio downloads."""

from contextlib import ExitStack
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time

from .catalog import items, text, thumbnail
from .compat import ProbeError, extractor_options
from .media import MediaFiles


VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")
EXTENSIONS = {"webm", "m4a", "mp4", "opus", "ogg", "aac", "mp3", "mkv", "mka", "flac", "wav"}


class DownloadError(RuntimeError):
    pass


class DownloadCancelled(DownloadError):
    pass


def clean_track(value):
    video_id = text(value.get("videoId") or value.get("id"))
    album = value.get("album") or {}
    artists = value.get("artists") or []
    return {
        "kind": "song", "id": video_id, "videoId": video_id,
        "title": text(value.get("title"))[:4096] or "Unavailable song",
        "artist": text(value.get("artist"))[:4096],
        "artists": [{"id": text(a.get("id")), "name": text(a.get("name"))} for a in artists if isinstance(a, dict)],
        "album": {"id": text(album.get("id")), "name": text(album.get("name"))} if isinstance(album, dict) else {},
        "thumbnail": text(value.get("thumbnail")) if text(value.get("thumbnail")).startswith("https://") else "",
        "duration": value.get("duration") if isinstance(value.get("duration"), (int, float)) else 0,
        "explicit": bool(value.get("explicit")), "available": bool(VIDEO_ID.fullmatch(video_id)) and value.get("available", True) is not False,
        "setVideoId": text(value.get("setVideoId")),
    }


def cache_artwork(url, folder):
    if not url.startswith("https://"):
        return ""
    import requests
    from PySide6.QtGui import QImage

    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = folder / (hashlib.sha256(url.encode()).hexdigest() + ".image")
    if target.is_file() and not QImage(str(target)).isNull():
        return target.as_uri()
    temporary = None
    try:
        with requests.get(url, stream=True, timeout=10) as response:
            response.raise_for_status()
            content = bytearray()
            for chunk in response.iter_content(65536):
                content.extend(chunk)
                if len(content) > 8 * 1024 * 1024:
                    return ""
        if QImage.fromData(bytes(content)).isNull():
            return ""
        with tempfile.NamedTemporaryFile(dir=folder, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        return target.as_uri()
    except (requests.RequestException, OSError):
        return ""
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


class DownloadStore:
    def __init__(self, data_dir):
        self.media = MediaFiles(Path(data_dir) / "media")
        self.root, self.db = self.media.root, self.media.db
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS collections (id TEXT PRIMARY KEY, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS download_jobs (
                collection_id TEXT PRIMARY KEY REFERENCES collections(id) ON DELETE CASCADE,
                state TEXT NOT NULL, completed INTEGER NOT NULL, total INTEGER NOT NULL,
                fraction REAL NOT NULL, error TEXT NOT NULL, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS media_refs (
                collection_id TEXT REFERENCES collections(id) ON DELETE CASCADE,
                video_id TEXT NOT NULL, PRIMARY KEY (collection_id, video_id));
            CREATE TABLE IF NOT EXISTS pending_delete (path TEXT PRIMARY KEY);
        """)

    def recover(self):
        from PySide6.QtCore import QLockFile

        lock = QLockFile(str(self.root / "transfer.lock"))
        lock.setStaleLockTime(0)
        if lock.tryLock(0):
            try:
                with self.db:
                    self.db.execute("UPDATE download_jobs SET state='queued', fraction=0 WHERE state='downloading'")
                self._collect_garbage()
            finally:
                lock.unlock()

    def schedule(self, body):
        identifier = body["kind"] + ":" + body["id"]
        previous = self.db.execute("SELECT body FROM collections WHERE id=?", (identifier,)).fetchone()
        if previous:
            old = json.loads(previous[0])
            for key in ("thumbnail", "localThumbnail"):
                body[key] = body.get(key) or old.get(key, "")
            old_tracks = {track["videoId"]: track for track in old["items"]}
            for track in body["items"]:
                before = old_tracks.get(track["videoId"], {})
                for key in ("thumbnail", "localThumbnail"):
                    track[key] = track.get(key) or before.get(key, "")
        with self.db:
            self.db.execute("INSERT INTO collections VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET body=excluded.body", (identifier, json.dumps(body)))
            self.db.execute("INSERT OR REPLACE INTO download_jobs VALUES (?, 'queued', 0, ?, 0, '', ?)", (identifier, len(body["items"]), time.time()))
            # Retain the previous snapshot's files until its replacement completes.
            self.db.executemany("INSERT OR IGNORE INTO media_refs VALUES (?, ?)", [(identifier, track["videoId"]) for track in body["items"] if VIDEO_ID.fullmatch(track["videoId"])])
        return identifier

    def collection(self, identifier):
        row = self.db.execute("SELECT body FROM collections WHERE id=?", (identifier,)).fetchone()
        if not row:
            raise DownloadError("This download was removed. Choose the music again.")
        return json.loads(row[0])

    def update_body(self, identifier, body):
        with self.db:
            self.db.execute("UPDATE collections SET body=? WHERE id=?", (json.dumps(body), identifier))

    def state(self, identifier):
        row = self.db.execute("SELECT state FROM download_jobs WHERE collection_id=?", (identifier,)).fetchone()
        return row[0] if row else "removed"

    def progress(self, identifier, completed, total, fraction=0, error="", state="downloading"):
        with self.db:
            self.db.execute("""UPDATE download_jobs SET state=?, completed=?, total=?, fraction=?, error=?
                WHERE collection_id=? AND state NOT IN ('cancelled')""", (state, completed, total, min(1., max(0., fraction)), error, identifier))

    def cancel(self, identifier):
        with self.db:
            self.db.execute("UPDATE download_jobs SET state='cancelled', error='Cancelled. Completed songs were kept.' WHERE collection_id=?", (identifier,))

    def retry(self, identifier):
        with self.db:
            self.db.execute("UPDATE download_jobs SET state='queued', error='', fraction=0 WHERE collection_id=?", (identifier,))

    def complete(self, identifier):
        videos = {track["videoId"] for track in self.collection(identifier)["items"] if VIDEO_ID.fullmatch(track["videoId"])}
        with self.db:
            old = self.db.execute("SELECT video_id FROM media_refs WHERE collection_id=?", (identifier,)).fetchall()
            self.db.executemany("DELETE FROM media_refs WHERE collection_id=? AND video_id=?", [(identifier, row[0]) for row in old if row[0] not in videos])
        self._collect_garbage()

    def remove(self, identifier):
        with self.db:
            self.db.execute("DELETE FROM collections WHERE id=?", (identifier,))
        self._collect_garbage()

    def _unlink(self, path):
        path = Path(path).resolve()
        if not path.is_relative_to(self.root) or path.suffix == ".sqlite3":
            return
        try:
            path.unlink(missing_ok=True)
            self.db.execute("DELETE FROM pending_delete WHERE path=?", (str(path),))
        except OSError:
            self.db.execute("INSERT OR IGNORE INTO pending_delete VALUES (?)", (str(path),))

    def _collect_garbage(self):
        with self.db:
            rows = self.db.execute("SELECT video_id, path FROM audio WHERE video_id NOT IN (SELECT video_id FROM media_refs)").fetchall()
            for video_id, relative in rows:
                path = (self.root / relative).resolve()
                if path.is_relative_to(self.root / "audio"):
                    self._unlink(path)
                self.db.execute("DELETE FROM audio WHERE video_id=?", (video_id,))
            referenced = {row[0] for row in self.db.execute("SELECT video_id FROM media_refs")}
            staging = self.root / "staging"
            if staging.is_dir():
                for path in staging.iterdir():
                    video_id = path.name.split(".", 1)[0]
                    if VIDEO_ID.fullmatch(video_id) and video_id not in referenced:
                        self._unlink(path)
            images = set()
            for row in self.db.execute("SELECT body FROM collections"):
                body = json.loads(row[0])
                images.add(body.get("localThumbnail", ""))
                images.update(track.get("localThumbnail", "") for track in body["items"])
            protected = images | {(self.root / row[0]).resolve().as_uri() for row in self.db.execute("SELECT path FROM audio")}
            for row in self.db.execute("SELECT path FROM pending_delete").fetchall():
                if Path(row[0]).resolve().as_uri() in protected:
                    self.db.execute("DELETE FROM pending_delete WHERE path=?", (row[0],))
                else:
                    self._unlink(row[0])
            art = self.root / "artwork"
            if art.is_dir():
                for path in art.iterdir():
                    if path.as_uri() not in images:
                        self._unlink(path)

    def status(self):
        collections = []
        ready, track_states, artwork = {}, {}, {}
        for identifier, raw, state, completed, total, fraction, error in self.db.execute("""SELECT c.id, c.body, j.state, j.completed, j.total, j.fraction, j.error
            FROM collections c JOIN download_jobs j ON c.id=j.collection_id ORDER BY j.created DESC""").fetchall():
            body = json.loads(raw)
            artwork[identifier] = self._artwork_uri(body.get("localThumbnail", ""))
            for track in body["items"]:
                video_id = track["videoId"]
                if video_id not in ready:
                    ready[video_id] = self.media.ready(video_id) is not None
                status = "ready" if ready[video_id] else "damaged" if state == "complete" else state
                if track_states.get(video_id) != "ready":
                    track_states[video_id] = status
                local_art = self._artwork_uri(track.get("localThumbnail", ""))
                if local_art or video_id not in artwork:
                    artwork[video_id] = local_art
            count = sum(ready[track["videoId"]] for track in body["items"])
            damaged = state == "complete" and count < total
            collections.append({"key": identifier, "id": body["id"], "kind": body["kind"], "title": body["title"], "thumbnail": body.get("localThumbnail") or body.get("thumbnail", ""), "state": "damaged" if damaged else state, "ready": count, "total": total, "progress": (completed + fraction) / max(1, total), "error": error})
        next_row = self.db.execute("SELECT collection_id FROM download_jobs WHERE state='queued' ORDER BY created LIMIT 1").fetchone()
        used = self.db.execute("SELECT coalesce(sum(bytes),0) FROM audio WHERE state='ready'").fetchone()[0]
        return {"collections": collections, "trackStates": track_states, "artwork": artwork, "next": next_row[0] if next_row else None, "bytes": used, "freeBytes": shutil.disk_usage(self.root).free}

    def _artwork_uri(self, value):
        from PySide6.QtCore import QUrl

        if not isinstance(value, str):
            return ""
        try:
            url = QUrl(value)
            if url.isLocalFile():
                path = Path(url.toLocalFile()).resolve()
                if path.is_relative_to(self.root / "artwork") and path.is_file():
                    return value
        except (OSError, ValueError, RuntimeError):
            pass
        return ""

    def lookup(self, kind, identifier):
        key = kind + ":" + identifier
        if not self.db.execute("SELECT 1 FROM collections WHERE id=?", (key,)).fetchone():
            return {}
        return self.view(key)

    def view(self, identifier):
        body = self.collection(identifier)
        body["downloadKey"] = identifier
        body["trackCount"] = len(body["items"])
        body["duration"] = sum(track.get("duration", 0) for track in body["items"])
        body["cursor"] = None
        for track in body["items"]:
            ready = self.media.ready(track["videoId"])
            track["downloadState"] = "ready" if ready else "missing"
            track["available"] = bool(ready) or track.get("available", True)
            track["thumbnail"] = track.get("localThumbnail") or track.get("thumbnail", "")
        body["thumbnail"] = body.get("localThumbnail") or body.get("thumbnail", "")
        if body["kind"] == "album" and body["items"]:
            body["artists"] = body["items"][0].get("artists", [])
        return body

    def close(self):
        self.media.close()


class Downloads:
    def __init__(self, auth, data_dir, progress=None, extractor_factory=None, artwork_fetch=cache_artwork):
        self.auth, self.store = auth, DownloadStore(data_dir)
        self.notify = progress or (lambda value: None)
        self.extractor_factory, self.artwork_fetch = extractor_factory, artwork_fetch

    def schedule(self, media):
        kind, identifier = media.get("kind", "song"), text(media.get("id") or media.get("videoId"))
        if kind not in {"song", "album", "playlist"} or not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", identifier):
            raise DownloadError("Choose a song, album or playlist to download.")
        if kind == "song":
            tracks, title, art = [clean_track(media)], text(media.get("title")), text(media.get("thumbnail"))
            if not tracks[0]["available"] and not self.store.media.ready(tracks[0]["videoId"]):
                raise DownloadError("This song is unavailable for download.")
        else:
            client = self.auth.catalog()
            raw = client.get_album(identifier) if kind == "album" else client.get_playlist(identifier, limit=None)
            title, art = text(raw.get("title")), thumbnail(raw.get("thumbnails"))
            tracks = items(raw.get("tracks", []), "song")
            for track in tracks:
                track["thumbnail"] = track["thumbnail"] or art
                if kind == "album":
                    track["album"] = {"id": identifier, "name": title}
                    if not track["artist"]:
                        track["artists"] = raw.get("artists") or []
                        track["artist"] = " • ".join(text(a.get("name")) for a in track["artists"])
            tracks = [clean_track(track) for track in tracks]
        if not tracks or not title:
            raise DownloadError("This collection has no music available to download.")
        body = {"kind": kind, "id": identifier, "title": title, "thumbnail": art if art.startswith("https://") else "", "items": tracks}
        return self.store.schedule(body)

    def run(self, identifier):
        from PySide6.QtCore import QLockFile

        body = self.store.collection(identifier)
        lock = QLockFile(str(self.store.root / "transfer.lock"))
        lock.setStaleLockTime(0)
        if not lock.tryLock(0):
            raise DownloadError("Another download is running. Wait for it to finish and retry.")
        total, completed, unavailable = len(body["items"]), 0, 0
        staging, audio = self.store.root / "staging", self.store.root / "audio"
        extractor, last_progress = None, [0.]

        def report(fraction=0., byte_count=0):
            self.store.progress(identifier, completed, total, fraction)
            self.notify({"collection": identifier, "completed": completed, "total": total, "fraction": fraction, "bytes": max(0, int(byte_count))})

        def hook(value):
            if self.store.state(identifier) in {"cancelled", "removed"}:
                raise DownloadCancelled("Download cancelled. Completed songs were kept.")
            now = time.monotonic()
            if now - last_progress[0] >= 0.5:
                downloaded = value.get("downloaded_bytes") or 0
                size = value.get("total_bytes") or value.get("total_bytes_estimate") or 0
                report(min(0.99, downloaded / size) if size else 0, downloaded)
                last_progress[0] = now

        try:
            staging.mkdir(exist_ok=True, mode=0o700)
            audio.mkdir(exist_ok=True, mode=0o700)
            if self.store.state(identifier) in {"cancelled", "removed"}:
                raise DownloadCancelled("Download cancelled. Completed songs were kept.")
            with ExitStack() as stack:
                report()
                for track in body["items"]:
                    if self.store.state(identifier) in {"cancelled", "removed"}:
                        raise DownloadCancelled("Download cancelled. Completed songs were kept.")
                    video_id = track["videoId"]
                    ready = self.store.media.ready(video_id)
                    if not track["available"] and not ready:
                        unavailable += 1
                        completed += 1
                        report()
                        continue
                    if not ready:
                        if extractor is None:
                            if self.auth.session is None:
                                self.auth.restore()
                            if self.auth.session is None:
                                raise DownloadError("Reconnect YouTube Music to finish this download. Completed songs were kept.")
                            from yt_dlp import YoutubeDL

                            options = extractor_options(staging)
                            options.update(outtmpl=str(staging / "%(id)s.%(ext)s"), noplaylist=True, continuedl=True, progress_hooks=[hook], cachedir=str(self.store.root / "extractor-cache"))
                            extractor = stack.enter_context((self.extractor_factory or YoutubeDL)(options))
                            for cookie in self.auth.session.cookie_jar():
                                extractor.cookiejar.set_cookie(cookie)
                        info = extractor.extract_info("https://www.youtube.com/watch?v=" + video_id, download=True)
                        if not info or info.get("id") != video_id or info.get("ext") not in EXTENSIONS or info.get("vcodec") != "none":
                            raise DownloadError("No supported audio-only format was downloaded for this song.")
                        temporary = staging / (video_id + "." + info["ext"])
                        target = audio / temporary.name
                        try:
                            self.store.media.publish(video_id, temporary, target)
                        except (ProbeError, subprocess.CalledProcessError, ValueError):
                            temporary.unlink(missing_ok=True)
                            raise DownloadError("Downloaded audio failed validation. Retry to download this song again.") from None
                        with self.store.db:
                            for partial in staging.glob(video_id + ".*"):
                                self.store._unlink(partial)
                    art = self.artwork_fetch(track.get("thumbnail", ""), self.store.root / "artwork")
                    if art:
                        track["localThumbnail"] = art
                    completed += 1
                    self.store.update_body(identifier, body)
                    report()
                art = self.artwork_fetch(body.get("thumbnail", ""), self.store.root / "artwork")
                if art:
                    body["localThumbnail"] = art
                    self.store.update_body(identifier, body)
                state = "partial" if unavailable else "complete"
                message = f"{unavailable} unavailable songs were skipped." if unavailable else ""
                self.store.progress(identifier, completed, total, error=message, state=state)
                self.store.complete(identifier)
                return self.store.status()
        except DownloadCancelled:
            raise
        except Exception as error:
            if self.store.state(identifier) in {"cancelled", "removed"}:
                raise DownloadCancelled("Download cancelled. Completed songs were kept.") from None
            message = "The download failed. Check your connection, available space and account, then retry. Completed songs were kept."
            if getattr(error, "errno", None) == errno.ENOSPC or getattr(error, "sqlite_errorcode", None) == sqlite3.SQLITE_FULL:
                message = "The disk is full. Free space and retry. Completed songs were kept."
            elif isinstance(error, DownloadError):
                message = str(error)
            try:
                self.store.progress(identifier, completed, total, error=message, state="failed")
            except sqlite3.Error:
                pass
            raise DownloadError(message) from None
        finally:
            lock.unlock()

    def close(self):
        self.store.close()
