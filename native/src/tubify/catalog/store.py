"""Disposable, bounded metadata cache. Durable audio belongs in a separate store."""

import json
from pathlib import Path
import sqlite3
import time
import zlib

from .database import connect


def wipe_metadata(path):
    """Best effort after sign-out; a cache that can't be opened holds nothing the app will read."""
    store = None
    try:
        store = MetadataStore(path)
        store.wipe()
    except (OSError, sqlite3.Error):
        pass
    finally:
        if store:
            store.close()


class MetadataStore:
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = connect(path)
        self.db.execute("""CREATE TABLE IF NOT EXISTS views (
            key TEXT PRIMARY KEY, saved REAL NOT NULL, body BLOB NOT NULL)""")

    def read(self, key):
        row = self.db.execute("SELECT saved, body FROM views WHERE key=?", (key,)).fetchone()
        if not row:
            return None
        try:
            return {"saved": row[0], "data": json.loads(zlib.decompress(row[1]))}
        except (ValueError, TypeError, zlib.error):
            self.db.execute("DELETE FROM views WHERE key=?", (key,))
            self.db.commit()
            return None

    def write(self, key, data):
        body = zlib.compress(json.dumps(data, separators=(",", ":")).encode())
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO views VALUES (?, ?, ?)", (key, time.time(), body))
            self.db.execute("DELETE FROM views WHERE key IN (SELECT key FROM views ORDER BY saved DESC LIMIT -1 OFFSET 200)")

    def invalidate(self, keep_routes=()):
        """Drop cached views, optionally keeping routes an account change cannot affect."""
        with self.db:
            if not keep_routes:
                self.db.execute("DELETE FROM views")
                return
            stale = []
            for key, in self.db.execute("SELECT key FROM views"):
                try:
                    route = json.loads(key)[1]
                except (ValueError, TypeError, IndexError, KeyError):
                    route = None
                if route not in keep_routes:
                    stale.append((key,))
            self.db.executemany("DELETE FROM views WHERE key=?", stale)

    def wipe(self):
        """Remove every cached view from disk, including the free pages SQLite would otherwise keep."""
        with self.db:
            self.db.execute("DELETE FROM views")
        self.db.execute("VACUUM")

    def close(self):
        self.db.close()
