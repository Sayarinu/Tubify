"""Locate bundled Windows helper programs and libmpv before the app or workers import them."""

import os
from pathlib import Path
import sys

from ..util import bundle_root, prepend_paths


_DLL_DIRECTORIES = []
_DLL_PATHS = set()
# libcrypto first, so libssl binds to the copy beside it.
OPENSSL = ("libcrypto-3-x64.dll", "libssl-3-x64.dll")
_PRELOADED = []


def prepare_runtime(environ=None, platform=None, bundle=None, add_dll_directory=None, load_library=None):
    """Make the bundled libmpv and yt-dlp helpers available to the GUI and child workers."""
    if (platform or sys.platform) != "win32":
        return
    environ = os.environ if environ is None else environ
    # PyInstaller one-folder builds keep bundled binaries in the contents directory, not beside Tubify.exe.
    bundle = bundle_root() if bundle is None else Path(bundle)
    if bundle is None:
        return
    helpers = bundle / "helpers"
    # Windows separates PATH entries with ";"; spelled out so tests on other systems match.
    prepend_paths(environ, "PATH", [helpers], ";")
    if add_dll_directory is None:
        add_dll_directory = getattr(os, "add_dll_directory", None)
    value = str(helpers)
    if add_dll_directory and helpers.is_dir() and value not in _DLL_PATHS:
        _DLL_DIRECTORIES.append(add_dll_directory(value))
        _DLL_PATHS.add(value)
    _preload_openssl(helpers, load_library)


def _preload_openssl(helpers, load_library=None):
    """Load the bundled OpenSSL by full path before Qt or libmpv asks for it by name.

    Windows searches System32 and the folders of other programs ahead of PATH, so an older
    libcrypto-3-x64.dll there could pair with the bundled libssl and stop Tubify starting.
    A DLL already loaded under the same name wins every later by-name load.
    """
    if _PRELOADED or not all((helpers / name).is_file() for name in OPENSSL):
        return
    if load_library is None:
        import ctypes

        load_library = ctypes.WinDLL
    for name in OPENSSL:
        path = helpers / name
        try:
            _PRELOADED.append(load_library(str(path)))
        except OSError:
            # Qt falls back to the system TLS backend; libmpv reports its own failure.
            return
