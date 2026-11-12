import os
import stat
import sys

import pytest

from tubify.catalog.store import MetadataStore, wipe_metadata
from tubify.compat import private_directory


def test_wiping_removes_views_and_their_bytes_from_disk(tmp_path):
    path = tmp_path / "metadata.sqlite3"
    store = MetadataStore(path)
    # Random-looking content doesn't compress away, so its marker would survive in free pages.
    store.write("key", {"title": "synthetic-private-library-" + os.urandom(4000).hex()})
    store.close()
    wipe_metadata(path)
    store = MetadataStore(path)
    assert store.read("key") is None
    store.close()
    assert b"synthetic-private-library" not in path.read_bytes()
    assert len(path.read_bytes()) < 16384


def test_wiping_an_unusable_cache_is_harmless(tmp_path):
    wipe_metadata(tmp_path)


@pytest.mark.skipif(sys.platform == "win32", reason="Windows data directories are already per-user")
def test_an_existing_open_directory_is_tightened(tmp_path):
    path = tmp_path / "data"
    path.mkdir(mode=0o755)
    path.chmod(0o755)
    assert private_directory(path) == path
    assert stat.S_IMODE(path.stat().st_mode) == 0o700
    created = private_directory(tmp_path / "a" / "new")
    assert stat.S_IMODE(created.stat().st_mode) == 0o700
