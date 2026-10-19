"""Verified local audio index shared by source selection and durable downloads."""

from pathlib import Path
import os

from .database import connect


class MediaFiles:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = connect(self.root / "media.sqlite3")
        self.db.execute("""CREATE TABLE IF NOT EXISTS audio (
            video_id TEXT PRIMARY KEY, path TEXT NOT NULL, bytes INTEGER NOT NULL,
            state TEXT NOT NULL DEFAULT 'ready')""")

    def ready(self, video_id):
        row = self.db.execute("SELECT path, bytes FROM audio WHERE video_id=? AND state='ready'", (video_id,)).fetchone()
        if not row:
            return None
        path = (self.root / row[0]).resolve()
        try:
            valid = path.is_relative_to(self.root) and path.is_file() and path.stat().st_size == row[1] and row[1] > 0
        except OSError:
            valid = False
        if not valid:
            self.mark_damaged(video_id)
            return None
        return path

    def publish(self, video_id, path, final_path=None):
        from .compat import validate_media

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
            self.db.execute("INSERT OR REPLACE INTO audio VALUES (?, ?, ?, 'ready')", (video_id, str(path.relative_to(self.root)), path.stat().st_size))

    def mark_damaged(self, video_id):
        with self.db:
            self.db.execute("UPDATE audio SET state='damaged' WHERE video_id=?", (video_id,))

    def close(self):
        self.db.close()
