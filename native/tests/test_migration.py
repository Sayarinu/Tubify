"""Data from before the Tubify rename moves to the new folders once, and nothing is overwritten."""
import json
from pathlib import Path
import sys

import pytest
from PySide6.QtCore import QCoreApplication

from tubify.system import migration
from tubify.system.migration import OLD_APPLICATION, OLD_ORGANIZATION, locations, move_locations, move_old_data


OLD = Path(OLD_ORGANIZATION) / OLD_APPLICATION
NEW = Path("Tubify") / "tubify"


def layout(platform, home, names):
    """The settings, data and cache folders Qt uses on each platform, rebuilt under a test home."""
    if platform == "linux":
        return [home / ".config" / names, home / ".local/share" / names, home / ".cache" / names]
    if platform == "darwin":
        return [home / "Library/Preferences" / names, home / "Library/Application Support" / names, home / "Library/Caches" / names]
    # Windows keeps settings and data in one LocalAppData folder, with the cache inside it.
    root = home / "AppData/Local" / names
    return [root, root, root / "cache"]


def fill(platform, home):
    config, data, cache = layout(platform, home, OLD)
    for folder in (config, data, cache):
        folder.mkdir(parents=True, exist_ok=True)
    (config / "settings.ini").write_text("[appearance]\ntheme=youtube-music-purple\n")
    (config / "theme.ini").write_text("[theme]\n")
    (data / "media/audio").mkdir(parents=True)
    (data / "media/audio/song.opus").write_bytes(b"audio")
    (data / "playback.json").write_text('{"items":[]}')
    (cache / "metadata.sqlite3").write_bytes(b"cache")


@pytest.mark.parametrize("platform", ["linux", "darwin", "win32"])
def test_old_data_moves_to_the_new_folders_and_is_kept(tmp_path, platform):
    fill(platform, tmp_path)
    pairs = list(zip(layout(platform, tmp_path, OLD), layout(platform, tmp_path, NEW)))
    moved = move_locations(pairs)
    config, data, cache = layout(platform, tmp_path, NEW)
    assert moved == list(dict.fromkeys([config, data, cache] if platform != "win32" else [config]))
    assert (config / "settings.ini").read_text() == "[appearance]\ntheme=youtube-music-purple\n"
    assert (config / "theme.ini").is_file()
    assert (data / "media/audio/song.opus").read_bytes() == b"audio"
    assert (data / "playback.json").read_text() == '{"items":[]}'
    assert (cache / "metadata.sqlite3").read_bytes() == b"cache"
    for old in layout(platform, tmp_path, OLD):
        assert not old.exists()
        # The empty YouTubeMusicNative folder goes too.
        assert not old.parent.exists()


@pytest.mark.parametrize("platform", ["linux", "darwin", "win32"])
def test_moving_twice_changes_nothing(tmp_path, platform):
    fill(platform, tmp_path)
    pairs = list(zip(layout(platform, tmp_path, OLD), layout(platform, tmp_path, NEW)))
    assert move_locations(pairs)
    before = sorted((path.relative_to(tmp_path), path.read_bytes() if path.is_file() else None) for path in tmp_path.rglob("*"))
    assert move_locations(pairs) == []
    assert sorted((path.relative_to(tmp_path), path.read_bytes() if path.is_file() else None) for path in tmp_path.rglob("*")) == before


@pytest.mark.parametrize("platform", ["linux", "darwin", "win32"])
def test_an_existing_new_folder_is_never_overwritten(tmp_path, platform):
    fill(platform, tmp_path)
    config = layout(platform, tmp_path, NEW)[0]
    config.mkdir(parents=True)
    (config / "settings.ini").write_text("[new]\n")
    pairs = list(zip(layout(platform, tmp_path, OLD), layout(platform, tmp_path, NEW)))
    moved = move_locations(pairs)
    assert config not in moved
    assert (config / "settings.ini").read_text() == "[new]\n"
    assert (layout(platform, tmp_path, OLD)[0] / "settings.ini").read_text().startswith("[appearance]")


def test_an_empty_new_folder_does_not_block_the_move(tmp_path):
    fill("linux", tmp_path)
    config = layout("linux", tmp_path, NEW)[0]
    config.mkdir(parents=True)
    move_locations(zip(layout("linux", tmp_path, OLD), layout("linux", tmp_path, NEW)))
    assert (config / "settings.ini").is_file()


def test_nothing_to_move_is_a_no_op(tmp_path):
    assert move_locations(zip(layout("linux", tmp_path, OLD), layout("linux", tmp_path, NEW))) == []
    assert list(tmp_path.iterdir()) == []


def test_a_move_across_drives_copies_before_deleting(tmp_path, monkeypatch):
    fill("linux", tmp_path)
    rename = migration.os.rename

    def cross_device(source, target):
        # Only the staged copy, on the new drive, can be renamed into place.
        if not Path(source).name.endswith(".moving"):
            raise OSError(migration.errno.EXDEV, "Invalid cross-device link")
        rename(source, target)

    monkeypatch.setattr(migration.os, "rename", cross_device)
    move_locations(zip(layout("linux", tmp_path, OLD), layout("linux", tmp_path, NEW)))
    config, data, _ = layout("linux", tmp_path, NEW)
    assert (config / "settings.ini").is_file() and (data / "media/audio/song.opus").read_bytes() == b"audio"
    assert not layout("linux", tmp_path, OLD)[0].exists()
    assert not any(path.name.endswith(".moving") for path in tmp_path.rglob("*"))


def test_a_failed_copy_keeps_the_old_data(tmp_path, monkeypatch):
    fill("linux", tmp_path)
    monkeypatch.setattr(migration.os, "rename", lambda source, target: (_ for _ in ()).throw(OSError(migration.errno.EXDEV, "cross-device")))
    monkeypatch.setattr(migration.shutil, "copytree", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        move_locations(zip(layout("linux", tmp_path, OLD), layout("linux", tmp_path, NEW)))
    assert (layout("linux", tmp_path, OLD)[0] / "settings.ini").is_file()
    assert not layout("linux", tmp_path, NEW)[0].exists()


def test_downloaded_artwork_links_follow_the_moved_folder(tmp_path):
    from tubify.downloads.downloads import DownloadStore

    old_data, new_data = layout("linux", tmp_path, OLD)[1], layout("linux", tmp_path, NEW)[1]
    store = DownloadStore(old_data)
    art = store.root / "artwork" / "cover.image"
    art.parent.mkdir(parents=True)
    art.write_bytes(b"image")
    body = {"items": [{"videoId": "abcdefghijk", "localThumbnail": art.as_uri()}], "localThumbnail": art.as_uri()}
    with store.db:
        store.db.execute("INSERT INTO collections VALUES (?, ?)", ("playlist:PL1", json.dumps(body)))
    store.db.close()
    (old_data / "playback.json").write_text(json.dumps({"items": [{"thumbnail": art.as_uri()}]}, separators=(",", ":")))

    move_locations([(old_data, new_data)])

    moved = DownloadStore(new_data)
    link = json.loads(moved.db.execute("SELECT body FROM collections").fetchone()[0])["localThumbnail"]
    assert moved._artwork_uri(link) == (moved.root / "artwork/cover.image").as_uri()
    assert moved.root.as_uri() + "/artwork/cover.image" in (new_data / "playback.json").read_text()
    # Cleaning up unused artwork must not mistake the moved cover for an orphan.
    moved._collect_garbage()
    assert (moved.root / "artwork/cover.image").read_bytes() == b"image"
    moved.db.close()


def test_a_damaged_database_does_not_stop_the_move(tmp_path):
    fill("linux", tmp_path)
    (layout("linux", tmp_path, OLD)[1] / "media/media.sqlite3").write_bytes(b"not a database")
    move_locations(zip(layout("linux", tmp_path, OLD), layout("linux", tmp_path, NEW)))
    assert (layout("linux", tmp_path, NEW)[1] / "media/audio/song.opus").is_file()


@pytest.fixture
def xdg(tmp_path, monkeypatch):
    for name, folder in (("XDG_CONFIG_HOME", ".config"), ("XDG_DATA_HOME", ".local/share"), ("XDG_CACHE_HOME", ".cache")):
        monkeypatch.setenv(name, str(tmp_path / folder))
    names = QCoreApplication.organizationName(), QCoreApplication.applicationName()
    QCoreApplication.setOrganizationName("Tubify")
    QCoreApplication.setApplicationName("tubify")
    yield tmp_path
    QCoreApplication.setOrganizationName(names[0])
    QCoreApplication.setApplicationName(names[1])


@pytest.mark.skipif(sys.platform != "linux", reason="Qt reads the XDG folders on Linux")
def test_qt_reports_the_old_and_new_folders_without_changing_the_app_names(xdg):
    assert [Path(path) for path in locations(OLD_ORGANIZATION, OLD_APPLICATION)] == layout("linux", xdg, OLD)
    assert [Path(path) for path in locations("Tubify", "tubify")] == layout("linux", xdg, NEW)
    assert (QCoreApplication.organizationName(), QCoreApplication.applicationName()) == ("Tubify", "tubify")


@pytest.mark.skipif(sys.platform != "linux", reason="Qt reads the XDG folders on Linux")
def test_startup_moves_old_data_once_and_reports_without_paths(xdg):
    fill("linux", xdg)
    messages = []
    assert move_old_data(messages.append) == layout("linux", xdg, NEW)
    assert (layout("linux", xdg, NEW)[0] / "settings.ini").is_file()
    assert len(messages) == 1 and str(xdg) not in messages[0]
    assert move_old_data(messages.append) == [] and len(messages) == 1


def test_startup_survives_a_failed_move(monkeypatch):
    messages = []
    monkeypatch.setattr(migration, "move_locations", lambda pairs: (_ for _ in ()).throw(PermissionError("/private/path")))
    assert move_old_data(messages.append) == []
    assert messages and "/private/path" not in messages[0]
