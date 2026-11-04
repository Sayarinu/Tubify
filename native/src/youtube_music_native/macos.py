"""macOS process environment; Finder launches apps without Homebrew or bundle search paths."""

import os
from pathlib import Path
import ssl
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
    # The bundled OpenSSL looks for certificates at a path from the build machine, so urllib
    # (update checks, Last.fm) cannot verify anything without being pointed at the bundled ones.
    certificates = bundle / "certifi" / "cacert.pem" if bundle else None
    if certificates and certificates.is_file():
        environ.setdefault("SSL_CERT_FILE", str(certificates))


def trusts_certificates(platform=None):
    """Whether HTTPS can verify anything; the packaged smoke test fails without it."""
    return (platform or sys.platform) != "darwin" or bool(ssl.create_default_context().get_ca_certs())
