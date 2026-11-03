"""Small helpers shared by several modules."""

import math
import os
from pathlib import Path
import sys
import tempfile


def atomic_write(path, content):
    """Replace path with content (text or bytes) so readers never see a partial file.

    A missing parent folder is created private to the user. The temporary file is
    removed when writing or replacing fails.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    data = content.encode("utf-8") if isinstance(content, str) else bytes(content)
    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def bundle_root():
    """Folder holding a PyInstaller build's bundled binaries (sys._MEIPASS), or None from source."""
    root = getattr(sys, "_MEIPASS", None)
    return Path(root) if root else None


def prepend_paths(environ, key, entries, separator=os.pathsep):
    """Put entries at the front of a path-list variable, skipping ones it already has."""
    current = [entry for entry in environ.get(key, "").split(separator) if entry]
    additions = [str(entry) for entry in entries if str(entry) not in current]
    if additions:
        environ[key] = separator.join(additions + current)


def parse_duration(value):
    """Seconds from a number or a "3:41" / "1:02:03" label; 0 when missing or invalid."""
    try:
        if isinstance(value, str) and ":" in value:
            seconds = 0.
            for part in value.split(":"):
                seconds = seconds * 60 + float(part)
        else:
            seconds = float(value or 0)
    except (ValueError, TypeError):
        return 0.
    return seconds if math.isfinite(seconds) and seconds > 0 else 0.


def needs_reconnect(error):
    """Whether a worker failure means the YouTube Music account must be connected again."""
    return error.get("code") in {"reconnect", "AuthError"}


def session_rejected(error):
    """Whether YouTube Music refused the saved session (HTTP 401 or 403)."""
    # ytmusicapi is only loaded once a catalog request ran; importing it here would slow every worker start.
    exceptions = sys.modules.get("ytmusicapi.exceptions")
    if exceptions is None or not isinstance(error, exceptions.YTMusicServerError):
        return False
    # The library reports the status code only in its message.
    return str(error).startswith(("Server returned HTTP 401", "Server returned HTTP 403"))
