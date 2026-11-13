"""Index of the music folders the user chose.

Files are referenced where they are. Nothing here moves, rewrites or deletes an audio file:
removing a folder or a song only removes Tubify's reference to it.
"""

import hashlib
import os
from pathlib import Path
import time
import uuid

from ..catalog.database import connect
from . import tags as tag_reader

# Device and file ids are stored as text: on Windows they can exceed SQLite's 64-bit integers.
TABLES = """
    CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS folders (
        id INTEGER PRIMARY KEY, path TEXT NOT NULL, key TEXT NOT NULL UNIQUE, device TEXT NOT NULL,
        added REAL NOT NULL, scanned REAL NOT NULL, state TEXT NOT NULL, rev INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS songs (
        id TEXT PRIMARY KEY, folder INTEGER NOT NULL REFERENCES folders(id), path TEXT NOT NULL, key TEXT NOT NULL UNIQUE,
        size INTEGER NOT NULL, mtime INTEGER NOT NULL, device TEXT NOT NULL, inode TEXT NOT NULL,
        title TEXT NOT NULL, artist TEXT NOT NULL, album TEXT NOT NULL, album_artist TEXT NOT NULL,
        track INTEGER NOT NULL, disc INTEGER NOT NULL, year INTEGER NOT NULL, duration REAL NOT NULL,
        codec TEXT NOT NULL, sample_rate INTEGER NOT NULL, artwork TEXT NOT NULL, tags_readable INTEGER NOT NULL,
        state TEXT NOT NULL, added REAL NOT NULL, rev INTEGER NOT NULL);
    CREATE INDEX IF NOT EXISTS songs_rev ON songs(rev);
    CREATE INDEX IF NOT EXISTS songs_folder ON songs(folder);
    CREATE TABLE IF NOT EXISTS removed (id TEXT PRIMARY KEY, rev INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS excluded (key TEXT PRIMARY KEY);
"""

# Temporary and in-progress files from downloaders and sync tools.
PARTIAL_SUFFIXES = {".part", ".ytdl", ".tmp", ".temp", ".crdownload", ".download", ".partial", ".!qb", ".aria2"}
# A file changed this recently may still be being written; a later scan picks it up.
SETTLE_SECONDS = 5
FOLDER_ART = ("cover", "folder", "front", "albumart", "album")
ART_SUFFIXES = (".jpg", ".jpeg", ".png")
ART_PIXELS = 600
BATCH = 200
PROGRESS_SECONDS = 0.5


class LibraryError(RuntimeError):
    pass


def path_key(path):
    """One spelling per file, so case-insensitive file systems don't list a song twice."""
    return os.path.normcase(os.path.abspath(path))


def inside(path, folder):
    path, folder = path_key(path), path_key(folder)
    return path == folder or path.startswith(folder.rstrip(os.sep) + os.sep)


def is_audio(name):
    return Path(name).suffix[1:].lower() in tag_reader.EXTENSIONS


def is_partial(name):
    lowered = name.lower()
    return name.startswith(".") or any(lowered.endswith(suffix) for suffix in PARTIAL_SUFFIXES) or ".part-" in lowered


def walk(root):
    """Audio files under root as (path, stat). Hidden folders, such as staging areas, and symbolic links to folders are skipped."""
    pending = [root]
    while pending:
        folder = pending.pop()
        try:
            entries = list(os.scandir(folder))
        except OSError:
            continue
        for entry in sorted(entries, key=lambda item: item.name):
            try:
                if entry.is_dir(follow_symlinks=False):
                    if not entry.name.startswith("."):
                        pending.append(entry.path)
                elif entry.is_file() and is_audio(entry.name) and not is_partial(entry.name):
                    yield entry.path, entry.stat()
            except OSError:
                continue


class LocalLibrary:
    def __init__(self, data_dir):
        self.root = Path(data_dir).resolve() / "local"
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.artwork = self.root / "artwork"
        self.db = connect(self.root / "library.sqlite3")
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript(TABLES)
        self._folder_art = {}

    # Revisions let the view fetch only what changed since its last look.
    def _bump(self):
        self.db.execute("INSERT INTO meta VALUES ('rev', 1) ON CONFLICT(key) DO UPDATE SET value=value+1")
        return self.db.execute("SELECT value FROM meta WHERE key='rev'").fetchone()[0]

    def revision(self):
        row = self.db.execute("SELECT value FROM meta WHERE key='rev'").fetchone()
        return row[0] if row else 0

    def add_folder(self, path):
        try:
            folder = Path(path).expanduser().resolve(strict=True)
        except (OSError, RuntimeError):
            raise LibraryError("This folder can't be opened. Check that it exists and is connected.") from None
        if not folder.is_dir():
            raise LibraryError("Choose a folder, not a file.")
        key = path_key(folder)
        existing = self.db.execute("SELECT id FROM folders WHERE key=?", (key,)).fetchone()
        if existing:
            return existing[0]
        if inside(self.root, folder):
            raise LibraryError("This folder holds Tubify's own data. Choose a music folder instead.")
        now = time.time()
        with self.db:
            rev = self._bump()
            cursor = self.db.execute("INSERT INTO folders (path, key, device, added, scanned, state, rev) VALUES (?, ?, ?, ?, 0, 'new', ?)",
                                     (str(folder), key, str(folder.stat().st_dev), now, rev))
        return cursor.lastrowid

    def remove_folder(self, folder_id):
        """Stop listing a folder. Its files stay where they are; songs another chosen folder still covers stay listed."""
        row = self.db.execute("SELECT path FROM folders WHERE id=?", (folder_id,)).fetchone()
        if not row:
            return
        others = self.db.execute("SELECT id, path FROM folders WHERE id<>?", (folder_id,)).fetchall()
        with self.db:
            rev = self._bump()
            for song_id, path in self.db.execute("SELECT id, path FROM songs WHERE folder=?", (folder_id,)).fetchall():
                # The deepest remaining folder that covers the song takes it over.
                owner = max((other for other in others if inside(path, other[1])), key=lambda other: len(other[1]), default=None)
                if owner:
                    self.db.execute("UPDATE songs SET folder=?, rev=? WHERE id=?", (owner[0], rev, song_id))
                else:
                    self.db.execute("DELETE FROM songs WHERE id=?", (song_id,))
                    self.db.execute("INSERT OR REPLACE INTO removed VALUES (?, ?)", (song_id, rev))
            if not any(inside(row[0], other[1]) for other in others):
                stale = [key for (key,) in self.db.execute("SELECT key FROM excluded") if inside(key, row[0])]
                self.db.executemany("DELETE FROM excluded WHERE key=?", [(key,) for key in stale])
            self.db.execute("DELETE FROM folders WHERE id=?", (folder_id,))
        self._collect_artwork()

    def remove_songs(self, song_ids):
        """Stop listing songs. The files stay; a rescan doesn't bring them back."""
        with self.db:
            rev = self._bump()
            for song_id in song_ids:
                row = self.db.execute("SELECT key FROM songs WHERE id=?", (song_id,)).fetchone()
                if row:
                    self.db.execute("INSERT OR IGNORE INTO excluded VALUES (?)", (row[0],))
                    self.db.execute("DELETE FROM songs WHERE id=?", (song_id,))
                    self.db.execute("INSERT OR REPLACE INTO removed VALUES (?, ?)", (song_id, rev))
        self._collect_artwork()

    def forget_missing(self, folder_id=None):
        """Drop songs whose files are gone, once the user asks to."""
        query = "SELECT id FROM songs WHERE state='missing'" + (" AND folder=?" if folder_id is not None else "")
        ids = [row[0] for row in self.db.execute(query, (folder_id,) if folder_id is not None else ())]
        with self.db:
            rev = self._bump()
            for song_id in ids:
                self.db.execute("DELETE FROM songs WHERE id=?", (song_id,))
                self.db.execute("INSERT OR REPLACE INTO removed VALUES (?, ?)", (song_id, rev))
        self._collect_artwork()
        return len(ids)

    def song(self, song_id):
        row = self.db.execute("SELECT " + COLUMNS + " FROM songs WHERE id=?", (song_id,)).fetchone()
        return self._song(row) if row else None

    def changes(self, since=0):
        """Folders, plus songs changed and removed since a revision. Revision 0 lists everything."""
        revision = self.revision()
        if since > revision:
            since = 0
        songs = [self._song(row) for row in self.db.execute("SELECT " + COLUMNS + " FROM songs WHERE rev>? ORDER BY rev", (since,))]
        removed = [row[0] for row in self.db.execute("SELECT id FROM removed WHERE rev>?", (since,))] if since else []
        counts = {}
        for folder, state, count in self.db.execute("SELECT folder, state, count(*) FROM songs GROUP BY folder, state"):
            counts.setdefault(folder, {})[state] = count
        folders = [{"id": folder_id, "path": path, "name": Path(path).name or path, "state": state, "scanned": scanned,
                    "songs": sum(counts.get(folder_id, {}).values()), "missing": counts.get(folder_id, {}).get("missing", 0)}
                   for folder_id, path, state, scanned in self.db.execute("SELECT id, path, state, scanned FROM folders ORDER BY added")]
        return {"revision": revision, "full": since == 0, "folders": folders, "songs": songs, "removed": removed}

    def _song(self, row):
        values = dict(zip(FIELDS, row))
        artwork = values.pop("artwork")
        art = (self.artwork / artwork).as_uri() if artwork else ""
        album = values["albumName"]
        return {**values, "kind": "song", "local": True, "localId": values["id"], "thumbnail": art,
                "available": values["state"] == "ready", "tagsReadable": bool(values["tagsReadable"]),
                "albumArtist": values["albumArtist"] or values["artist"], "album": {"id": "", "name": album},
                "albumName": album}

    def scan(self, folder_id=None, progress=None, now=None):
        """Bring the index up to date with the folders on disk, reading only new and changed files."""
        from PySide6.QtCore import QLockFile

        lock = QLockFile(str(self.root / "scan.lock"))
        lock.setStaleLockTime(0)
        if not lock.tryLock(0):
            raise LibraryError("Local music is already being scanned.")
        report = progress or (lambda value: None)
        totals = {"scanned": 0, "added": 0, "updated": 0, "missing": 0, "waiting": 0, "offline": 0}
        try:
            query = "SELECT id, path, device FROM folders" + (" WHERE id=?" if folder_id is not None else "") + " ORDER BY length(path)"
            for folder in self.db.execute(query, (folder_id,) if folder_id is not None else ()).fetchall():
                self._scan_folder(*folder, totals, report, now)
        finally:
            lock.unlock()
        self._collect_artwork()
        return {**totals, **self.changes()}

    def _set_folder(self, folder_id, state, **values):
        with self.db:
            rev = self._bump()
            assignments = "".join(f", {name}=?" for name in values)
            self.db.execute(f"UPDATE folders SET state=?, rev=?{assignments} WHERE id=?", (state, rev, *values.values(), folder_id))

    def _offline(self, folder_id, totals):
        """A folder that is gone keeps its songs, shown as unavailable until it comes back."""
        totals["offline"] += 1
        with self.db:
            rev = self._bump()
            self.db.execute("UPDATE songs SET state='offline', rev=? WHERE folder=? AND state<>'offline'", (rev, folder_id))
            self.db.execute("UPDATE folders SET state='offline', rev=? WHERE id=?", (rev, folder_id))

    def _scan_folder(self, folder_id, path, device, totals, report, now):
        root = Path(path)
        try:
            present = root.is_dir()
            current_device = str(root.stat().st_dev) if present else device
        except OSError:
            present, current_device = False, device
        if not present:
            return self._offline(folder_id, totals)
        known = {row[0]: row[1:] for row in self.db.execute("SELECT key, id, size, mtime, state, folder FROM songs")}
        owned = {row[0] for row in self.db.execute("SELECT key FROM songs WHERE folder=?", (folder_id,))}
        excluded = {row[0] for row in self.db.execute("SELECT key FROM excluded")}
        self._set_folder(folder_id, "scanning")
        report({"folder": folder_id, "phase": "listing", "scanned": 0, "total": 0})
        files, seen_inodes, waiting = [], {}, 0
        moment = time.time() if now is None else now
        for file_path, stat in walk(root):
            key = path_key(file_path)
            if key in excluded:
                continue
            if moment - stat.st_mtime < SETTLE_SECONDS:
                # Still being written, or just finished: the next scan reads it.
                waiting += 1
                if key in owned:
                    owned.discard(key)
                continue
            # A hard link or a second path to the same file is listed once.
            if stat.st_ino:
                identity = (stat.st_dev, stat.st_ino)
                if identity in seen_inodes and seen_inodes[identity] != key:
                    continue
                seen_inodes[identity] = key
            files.append((file_path, key, stat))
        found = {key for _, key, _ in files}
        if not files and owned:
            # An empty mount point looks like a folder whose music was all deleted.
            # Treat it as disconnected; the songs come back when the drive does.
            if current_device != device or not any(root.iterdir()):
                return self._offline(folder_id, totals)
        gone = owned - found
        missing = {}
        if gone:
            with self.db:
                rev = self._bump()
                for key in gone:
                    song_id = known[key][0]
                    self.db.execute("UPDATE songs SET state='missing', rev=? WHERE id=? AND state<>'missing'", (rev, song_id))
            totals["missing"] += len(gone)
        for row in self.db.execute("SELECT " + COLUMNS + " FROM songs WHERE folder=? AND state='missing'", (folder_id,)):
            values = dict(zip(FIELDS, row))
            missing.setdefault(values["size"], []).append(values)
        total, done, batch, last = len(files), 0, [], 0.
        report({"folder": folder_id, "phase": "reading", "scanned": 0, "total": total})
        for file_path, key, stat in files:
            done += 1
            previous = known.get(key)
            if previous and previous[1] == stat.st_size and previous[2] == stat.st_mtime_ns and previous[3] not in {"missing", "offline"}:
                pass
            elif previous and previous[1] == stat.st_size and previous[2] == stat.st_mtime_ns:
                batch.append(("restore", previous[0], None))
            else:
                batch.append(("read", key, (file_path, stat, previous)))
            if len(batch) >= BATCH:
                self._apply(folder_id, batch, missing, totals)
                batch = []
            if time.monotonic() - last >= PROGRESS_SECONDS:
                last = time.monotonic()
                report({"folder": folder_id, "phase": "reading", "scanned": done, "total": total, "revision": self.revision()})
        self._apply(folder_id, batch, missing, totals)
        totals["scanned"] += total
        totals["waiting"] += waiting
        self._set_folder(folder_id, "ready", scanned=time.time(), device=current_device)
        report({"folder": folder_id, "phase": "done", "scanned": total, "total": total, "revision": self.revision()})

    def _apply(self, folder_id, batch, missing, totals):
        """Read a batch of files outside the transaction, then write them together."""
        rows = []
        for action, key, details in batch:
            if action == "restore":
                rows.append(("restore", key, None))
                continue
            file_path, stat, previous = details
            values = tag_reader.read(file_path)
            values["artwork"] = self._store_picture(values.pop("picture")) or self._folder_picture(file_path)
            rows.append(("write", key, (file_path, stat, previous, values)))
        if not rows:
            return
        with self.db:
            rev = self._bump()
            now = time.time()
            for action, key, details in rows:
                if action == "restore":
                    self.db.execute("UPDATE songs SET state='ready', rev=? WHERE id=?", (rev, key))
                    continue
                file_path, stat, previous, values = details
                fields = (folder_id, file_path, key, stat.st_size, stat.st_mtime_ns, str(stat.st_dev), str(stat.st_ino),
                          values["title"], values["artist"], values["album"], values["albumArtist"], values["track"], values["disc"],
                          values["year"], values["duration"], values["codec"], values["sampleRate"], values["artwork"],
                          int(values["tagsReadable"]))
                if previous:
                    self.db.execute("""UPDATE songs SET folder=?, path=?, key=?, size=?, mtime=?, device=?, inode=?, title=?, artist=?,
                        album=?, album_artist=?, track=?, disc=?, year=?, duration=?, codec=?, sample_rate=?, artwork=?,
                        tags_readable=?, state='ready', rev=? WHERE id=?""", (*fields, rev, previous[0]))
                    totals["updated"] += 1
                    continue
                moved = self._match_moved(missing, stat.st_size, values)
                if moved:
                    # Same song at a new path: keep its id, so queues and history still find it.
                    self.db.execute("""UPDATE songs SET folder=?, path=?, key=?, size=?, mtime=?, device=?, inode=?, title=?, artist=?,
                        album=?, album_artist=?, track=?, disc=?, year=?, duration=?, codec=?, sample_rate=?, artwork=?,
                        tags_readable=?, state='ready', rev=? WHERE id=?""", (*fields, rev, moved))
                    totals["updated"] += 1
                    continue
                self.db.execute("INSERT INTO songs VALUES (?, " + ", ".join("?" * len(fields)) + ", 'ready', ?, ?)",
                                ("local:" + uuid.uuid4().hex[:20], *fields, now, rev))
                totals["added"] += 1

    @staticmethod
    def _match_moved(missing, size, values):
        for candidate in missing.get(size, []):
            if (candidate["title"], candidate["artist"], candidate["albumName"]) == (values["title"], values["artist"], values["album"]) \
                    and abs(candidate["duration"] - values["duration"]) < 1:
                missing[size].remove(candidate)
                return candidate["id"]
        return None

    def _store_picture(self, data):
        """Cache a downscaled copy of a picture; pictures shared by an album's songs are stored once."""
        if not data:
            return ""
        name = hashlib.sha256(data).hexdigest()[:40] + ".jpg"
        target = self.artwork / name
        if target.is_file():
            return name
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QImage

        image = QImage.fromData(data)
        if image.isNull():
            return ""
        if max(image.width(), image.height()) > ART_PIXELS:
            image = image.scaled(ART_PIXELS, ART_PIXELS, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.artwork.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = target.with_name(target.name + ".tmp")
        if not image.save(str(temporary), "JPG", 90):
            temporary.unlink(missing_ok=True)
            return ""
        os.replace(temporary, target)
        return name

    def _folder_picture(self, file_path):
        """A same-named picture next to the file, then the folder's cover image."""
        path = Path(file_path)
        for suffix in ART_SUFFIXES:
            for candidate in (path.with_suffix(suffix), path.with_suffix(suffix.upper())):
                stored = self._picture_file(candidate)
                if stored:
                    return stored
        folder = path.parent
        if folder not in self._folder_art:
            choice = ""
            try:
                names = {entry.name.lower(): entry.path for entry in os.scandir(folder) if entry.is_file()}
            except OSError:
                names = {}
            for stem in FOLDER_ART:
                for suffix in ART_SUFFIXES:
                    if stem + suffix in names:
                        choice = self._picture_file(names[stem + suffix])
                        break
                if choice:
                    break
            self._folder_art[folder] = choice
        return self._folder_art[folder]

    def _picture_file(self, path):
        try:
            if not os.path.isfile(path) or os.path.getsize(path) > tag_reader.PICTURE_LIMIT:
                return ""
            with open(path, "rb") as handle:
                return self._store_picture(handle.read())
        except OSError:
            return ""

    def _collect_artwork(self):
        if not self.artwork.is_dir():
            return
        used = {row[0] for row in self.db.execute("SELECT DISTINCT artwork FROM songs")}
        for path in self.artwork.iterdir():
            if path.name not in used and not path.name.endswith(".tmp"):
                path.unlink(missing_ok=True)

    def close(self):
        self.db.close()


FIELDS = ("id", "folder", "path", "size", "title", "artist", "albumName", "albumArtist", "track", "disc", "year", "duration",
          "codec", "sampleRate", "artwork", "tagsReadable", "state", "added")
COLUMNS = ("id, folder, path, size, title, artist, album, album_artist, track, disc, year, duration, codec, sample_rate, "
           "artwork, tags_readable, state, added")
