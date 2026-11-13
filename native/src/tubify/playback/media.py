"""Verified local audio index shared by source selection and durable downloads.

A song is either a private copy inside the media folder, or, when downloads are kept as audio
files, an external file the person owns. Tubify never deletes an external file.
"""

from pathlib import Path
import os

from ..catalog.database import connect


class MediaFiles:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = connect(self.root / "media.sqlite3")
        self.db.execute("""CREATE TABLE IF NOT EXISTS audio (
            video_id TEXT PRIMARY KEY, path TEXT NOT NULL, bytes INTEGER NOT NULL,
            state TEXT NOT NULL DEFAULT 'ready', external INTEGER NOT NULL DEFAULT 0)""")
        # Older libraries gain the column once; workers opening it together take turns.
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            if "external" not in {row[1] for row in self.db.execute("PRAGMA table_info(audio)")}:
                self.db.execute("ALTER TABLE audio ADD COLUMN external INTEGER NOT NULL DEFAULT 0")

    def ready(self, video_id):
        row = self.db.execute("SELECT path, bytes, external FROM audio WHERE video_id=? AND state='ready'", (video_id,)).fetchone()
        if not row:
            return None
        try:
            if row[2]:
                # Other apps may retag the person's file, so only its presence is required.
                path = Path(row[0])
                valid = path.is_absolute() and path.is_file() and path.stat().st_size > 0
            else:
                path = (self.root / row[0]).resolve()
                valid = path.is_relative_to(self.root) and path.is_file() and path.stat().st_size == row[1] and row[1] > 0
        except OSError:
            valid = False
        if not valid:
            # The person's file may be on a drive that is only disconnected for now; it plays again once back.
            if not row[2]:
                self.mark_damaged(video_id)
            return None
        return path

    def publish(self, video_id, path, final_path=None):
        from ..compat import validate_media

        path = Path(path).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Completed audio must be inside the media directory")
        validate_media(path)
        if final_path is not None:
            final_path = Path(final_path).resolve()
            if not final_path.is_relative_to(self.root):
                raise ValueError("Completed audio must be inside the media directory")
            os.replace(path, final_path)
            path = final_path
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO audio (video_id, path, bytes, state, external) VALUES (?, ?, ?, 'ready', 0)",
                            (video_id, str(path.relative_to(self.root)), path.stat().st_size))

    def external(self, video_id):
        """The person's audio file this song plays from, or None for a private copy."""
        row = self.db.execute("SELECT path FROM audio WHERE video_id=? AND external=1", (video_id,)).fetchone()
        return Path(row[0]) if row else None

    def mark_damaged(self, video_id):
        with self.db:
            self.db.execute("UPDATE audio SET state='damaged' WHERE video_id=?", (video_id,))

    def close(self):
        self.db.close()
