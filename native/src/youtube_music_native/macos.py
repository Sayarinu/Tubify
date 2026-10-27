"""macOS process environment; Finder launches apps without Homebrew or bundle search paths."""

import os
from pathlib import Path
import sys

HOMEBREW = (Path("/opt/homebrew"), Path("/usr/local"))


def bundle_root():
    # PyInstaller app bundles keep binaries in Contents/Frameworks (sys._MEIPASS).
    root = getattr(sys, "_MEIPASS", None)
    return Path(root) if root else None


def _prepend(environ, key, entries):
    current = [entry for entry in environ.get(key, "").split(os.pathsep) if entry]
    additions = [str(entry) for entry in entries if str(entry) not in current]
    if additions:
        environ[key] = os.pathsep.join(additions + current)


def prepare_runtime(environ=None, platform=None, bundle=None):
    """Let python-mpv, yt-dlp and compat checks find libmpv, Deno and FFmpeg; inherited by workers."""
    environ = os.environ if environ is None else environ
    if (platform or sys.platform) != "darwin":
        return
    bundle = bundle_root() if bundle is None else bundle
    bundled = [bundle] if bundle else []
    _prepend(environ, "DYLD_FALLBACK_LIBRARY_PATH", bundled + [prefix / "lib" for prefix in HOMEBREW])
    _prepend(environ, "PATH", [*(entry / "helpers" for entry in bundled), *(prefix / "bin" for prefix in HOMEBREW)])
