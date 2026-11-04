"""Open shared worker databases without racing the first WAL transition."""

import sqlite3
import time


def connect(path):
    connection = sqlite3.connect(path)
    deadline = time.monotonic() + 5
    try:
        while True:
            try:
                connection.execute("PRAGMA journal_mode=WAL").fetchone()
                return connection
            except sqlite3.OperationalError as error:
                # SQLite can reject a simultaneous journal-mode change without waiting.
                if (error.sqlite_errorcode & 0xff) not in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED} or time.monotonic() >= deadline:
                    raise
                time.sleep(.01)
    except BaseException:
        connection.close()
        raise
