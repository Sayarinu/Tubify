# Building Tubify from source

Most people should [download a release](https://github.com/Sayarinu/Tubify/releases/latest) instead. This page is for contributors and packagers.

Tubify is a Python and Qt Quick (PySide6 + QML) app. One codebase in [`native/`](../native) serves Linux, macOS and Windows.

## Run from a checkout

```sh
cd native
python -m pip install -e '.[test]'
tubify              # your account
tubify --fixture    # synthetic data, no account needed
python -m pytest tests -q
```

Playback needs FFmpeg and Deno on `PATH`, and libmpv where the system library loader can find it: installed system-wide or on `LD_LIBRARY_PATH` (Linux) or `DYLD_LIBRARY_PATH` (macOS). On Windows, libmpv's DLL directory must be on `PATH`.

## Packages

Build each package on its own operating system:

| Platform | Command | Output |
|---|---|---|
| Linux x86_64 (pacman) | `./scripts/build-native-arch-package.sh` | `dist/native/youtube-music-native-*.pkg.tar.zst` (published as `Tubify-<version>-linux-x86_64.pkg.tar.zst`) |
| macOS (Apple Silicon) | `./scripts/build-native-macos.sh` | `dist/native/Tubify-<version>-macos-arm64.dmg` |
| Windows x64 | `./scripts/build-native-windows.ps1` | `dist/native/Tubify-<version>-windows-x64-setup.exe` |

Platform notes are in [`platforms/macos`](../platforms/macos/README.md) and [`platforms/windows`](../platforms/windows/README.md).

## Releases

Every merge to `main` is built, tested on all three platforms and published as a versioned release. A pull request's label decides how big the version bump is: no label for a patch, **Feature** for a minor bump, **Major Release** for a major bump. The full release process is in [`docs/releases`](releases/README.md).

## Licensing

Tubify is MIT licensed (see [`LICENSE`](../LICENSE)). Packages that bundle third-party components must ship [`THIRD_PARTY_NOTICES.md`](../native/src/youtube_music_native/assets/THIRD_PARTY_NOTICES.md), which the build already does on every platform. If you add a dependency or a bundled binary, add it to that file too.

## What the Windows and macOS packages ship

Both builds bundle Qt themselves, so `native/pyproject.toml` depends on `PySide6-Essentials`, not the full `PySide6`, which adds Chromium, 3D and charting. [`packaging/bundle_contents.py`](../packaging/bundle_contents.py) then keeps only the QML modules and Controls style Tubify uses, drops Qt's translations and fails the build if a finished bundle holds unneeded files or passes its size limits.

If you import a new Qt module in Python or QML, add it to that file. `native/tests/test_bundle_contents.py` fails until you do. The Arch package uses the system's Qt and isn't affected.
