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

## Repository layout

| Path | Holds |
|---|---|
| `native/src/youtube_music_native/` | The app. Core modules are at the top; features are in `account/`, `catalog/`, `playback/`, `lyrics/`, `artwork/`, `downloads/`, `integrations/`, `system/` and `updates/`. |
| `native/src/youtube_music_native/qml/` | The UI: `Main.qml`, then `components/`, `pages/`, `player/`, `settings/`, `dialogs/` and `shell/`. |
| `native/tests/` | Unit tests (`test_*`) and smoke tests (`smoke_*`). |
| `packaging/` | Package definitions, in `linux/`, `macos/` and `windows/`. |
| `scripts/` | Build, signing and release tools. |
| `docs/` | This documentation. |

## Packages

Build each package on its own operating system. Requirements and details are on each platform's page.

| Platform | Page | Output |
|---|---|---|
| Linux x86_64 (pacman) | [Linux](platforms/linux.md) | `Tubify-<version>-linux-x86_64.pkg.tar.zst` |
| macOS (Apple Silicon) | [macOS](platforms/macos.md) | `Tubify-<version>-macos-arm64.dmg` |
| Windows x64 | [Windows](platforms/windows.md) | `Tubify-<version>-windows-x64-setup.exe` |

## Releases

See [Releases](releases.md).

## Licensing

Tubify is MIT licensed (see [`LICENSE`](../LICENSE)). Packages that bundle third-party components must ship [`THIRD_PARTY_NOTICES.md`](../native/src/youtube_music_native/assets/THIRD_PARTY_NOTICES.md), which the build already does on every platform. If you add a dependency or a bundled binary, add it to that file too.

## What the Windows and macOS packages ship

Both builds bundle Qt themselves, so `native/pyproject.toml` depends on `PySide6-Essentials`, not the full `PySide6`, which adds Chromium, 3D and charting. [`packaging/bundle_contents.py`](../packaging/bundle_contents.py) then keeps only the QML modules and Controls style Tubify uses, drops Qt's translations and fails the build if a finished bundle holds unneeded files or passes its size limits.

If you import a new Qt module in Python or QML, add it to that file. `native/tests/test_bundle_contents.py` fails until you do. The Linux package uses the system's Qt and isn't affected.
