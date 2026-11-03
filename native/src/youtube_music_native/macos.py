"""macOS process environment; Finder launches apps without Homebrew or bundle search paths."""

import os
from pathlib import Path
import sys

from .util import bundle_root, prepend_paths

HOMEBREW = (Path("/opt/homebrew"), Path("/usr/local"))


def prepare_runtime(environ=None, platform=None, bundle=None):
    """Let python-mpv, yt-dlp and compat checks find libmpv, Deno and FFmpeg; inherited by workers."""
    environ = os.environ if environ is None else environ
    if (platform or sys.platform) != "darwin":
        return
    # PyInstaller app bundles keep binaries in Contents/Frameworks.
    bundle = bundle_root() if bundle is None else bundle
    bundled = [bundle] if bundle else []
    prepend_paths(environ, "DYLD_FALLBACK_LIBRARY_PATH", bundled + [prefix / "lib" for prefix in HOMEBREW])
    prepend_paths(environ, "PATH", [*(entry / "helpers" for entry in bundled), *(prefix / "bin" for prefix in HOMEBREW)])
