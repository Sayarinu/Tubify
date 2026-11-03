"""Locate bundled Windows helper programs and libmpv before the app or workers import them."""

import os
from pathlib import Path
import sys

from .util import bundle_root, prepend_paths


_DLL_DIRECTORIES = []
_DLL_PATHS = set()


def prepare_runtime(environ=None, platform=None, bundle=None, add_dll_directory=None):
    """Make bundled mpv DLLs and yt-dlp helpers available to the GUI and child workers."""
    if (platform or sys.platform) != "win32":
        return
    environ = os.environ if environ is None else environ
    # PyInstaller one-folder builds keep bundled binaries in the contents directory, not beside Tubify.exe.
    bundle = bundle_root() if bundle is None else Path(bundle)
    if bundle is None:
        return
    mpv = bundle / "mpv"
    helpers = bundle / "helpers"
    # Windows separates PATH entries with ";"; spelled out so tests on other systems match.
    prepend_paths(environ, "PATH", [helpers, mpv], ";")
    if add_dll_directory is None:
        add_dll_directory = getattr(os, "add_dll_directory", None)
    if add_dll_directory:
        for directory in (mpv, helpers):
            value = str(directory)
            if directory.is_dir() and value not in _DLL_PATHS:
                _DLL_DIRECTORIES.append(add_dll_directory(value))
                _DLL_PATHS.add(value)
