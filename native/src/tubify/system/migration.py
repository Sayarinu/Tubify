"""Move app data from the names used before 1.0 to Tubify's, once, before anything opens it.

Before 1.0 Qt kept settings, downloads and caches under the organization
YouTubeMusicNative and the application youtube-music-native. Each folder Qt gives
the app (settings, data and cache) moves to the folder it has under the Tubify
names, unless that folder already holds something. Login stays in the system
keyring, whose entry never used the old names.
"""

import errno
import os
from contextlib import closing
from pathlib import Path
import shutil
import sqlite3
import sys

from PySide6.QtCore import QCoreApplication, QStandardPaths

from ..util import atomic_write


OLD_ORGANIZATION = "YouTubeMusicNative"
OLD_APPLICATION = "youtube-music-native"
LOCATIONS = (
    QStandardPaths.StandardLocation.AppConfigLocation,
    QStandardPaths.StandardLocation.AppLocalDataLocation,
    QStandardPaths.StandardLocation.CacheLocation,
)
# Files that hold absolute file:// links into the data folder, such as downloaded artwork.
LINKED_FILES = ("playback.json",)
LINKED_DATABASES = ("media/media.sqlite3",)


def locations(organization, application):
    """The settings, data and cache folders Qt uses on this platform under the given names."""
    current = QCoreApplication.organizationName(), QCoreApplication.applicationName()
    QCoreApplication.setOrganizationName(organization)
    QCoreApplication.setApplicationName(application)
    try:
        return [QStandardPaths.writableLocation(location) for location in LOCATIONS]
    finally:
        QCoreApplication.setOrganizationName(current[0])
        QCoreApplication.setApplicationName(current[1])


def move_old_data(report=None):
    """Move data left under the old names to the current ones. Never raises; returns the folders moved."""
    report = report or (lambda message: print(message, file=sys.stderr))
    try:
        old = locations(OLD_ORGANIZATION, OLD_APPLICATION)
        new = locations(QCoreApplication.organizationName(), QCoreApplication.applicationName())
        moved = move_locations(zip(old, new))
    except Exception:
        report("Tubify could not move its data from the previous app name. It is still in the old folders.")
        return []
    if moved:
        report("Tubify moved its data from the previous app name.")
    return moved


def move_locations(pairs):
    """Move each old folder that exists to its new place if nothing is there yet. Returns the new folders."""
    moved = []
    for old, new in dict.fromkeys((Path(old), Path(new)) for old, new in pairs if old and new):
        # On Windows the cache sits inside the data folder, so it has already gone with it.
        if old == new or old.is_relative_to(new) or new.is_relative_to(old) or not old.is_dir():
            continue
        if not _free(new):
            continue
        resolved = old.resolve()
        _move(old, new)
        try:
            # A symlinked folder moves as a link, so what it points at, and every link into it, stays the same.
            if new.resolve() != resolved:
                _relink(new, resolved, new.resolve())
        except (OSError, sqlite3.Error, UnicodeError):
            # The data is in place; a missed link only costs a downloaded cover until it is fetched again.
            pass
        if old.parent.name == OLD_ORGANIZATION:
            try:
                old.parent.rmdir()
            except OSError:
                pass
        moved.append(new)
    return moved


def _free(path):
    """True when path does not exist, removing it first if it is an empty folder."""
    if not os.path.lexists(path):
        return True
    if path.is_dir() and not path.is_symlink() and not any(path.iterdir()):
        path.rmdir()
        return True
    return False


def _move(old, new):
    new.parent.mkdir(parents=True, exist_ok=True)
    try:
        # rename, not replace: an existing folder must never be overwritten.
        os.rename(old, new)
        return
    except OSError as error:
        if error.errno != errno.EXDEV:
            raise
    # A different drive: copy everything first, and only delete the old folder once the copy is complete.
    staging = new.with_name(new.name + ".moving")
    shutil.rmtree(staging, ignore_errors=True)
    try:
        shutil.copytree(old, staging, symlinks=True)
        os.rename(staging, new)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    shutil.rmtree(old, ignore_errors=True)


def _relink(root, old, new):
    """Point absolute links saved inside the moved folder at its new place."""
    replacements = ((old.as_uri() + "/", new.as_uri() + "/"), (str(old) + os.sep, str(new) + os.sep))
    for name in LINKED_FILES:
        path = root / name
        if path.is_file():
            text = original = path.read_text(encoding="utf-8")
            for before, after in replacements:
                text = text.replace(before, after)
            if text != original:
                atomic_write(path, text)
    for name in LINKED_DATABASES:
        path = root / name
        if not path.is_file():
            continue
        with closing(sqlite3.connect(path, timeout=5)) as db, db:
            tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            for table in tables:
                quoted = '"' + table.replace('"', '""') + '"'
                for column in [row[1] for row in db.execute(f"PRAGMA table_info({quoted})") if row[2].upper() == "TEXT"]:
                    column = '"' + column.replace('"', '""') + '"'
                    for before, after in replacements:
                        db.execute(f"UPDATE OR IGNORE {quoted} SET {column}=replace({column}, ?, ?) WHERE instr({column}, ?) > 0", (before, after, before))
