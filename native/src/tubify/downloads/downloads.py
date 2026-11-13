"""Durable collection snapshots and resumable, deduplicated audio downloads."""

from contextlib import ExitStack
import errno
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import time

from ..catalog.catalog import items, text, thumbnail
from ..artwork.artwork_sources import apply_artwork, media_variants
from ..compat import ProbeError, extractor_options
from ..playback.media import MediaFiles
from ..util import atomic_write
from . import saved_files


VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")
EXTENSIONS = {"webm", "m4a", "mp4", "opus", "ogg", "aac", "mp3", "mkv", "mka", "flac", "wav"}


class DownloadError(RuntimeError):
    pass


class DownloadCancelled(DownloadError):
    pass


class DownloadBlocked(DownloadError):
    """A cause (account, full disk, another transfer) that would fail every queued collection."""


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
        "largeThumbnail": apply_artwork({}, media_variants(value)).get("largeThumbnail", ""),
        "artworkVariants": media_variants(value),
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
        atomic_write(target, content)
        return target.as_uri()
    except (requests.RequestException, OSError):
        return ""


TABLES = """
    CREATE TABLE IF NOT EXISTS collections (id TEXT PRIMARY KEY, body TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS collection_jobs (
        collection_id TEXT PRIMARY KEY REFERENCES collections(id) ON DELETE CASCADE,
        cancelled INTEGER NOT NULL, finished INTEGER NOT NULL, created REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS song_jobs (
        video_id TEXT PRIMARY KEY, state TEXT NOT NULL, fraction REAL NOT NULL, error TEXT NOT NULL,
        queued REAL NOT NULL, position INTEGER NOT NULL, track TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS media_refs (
        collection_id TEXT REFERENCES collections(id) ON DELETE CASCADE,
        video_id TEXT NOT NULL, PRIMARY KEY (collection_id, video_id));
    CREATE TABLE IF NOT EXISTS pending_delete (path TEXT PRIMARY KEY);
    CREATE TABLE IF NOT EXISTS exports (
        collection_id TEXT PRIMARY KEY REFERENCES collections(id) ON DELETE CASCADE,
        folder TEXT NOT NULL, state TEXT NOT NULL, saved INTEGER NOT NULL, error TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS saved_files (
        video_id TEXT NOT NULL, folder TEXT NOT NULL, path TEXT NOT NULL, PRIMARY KEY (video_id, folder));
"""
CANCELLED = "Download cancelled. Completed songs were kept."
STOPPED = "Download stopped. Retry to continue; completed songs were kept."


class DownloadStore:
    """Collection snapshots whose songs are each queued and downloaded once.

    A collection's state is worked out from its songs: a song shared by several
    playlists has one job and one file, and a playlist counts as downloaded as soon
    as every available song in it is, however it got there.
    """

    def __init__(self, data_dir):
        self.media = MediaFiles(Path(data_dir) / "media")
        self.root, self.db = self.media.root, self.media.db
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.executescript(TABLES)
        self._migrate()

    def _migrate(self):
        """Turn the old one-job-per-collection queue into song jobs."""
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            if not self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='download_jobs'").fetchone():
                return
            ready = {row[0] for row in self.db.execute("SELECT video_id FROM audio WHERE state='ready'")}
            for identifier, state, error, created, raw in self.db.execute("""SELECT j.collection_id, j.state, j.error, j.created, c.body
                    FROM download_jobs j JOIN collections c ON c.id=j.collection_id""").fetchall():
                self.db.execute("INSERT OR IGNORE INTO collection_jobs VALUES (?, ?, ?, ?)", (identifier, int(state == "cancelled"), int(state in {"complete", "partial"}), created))
                if state in {"queued", "downloading", "failed"}:
                    self._queue(json.loads(raw), ready, created, "failed" if state == "failed" else "queued", error if state == "failed" else "")
            self.db.execute("DROP TABLE download_jobs")

    def _queue(self, body, ready, when, state="queued", error=""):
        """Queue the collection's missing songs. A song that is already queued keeps its place."""
        self.db.executemany("""INSERT INTO song_jobs VALUES (?, ?, 0, ?, ?, ?, ?)
            ON CONFLICT(video_id) DO UPDATE SET state=excluded.state, fraction=0, error=excluded.error,
                queued=excluded.queued, position=excluded.position, track=excluded.track
            WHERE song_jobs.state IN ('failed', 'cancelled')""",
            [(track["videoId"], state, error, when, index, json.dumps(track)) for index, track in enumerate(body["items"])
             if VIDEO_ID.fullmatch(track["videoId"]) and track.get("available", True) and track["videoId"] not in ready])

    def _verified(self, body):
        return {video_id for video_id in {track["videoId"] for track in body["items"]} if VIDEO_ID.fullmatch(video_id) and self.media.ready(video_id)}

    def _prune(self):
        """Drop jobs no collection holds, and stop songs only cancelled collections still want."""
        self.db.execute("DELETE FROM song_jobs WHERE video_id NOT IN (SELECT video_id FROM media_refs)")
        self.db.execute("""UPDATE song_jobs SET state='cancelled', fraction=0, error=? WHERE state IN ('queued', 'downloading')
            AND video_id NOT IN (SELECT r.video_id FROM media_refs r JOIN collection_jobs j ON j.collection_id=r.collection_id WHERE j.cancelled=0)""", (CANCELLED,))

    def recover(self):
        from PySide6.QtCore import QLockFile

        lock = QLockFile(str(self.root / "transfer.lock"))
        lock.setStaleLockTime(0)
        if lock.tryLock(0):
            try:
                with self.db:
                    self.db.execute("UPDATE song_jobs SET state='queued', fraction=0 WHERE state='downloading'")
                    self.db.execute("UPDATE exports SET state='pending' WHERE state='saving'")
                self._collect_garbage()
            finally:
                lock.unlock()

    def schedule(self, body, files=""):
        identifier = body["kind"] + ":" + body["id"]
        previous = self.db.execute("SELECT body FROM collections WHERE id=?", (identifier,)).fetchone()
        if previous:
            old = json.loads(previous[0])
            for key in ("thumbnail", "localThumbnail", "largeThumbnail", "artworkVariants"):
                body[key] = body.get(key) or old.get(key, "")
            old_tracks = {track["videoId"]: track for track in old["items"]}
            for track in body["items"]:
                before = old_tracks.get(track["videoId"], {})
                for key in ("thumbnail", "localThumbnail", "largeThumbnail", "artworkVariants"):
                    track[key] = track.get(key) or before.get(key, "")
        ready, now = self._verified(body), time.time()
        with self.db:
            self.db.execute("INSERT INTO collections VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET body=excluded.body", (identifier, json.dumps(body)))
            self.db.execute("INSERT OR REPLACE INTO collection_jobs VALUES (?, 0, 0, ?)", (identifier, now))
            # Retain the previous snapshot's files until its replacement completes.
            self.db.executemany("INSERT OR IGNORE INTO media_refs VALUES (?, ?)", [(identifier, track["videoId"]) for track in body["items"] if VIDEO_ID.fullmatch(track["videoId"])])
            self._queue(body, ready, now)
        if files:
            self.request_files(identifier, files)
        return identifier

    # Audio files saved to a folder the person chose, after a collection's songs are downloaded.
    def request_files(self, identifier, folder):
        if not self.db.execute("SELECT 1 FROM collections WHERE id=?", (identifier,)).fetchone():
            raise DownloadError("This download was removed. Choose the music again.")
        with self.db:
            self.db.execute("""INSERT INTO exports VALUES (?, ?, 'pending', 0, '') ON CONFLICT(collection_id)
                DO UPDATE SET folder=excluded.folder, state='pending', saved=0, error=''""", (identifier, str(folder)))

    def export(self, identifier):
        row = self.db.execute("SELECT folder, state, saved, error FROM exports WHERE collection_id=?", (identifier,)).fetchone()
        return dict(zip(("folder", "state", "saved", "error"), row)) if row else None

    def next_export(self, collection=None, exclude=()):
        """A collection whose songs are all downloaded and whose files are still to save."""
        jobs, ready = self._jobs(), {}
        for identifier, raw in self.db.execute("""SELECT c.id, c.body FROM exports e JOIN collections c ON c.id=e.collection_id
                WHERE e.state='pending' ORDER BY c.rowid""").fetchall():
            if identifier not in exclude and (collection is None or identifier == collection):
                if self._summary(json.loads(raw), 0, jobs, ready)["state"] == "complete":
                    return identifier
        return None

    def set_export(self, identifier, state, saved=None, error=""):
        with self.db:
            if saved is None:
                return self.db.execute("UPDATE exports SET state=?, error=? WHERE collection_id=?", (state, error, identifier)).rowcount == 1
            return self.db.execute("UPDATE exports SET state=?, saved=?, error=? WHERE collection_id=?", (state, saved, error, identifier)).rowcount == 1

    def saved_file(self, video_id, folder):
        row = self.db.execute("SELECT path FROM saved_files WHERE video_id=? AND folder=?", (video_id, str(folder))).fetchone()
        return row[0] if row and Path(row[0]).is_file() else None

    def record_saved(self, video_id, folder, path):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO saved_files VALUES (?, ?, ?)", (video_id, str(folder), str(path)))

    def collection(self, identifier):
        row = self.db.execute("SELECT body FROM collections WHERE id=?", (identifier,)).fetchone()
        if not row:
            raise DownloadError("This download was removed. Choose the music again.")
        return json.loads(row[0])

    def update_body(self, identifier, body):
        from ..artwork.large_artwork import local_image
        from ..artwork.artwork_sources import quality

        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            current = self.db.execute("SELECT body FROM collections WHERE id=?", (identifier,)).fetchone()
            if not current:
                return
            previous = {track["videoId"]: track for track in json.loads(current[0])["items"]}
            for track in body["items"]:
                old = previous.get(track["videoId"], {})
                before = local_image(self._artwork_uri(old.get("localThumbnail", "")))
                after = local_image(self._artwork_uri(track.get("localThumbnail", "")))
                if quality(before) > quality(after):
                    track["localThumbnail"] = before["url"]
                apply_artwork(track, media_variants(track) + media_variants(old))
            self.db.execute("UPDATE collections SET body=? WHERE id=?", (json.dumps(body), identifier))

    def state(self, identifier):
        row = self.db.execute("""SELECT c.body, j.cancelled FROM collections c JOIN collection_jobs j ON c.id=j.collection_id
            WHERE c.id=?""", (identifier,)).fetchone()
        return self._summary(json.loads(row[0]), row[1], self._jobs(), {})["state"] if row else "removed"

    def _jobs(self):
        return {row[0]: row[1:] for row in self.db.execute("SELECT video_id, state, fraction, error FROM song_jobs")}

    def _summary(self, body, cancelled, jobs, ready):
        """A collection's state from its songs; ready caches media.ready across collections."""
        needed = done = unavailable = 0
        fraction, states, errors = 0., set(), []
        for track in body["items"]:
            video_id = track["videoId"]
            if video_id not in ready:
                ready[video_id] = bool(VIDEO_ID.fullmatch(video_id)) and self.media.ready(video_id) is not None
            if ready[video_id]:
                needed, done = needed + 1, done + 1
                continue
            if not track.get("available", True) or not VIDEO_ID.fullmatch(video_id):
                unavailable += 1
                continue
            needed += 1
            job = jobs.get(video_id)
            states.add(job[0] if job else "missing")
            if job and job[0] == "downloading":
                fraction = max(fraction, job[1])
            if job and job[0] == "failed" and job[2]:
                errors.append(job[2])
        if done == needed:
            state = "complete"
        elif cancelled:
            state = "cancelled"
        else:
            state = next((value for value in ("downloading", "queued", "failed", "cancelled") if value in states), "damaged")
        error = errors[0] if state == "failed" and errors else CANCELLED if state == "cancelled" else f"{unavailable} unavailable songs were skipped." if state == "complete" and unavailable else ""
        return {"state": state, "ready": done, "total": len(body["items"]), "progress": (done + fraction) / max(1, needed), "error": error}

    def cancel(self, identifier):
        with self.db:
            self.db.execute("UPDATE collection_jobs SET cancelled=1 WHERE collection_id=?", (identifier,))
            self.db.execute("UPDATE exports SET state='cancelled' WHERE collection_id=? AND state IN ('pending', 'saving')", (identifier,))
            self._prune()

    def retry(self, identifier):
        body = self.collection(identifier)
        ready = self._verified(body)
        with self.db:
            self.db.execute("UPDATE collection_jobs SET cancelled=0, finished=0 WHERE collection_id=?", (identifier,))
            self.db.execute("UPDATE exports SET state='pending', error='' WHERE collection_id=? AND state IN ('failed', 'cancelled')", (identifier,))
            self._queue(body, ready, time.time())

    def stop(self, message=STOPPED):
        """Mark the song a lost transfer was downloading as failed so it can be retried."""
        with self.db:
            self.db.execute("UPDATE song_jobs SET state='failed', fraction=0, error=? WHERE state='downloading'", (message,))
            self.db.execute("UPDATE exports SET state='failed', error=? WHERE state='saving'", (message,))

    def complete(self, identifier):
        videos = {track["videoId"] for track in self.collection(identifier)["items"] if VIDEO_ID.fullmatch(track["videoId"])}
        with self.db:
            old = self.db.execute("SELECT video_id FROM media_refs WHERE collection_id=?", (identifier,)).fetchall()
            self.db.executemany("DELETE FROM media_refs WHERE collection_id=? AND video_id=?", [(identifier, row[0]) for row in old if row[0] not in videos])
            self.db.execute("UPDATE collection_jobs SET finished=1 WHERE collection_id=?", (identifier,))
            self._prune()
        self._collect_garbage()

    def remove(self, identifier):
        with self.db:
            self.db.execute("DELETE FROM collections WHERE id=?", (identifier,))
            self._prune()
        self._collect_garbage()

    def next_song(self, collection=None, exclude=()):
        """The next queued song as (videoId, track), optionally only from one collection."""
        query, values = "SELECT video_id, track FROM song_jobs WHERE state='queued'", ()
        if collection:
            query, values = query + " AND video_id IN (SELECT video_id FROM media_refs WHERE collection_id=?)", (collection,)
        for video_id, track in self.db.execute(query + " ORDER BY queued, position", values):
            if video_id not in exclude:
                return video_id, json.loads(track)
        return None

    def unfinished(self, collection=None, exclude=()):
        """A collection whose songs are all here but whose cover and cleanup are still to do."""
        rows = self.db.execute("""SELECT c.id, c.body FROM collections c JOIN collection_jobs j ON c.id=j.collection_id
            WHERE j.finished=0 AND j.cancelled=0 ORDER BY j.created""").fetchall()
        jobs, ready = self._jobs(), {}
        for identifier, raw in rows:
            if identifier not in exclude and (collection is None or identifier == collection):
                if self._summary(json.loads(raw), 0, jobs, ready)["state"] == "complete":
                    return identifier
        return None

    def start_song(self, video_id):
        with self.db:
            return self.db.execute("UPDATE song_jobs SET state='downloading', fraction=0, error='' WHERE video_id=? AND state='queued'", (video_id,)).rowcount == 1

    def song_state(self, video_id):
        row = self.db.execute("SELECT state FROM song_jobs WHERE video_id=?", (video_id,)).fetchone()
        return row[0] if row else "removed"

    def song_progress(self, video_id, fraction):
        with self.db:
            self.db.execute("UPDATE song_jobs SET fraction=? WHERE video_id=? AND state='downloading'", (min(1., max(0., fraction)), video_id))

    def song_failed(self, video_id, message):
        with self.db:
            self.db.execute("UPDATE song_jobs SET state='failed', fraction=0, error=? WHERE video_id=? AND state='downloading'", (message, video_id))

    def song_done(self, video_id, art=""):
        """Finish a song's job and give every collection holding it the cached cover."""
        from ..artwork.large_artwork import local_image
        from ..artwork.artwork_sources import quality

        new = quality(local_image(self._artwork_uri(art))) if art else 0
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            self.db.execute("DELETE FROM song_jobs WHERE video_id=?", (video_id,))
            if not art:
                return
            for identifier, raw in self.db.execute("""SELECT c.id, c.body FROM collections c JOIN media_refs r ON r.collection_id=c.id
                    WHERE r.video_id=?""", (video_id,)).fetchall():
                body, changed = json.loads(raw), False
                for track in body["items"]:
                    if track["videoId"] == video_id and new >= quality(local_image(self._artwork_uri(track.get("localThumbnail", "")))):
                        track["localThumbnail"], changed = art, True
                if changed:
                    self.db.execute("UPDATE collections SET body=? WHERE id=?", (json.dumps(body), identifier))

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
        jobs, ready = self._jobs(), {}
        collections, songs, collection_states = [], {}, {}
        track_states, track_progress, artwork = {}, {}, {}
        exports = {row[0]: dict(zip(("folder", "state", "saved", "error"), row[1:])) for row in self.db.execute("SELECT collection_id, folder, state, saved, error FROM exports")}
        for identifier, raw, cancelled, created in self.db.execute("""SELECT c.id, c.body, j.cancelled, j.created
                FROM collections c JOIN collection_jobs j ON c.id=j.collection_id ORDER BY j.created DESC""").fetchall():
            body = json.loads(raw)
            summary = self._summary(body, cancelled, jobs, ready)
            if identifier in exports:
                summary["files"] = {**exports[identifier], "total": summary["ready"]}
            artwork[identifier] = self._artwork_uri(body.get("localThumbnail", ""))
            for track in body["items"]:
                video_id = track["videoId"]
                job = jobs.get(video_id)
                state = "ready" if ready[video_id] else job[0] if job else "unavailable" if not track.get("available", True) else "damaged"
                if track_states.get(video_id) in {None, "unavailable", "damaged"}:
                    track_states[video_id] = state
                if job and job[0] == "downloading":
                    track_progress[video_id] = job[1]
                local_art = self._artwork_uri(track.get("localThumbnail", ""))
                if local_art or video_id not in artwork:
                    artwork[video_id] = local_art
                if state != "unavailable" and VIDEO_ID.fullmatch(video_id):
                    if video_id in songs:
                        songs[video_id]["added"] = min(songs[video_id]["added"], created)
                    else:
                        songs[video_id] = {**{key: value for key, value in track.items() if key != "artworkVariants"},
                                           "thumbnail": local_art or track.get("thumbnail", ""), "added": created}
            collection_states[identifier] = summary["state"]
            collections.append({"key": identifier, "id": body["id"], "kind": body["kind"], "title": body["title"],
                                "thumbnail": body.get("localThumbnail") or body.get("thumbnail", ""), "added": created, **summary})
        for video_id, song in songs.items():
            song["downloadState"] = track_states[video_id]
        queued = self.db.execute("SELECT video_id FROM song_jobs WHERE state='queued' ORDER BY queued, position LIMIT 1").fetchone()
        finishing = self.db.execute("SELECT 1 FROM collection_jobs WHERE finished=0 AND cancelled=0").fetchone()
        next_row = queued[0] if queued else ("finish" if finishing and self.unfinished() else "save" if self.next_export() else None)
        used = self.db.execute("SELECT coalesce(sum(bytes),0) FROM audio WHERE state='ready'").fetchone()[0]
        return {"collections": collections, "songs": list(songs.values()), "collectionStates": collection_states,
                "trackStates": track_states, "trackProgress": track_progress, "artwork": artwork, "next": next_row,
                "bytes": used, "freeBytes": shutil.disk_usage(self.root).free}

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
        self._extractor, self._stack, self._hook = None, None, None

    def schedule(self, media, files=""):
        kind, identifier = media.get("kind", "song"), text(media.get("id") or media.get("videoId"))
        if kind not in {"song", "album", "playlist"} or not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", identifier):
            raise DownloadError("Choose a song, album or playlist to download.")
        if kind == "song":
            tracks, title, art = [clean_track(media)], text(media.get("title")), text(media.get("thumbnail"))
            artwork = media_variants(media)
            if not tracks[0]["available"] and not self.store.media.ready(tracks[0]["videoId"]):
                raise DownloadError("This song is unavailable for download.")
        else:
            client = self.auth.catalog()
            raw = client.get_album(identifier) if kind == "album" else client.get_playlist(identifier, limit=None)
            title, art = text(raw.get("title")), thumbnail(raw.get("thumbnails"))
            artwork = media_variants({"artworkVariants": raw.get("thumbnails", [])})
            tracks = items(raw.get("tracks", []), "song")
            for track in tracks:
                track["thumbnail"] = track["thumbnail"] or art
                if kind == "album":
                    track["album"] = {"id": identifier, "name": title}
                    apply_artwork(track, media_variants(track) + artwork)
                    if not track["artist"]:
                        track["artists"] = raw.get("artists") or []
                        track["artist"] = " • ".join(text(a.get("name")) for a in track["artists"])
            tracks = [clean_track(track) for track in tracks]
        if not tracks or not title:
            raise DownloadError("This collection has no music available to download.")
        body = {"kind": kind, "id": identifier, "title": title, "thumbnail": art if art.startswith("https://") else "", "items": tracks}
        apply_artwork(body, artwork)
        return self.store.schedule(body, files)

    def schedule_all(self, playlists, files=""):
        """Queue every playlist that is not already queued or downloaded, in one request."""
        scheduled, failed = 0, 0
        for media in playlists:
            if not isinstance(media, dict):
                continue
            key = "playlist:" + text(media.get("id"))
            if self.store.state(key) in {"queued", "downloading", "complete"}:
                if files and not self.store.export(key):
                    # Already downloaded, but its files weren't saved yet.
                    self.store.request_files(key, files)
                continue
            try:
                self.schedule({**media, "kind": "playlist"}, files)
                scheduled += 1
            except Exception:
                # One unavailable or empty playlist must not stop the rest of the library.
                failed += 1
            # Lets the view start transfers as soon as each playlist is queued.
            self.notify({"scheduled": scheduled, "failed": failed})
        return {"scheduled": scheduled, "failed": failed}

    def run_queue(self, identifier=None):
        """Download every queued song, then finish collections that are whole, in this one process.

        Starting a new worker process for each collection made a long queue (such as a
        whole library) relaunch the app over and over, which slowed the machine down.
        A song that fails is marked on its job and the rest of the queue carries on.
        """
        return self._drain()

    def run(self, identifier):
        """Download one collection's queued songs; the first failure stops and is raised."""
        if self.store.state(identifier) in {"cancelled", "removed"}:
            raise DownloadCancelled(CANCELLED)
        return self._drain(identifier)

    def _drain(self, collection=None):
        from PySide6.QtCore import QLockFile

        lock = QLockFile(str(self.store.root / "transfer.lock"))
        lock.setStaleLockTime(0)
        if not lock.tryLock(0):
            raise DownloadBlocked("Another download is running. Wait for it to finish and retry.")
        attempted, finished, exported = set(), set(), set()
        try:
            for folder in ("staging", "audio"):
                (self.store.root / folder).mkdir(exist_ok=True, mode=0o700)
            with ExitStack() as stack:
                self._stack = stack
                while True:
                    job = self.store.next_song(collection, attempted)
                    if job:
                        attempted.add(job[0])
                        try:
                            self._download(*job)
                        except DownloadBlocked:
                            raise
                        except DownloadError:
                            # The failure is recorded on that song and the rest of the queue continues.
                            if collection:
                                raise
                        continue
                    identifier = self.store.unfinished(collection, finished)
                    if identifier is not None:
                        finished.add(identifier)
                        self._finish(identifier)
                        continue
                    identifier = self.store.next_export(collection, exported)
                    if identifier is None:
                        break
                    exported.add(identifier)
                    self._save_files(identifier)
        finally:
            self._extractor, self._stack, self._hook = None, None, None
            lock.unlock()
        # Songs finished after their collection was removed are not kept.
        self.store._collect_garbage()
        return self.store.status()

    def _open_extractor(self):
        if self._extractor is None:
            if self.auth.session is None:
                self.auth.restore()
            if self.auth.session is None:
                raise DownloadBlocked("Reconnect YouTube Music to finish this download. Completed songs were kept.")
            from yt_dlp import YoutubeDL

            staging = self.store.root / "staging"
            options = extractor_options(staging)
            options.update(outtmpl=str(staging / "%(id)s.%(ext)s"), noplaylist=True, continuedl=True,
                           progress_hooks=[lambda value: self._hook(value)], cachedir=str(self.store.root / "extractor-cache"))
            self._extractor = self._stack.enter_context((self.extractor_factory or YoutubeDL)(options))
            for cookie in self.auth.session.cookie_jar():
                self._extractor.cookiejar.set_cookie(cookie)
        return self._extractor

    def _download(self, video_id, track):
        if not self.store.start_song(video_id):
            raise DownloadCancelled(CANCELLED)
        staging, audio = self.store.root / "staging", self.store.root / "audio"
        last_progress = [0.]

        def report(fraction=0., byte_count=0):
            self.store.song_progress(video_id, fraction)
            self.notify({"videoId": video_id, "fraction": fraction, "bytes": max(0, int(byte_count))})

        def hook(value):
            if self.store.song_state(video_id) != "downloading":
                raise DownloadCancelled(CANCELLED)
            now = time.monotonic()
            if now - last_progress[0] >= 0.5:
                downloaded = value.get("downloaded_bytes") or 0
                size = value.get("total_bytes") or value.get("total_bytes_estimate") or 0
                report(min(0.99, downloaded / size) if size else 0, downloaded)
                last_progress[0] = now

        self._hook = hook
        try:
            report()
            if not self.store.media.ready(video_id):
                info = self._open_extractor().extract_info("https://www.youtube.com/watch?v=" + video_id, download=True)
                if not info or info.get("id") != video_id or info.get("ext") not in EXTENSIONS or info.get("vcodec") != "none":
                    raise DownloadError("No supported audio-only format was downloaded for this song.")
                temporary = staging / (video_id + "." + info["ext"])
                try:
                    self.store.media.publish(video_id, temporary, audio / temporary.name)
                except (ProbeError, subprocess.CalledProcessError, ValueError):
                    temporary.unlink(missing_ok=True)
                    raise DownloadError("Downloaded audio failed validation. Retry to download this song again.") from None
                with self.store.db:
                    for partial in staging.glob(video_id + ".*"):
                        self.store._unlink(partial)
            art = self.artwork_fetch(track.get("largeThumbnail") or track.get("thumbnail", ""), self.store.root / "artwork")
            self.store.song_done(video_id, art)
            self.notify({"videoId": video_id, "fraction": 1., "done": True})
        except DownloadCancelled:
            raise
        except Exception as error:
            if self.store.song_state(video_id) != "downloading":
                raise DownloadCancelled(CANCELLED) from None
            message = "The download failed. Check your connection, available space and account, then retry. Completed songs were kept."
            failure = DownloadError
            if getattr(error, "errno", None) == errno.ENOSPC or getattr(error, "sqlite_errorcode", None) == sqlite3.SQLITE_FULL:
                message, failure = "The disk is full. Free space and retry. Completed songs were kept.", DownloadBlocked
            elif isinstance(error, DownloadError):
                message, failure = str(error), type(error)
            try:
                self.store.song_failed(video_id, message)
            except sqlite3.Error:
                pass
            raise failure(message) from None

    def _save_files(self, identifier):
        """Copy a downloaded collection's songs into the chosen folder as tagged audio files."""
        from PySide6.QtCore import QUrl

        export = self.store.export(identifier)
        if not export or not self.store.set_export(identifier, "saving", 0):
            return
        folder, body = export["folder"], self.store.collection(identifier)
        numbered, saved = body["kind"] == "album", 0
        for index, track in enumerate(body["items"]):
            if (self.store.export(identifier) or {}).get("state") != "saving":
                return
            video_id = track["videoId"]
            source = self.store.media.ready(video_id) if VIDEO_ID.fullmatch(video_id) else None
            if source is None:
                continue
            if not self.store.saved_file(video_id, folder):
                art = self.store._artwork_uri(track.get("localThumbnail", "")) or self.store._artwork_uri(body.get("localThumbnail", ""))
                try:
                    path = saved_files.save(source, track, folder, index + 1 if numbered else 0, QUrl(art).toLocalFile() if art else "")
                except saved_files.SaveError as error:
                    self.store.set_export(identifier, "failed", saved, str(error))
                    self.notify({"collection": identifier, "done": True})
                    return
                except OSError as error:
                    full = getattr(error, "errno", None) == errno.ENOSPC
                    message = "The disk is full. Free space and retry. Saved files were kept." if full else "Audio files couldn't be saved. Retry."
                    self.store.set_export(identifier, "failed", saved, message)
                    if full:
                        raise DownloadBlocked(message) from None
                    return
                self.store.record_saved(video_id, folder, path)
            saved += 1
            self.store.set_export(identifier, "saving", saved)
            self.notify({"collection": identifier, "saved": saved})
        self.store.set_export(identifier, "saved", saved)
        self.notify({"collection": identifier, "filesSaved": folder, "done": True})

    def _finish(self, identifier):
        """Save the cover and any missing song covers once every song of a collection is here."""
        body, folder = self.store.collection(identifier), self.store.root / "artwork"
        for track in body["items"]:
            if not self.store._artwork_uri(track.get("localThumbnail", "")) and self.store.media.ready(track["videoId"]):
                track["localThumbnail"] = self.artwork_fetch(track.get("largeThumbnail") or track.get("thumbnail", ""), folder) or track.get("localThumbnail", "")
        art = self.artwork_fetch(body.get("largeThumbnail") or body.get("thumbnail", ""), folder)
        if art:
            body["localThumbnail"] = art
        self.store.update_body(identifier, body)
        self.store.complete(identifier)
        self.notify({"collection": identifier, "done": True})

    def close(self):
        self.store.close()
