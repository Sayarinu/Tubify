"""Small helpers shared by several modules."""

import os
from pathlib import Path
import sys
import tempfile


def atomic_write(path, content):
    """Replace path with content (text or bytes) so readers never see a partial file.

    The temporary file is removed when writing or replacing fails.
    """
    path = Path(path)
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


def session_rejected(error):
    """Whether YouTube Music refused the saved session (HTTP 401 or 403)."""
    # ytmusicapi is only loaded once a catalog request ran; importing it here would slow every worker start.
    exceptions = sys.modules.get("ytmusicapi.exceptions")
    if exceptions is None or not isinstance(error, exceptions.YTMusicServerError):
        return False
    # The library reports the status code only in its message.
    return str(error).startswith(("Server returned HTTP 401", "Server returned HTTP 403"))
