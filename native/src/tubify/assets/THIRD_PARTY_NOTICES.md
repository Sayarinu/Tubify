# Third-party notices

Tubify's own source code is released under the [MIT License](https://github.com/Sayarinu/Tubify/blob/main/LICENSE).

Tubify releases also contain or depend on the third-party software listed below. Each component remains under its own license. This list does not change those licenses. The full license text of each component is available at its source link and inside the component's own distribution.

## Bundled with the Windows and macOS apps

The Windows installer and the macOS app include the components below so that nothing else needs to be installed.

| Component | Used for | License | Source |
|---|---|---|---|
| Python | Application runtime | PSF-2.0 | https://www.python.org/downloads/source/ |
| Qt 6 and PySide6 / Shiboken6 | User interface | LGPL-3.0-only | https://code.qt.io/cgit/pyside/pyside-setup.git/ |
| mpv (libmpv) | Audio and video playback | GPL-2.0-or-later (as built by MSYS2 and Homebrew) | https://github.com/mpv-player/mpv |
| FFmpeg | Decoding, format checks and download conversion | GPL-2.0-or-later or GPL-3.0-or-later, depending on the libraries the MSYS2 and Homebrew builds enable | https://ffmpeg.org/download.html#get-sources |
| Deno | JavaScript runtime used by yt-dlp for YouTube's player challenges | MIT | https://github.com/denoland/deno |
| PyInstaller bootloader | Starts the bundled app | GPL-2.0-or-later with the PyInstaller bootloader exception | https://github.com/pyinstaller/pyinstaller |
| Sparkle (macOS only) | Signed in-app updates | MIT | https://github.com/sparkle-project/Sparkle |
| PyObjC (macOS only) | Now Playing and Sparkle integration | MIT | https://github.com/ronaldoussoren/pyobjc |
| PyWinRT (Windows only) | Media keys and the Windows media overlay | MIT | https://github.com/pywinrt/pywinrt |
| pywin32-ctypes (Windows only) | Credential storage | BSD-3-Clause | https://github.com/enthought/pywin32-ctypes |

The Linux package doesn't bundle these. pacman installs Qt, mpv, FFmpeg, Deno and the Python libraries as system packages under their own licenses.

## Python libraries

| Component | Used for | License | Source |
|---|---|---|---|
| ytmusicapi | YouTube Music catalog and library | MIT | https://github.com/sigma67/ytmusicapi |
| yt-dlp | Resolving playable streams and downloads | Unlicense | https://github.com/yt-dlp/yt-dlp |
| yt-dlp-ejs | yt-dlp player challenge scripts | Unlicense AND MIT AND ISC | https://github.com/yt-dlp/ejs |
| python-mpv | Python bindings for libmpv | GPL-2.0-or-later OR LGPL-2.1-or-later | https://github.com/jaseg/python-mpv |
| keyring, jaraco.classes, jaraco.context, jaraco.functools | Storing the session in the system keychain | MIT | https://github.com/jaraco/keyring |
| jeepney (Linux only) | MPRIS media controls and sleep handling | MIT | https://gitlab.com/takluyver/jeepney |
| SecretStorage (Linux only) | Keyring backend | BSD-3-Clause | https://github.com/mitya57/secretstorage |
| cryptography, cffi, pycparser | Keyring and cookie decryption support | Apache-2.0 OR BSD-3-Clause; MIT-0; BSD-3-Clause | https://github.com/pyca/cryptography |
| mutagen | Audio metadata (yt-dlp dependency) | GPL-2.0-or-later | https://github.com/quodlibet/mutagen |
| pycryptodomex | Verifies signed Linux updates (direct dependency); also used by yt-dlp | BSD-2-Clause and Public Domain | https://github.com/Legrandin/pycryptodome |
| requests, urllib3, idna, charset-normalizer | HTTP | Apache-2.0; MIT; BSD-3-Clause; MIT | https://github.com/psf/requests |
| certifi | Trusted certificate authorities | MPL-2.0 | https://github.com/certifi/python-certifi |
| websockets | Network transport used by yt-dlp | BSD-3-Clause | https://github.com/python-websockets/websockets |
| Brotli | Compressed HTTP responses | MIT | https://github.com/google/brotli |
| more-itertools | Utility functions | MIT | https://github.com/more-itertools/more-itertools |
| QR Code generator library (Project Nayuki), included as `qrcodegen.py` with its MIT notice | QR codes for Continue on Phone | MIT | https://github.com/nayuki/QR-Code-generator |

## Fonts and icons

| Component | License | Source |
|---|---|---|
| Roboto and Roboto Condensed | SIL Open Font License 1.1 (full text in `Roboto-OFL.txt`) | https://github.com/googlefonts/roboto-3-classic |
| Lucide icons | ISC, with the included Feather MIT notice (full text in `lucide-LICENSE`) | https://github.com/lucide-icons/lucide |

## Source code for GPL and LGPL components

You can get the complete corresponding source code for the GPL and LGPL components above, at the versions included in a given Tubify release, from the source links listed. For the exact builds, use the MSYS2 (`mingw-w64-ucrt-x86_64-mpv`, `mingw-w64-ucrt-x86_64-ffmpeg`) and Homebrew (`mpv`, `ffmpeg`) package sources. You can replace the bundled Qt, mpv and FFmpeg libraries with your own builds of compatible versions.

## Trademarks

YouTube and YouTube Music are trademarks of Google LLC. Tubify is an independent project and is not affiliated with, endorsed by or sponsored by Google or YouTube.
