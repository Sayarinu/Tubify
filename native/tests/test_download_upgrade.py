import sqlite3

from tubify.downloads.downloads import DownloadStore


def test_an_older_library_gains_the_new_columns_and_keeps_its_downloads(tmp_path):
    media = tmp_path / "media"
    media.mkdir()
    old = sqlite3.connect(media / "media.sqlite3")
    old.executescript("""
        CREATE TABLE audio (video_id TEXT PRIMARY KEY, path TEXT NOT NULL, bytes INTEGER NOT NULL, state TEXT NOT NULL DEFAULT 'ready');
        INSERT INTO audio VALUES ('abcdefghijk', 'audio/abcdefghijk.opus', 8, 'ready');
        CREATE TABLE collections (id TEXT PRIMARY KEY, body TEXT NOT NULL);
        INSERT INTO collections VALUES ('song:abcdefghijk', '{"kind": "song", "id": "abcdefghijk", "title": "Song", "items": []}');
        CREATE TABLE exports (collection_id TEXT PRIMARY KEY REFERENCES collections(id) ON DELETE CASCADE,
            folder TEXT NOT NULL, state TEXT NOT NULL, saved INTEGER NOT NULL, error TEXT NOT NULL);
        INSERT INTO exports VALUES ('song:abcdefghijk', '/music', 'saved', 1, '');
    """)
    old.commit()
    old.close()
    store = DownloadStore(tmp_path)
    assert store.db.execute("SELECT path, external FROM audio").fetchall() == [("audio/abcdefghijk.opus", 0)]
    assert store.export("song:abcdefghijk") == {"folder": "/music", "state": "saved", "saved": 1, "error": "", "move": 0}
    store.close()
    # Opening it again changes nothing.
    DownloadStore(tmp_path).close()
