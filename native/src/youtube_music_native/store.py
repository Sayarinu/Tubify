"""Disposable, bounded metadata cache. Durable audio belongs in a separate store."""

import json
from pathlib import Path
import sqlite3
import time
import zlib


class MetadataStore:
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA journal_mode=WAL")
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

    def invalidate(self):
        with self.db:
            self.db.execute("DELETE FROM views")

    def close(self):
        self.db.close()
