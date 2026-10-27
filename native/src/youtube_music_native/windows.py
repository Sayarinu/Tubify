"""Locate bundled Windows helper programs and libmpv before the app or workers import them."""

import os
from pathlib import Path
import sys


_DLL_DIRECTORIES = []
_DLL_PATHS = set()


def bundle_root():
    # PyInstaller one-folder builds keep bundled binaries in the contents directory (sys._MEIPASS), not beside Tubify.exe.
    root = getattr(sys, "_MEIPASS", None)
    return Path(root) if root else None


def _prepend(environ, key, entries, separator):
    current = [entry for entry in environ.get(key, "").split(separator) if entry]
    additions = [str(entry) for entry in entries if str(entry) not in current]
    if additions:
        environ[key] = separator.join(additions + current)


def prepare_runtime(environ=None, platform=None, bundle=None, add_dll_directory=None):
    """Make bundled mpv DLLs and yt-dlp helpers available to the GUI and child workers."""
    if (platform or sys.platform) != "win32":
        return
    environ = os.environ if environ is None else environ
    bundle = bundle_root() if bundle is None else Path(bundle)
    if bundle is None:
        return
    separator = ";" if (platform or sys.platform) == "win32" else os.pathsep
    mpv = bundle / "mpv"
    helpers = bundle / "helpers"
    _prepend(environ, "PATH", [helpers, mpv], separator)
    if add_dll_directory is None:
        add_dll_directory = getattr(os, "add_dll_directory", None)
    if add_dll_directory:
        for directory in (mpv, helpers):
            value = str(directory)
            if directory.is_dir() and value not in _DLL_PATHS:
                _DLL_DIRECTORIES.append(add_dll_directory(value))
                _DLL_PATHS.add(value)
