from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from youtube_music_native.media import MediaFiles
from youtube_music_native.store import MetadataStore


@pytest.mark.parametrize("store_type,name", [(MediaFiles, "media"), (MetadataStore, "metadata.sqlite3")])
def test_workers_can_initialize_a_fresh_shared_database_together(tmp_path, store_type, name):
    with ThreadPoolExecutor(max_workers=3) as pool:
        for run in range(20):
            barrier = Barrier(3)
            path = tmp_path / str(run) / name

            def open_store():
                barrier.wait(timeout=5)
                store = store_type(path)
                try:
                    assert store.db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
                finally:
                    store.close()

            futures = [pool.submit(open_store) for _ in range(3)]
            for future in futures:
                future.result(timeout=10)
