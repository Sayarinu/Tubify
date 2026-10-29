# Tubify

A native Python/Qt (PySide6 + QML) desktop client for YouTube Music with offline downloads. Linux, macOS and Windows share one codebase in `native/`.

The [specification and QoL roadmap](https://linear.app/nouvelle-lune-atelier/issue/LUNE-367/publish-native-qol-roadmap-and-revised-player-specification) and the [launch and packaging guide](https://linear.app/nouvelle-lune-atelier/issue/LUNE-389/move-native-client-implementation-documentation-into-linear) live in Linear.

## Signing in

Tubify reuses the YouTube Music sign-in from your own browser and opens it for you if you aren't signed in yet. Sign in to YouTube Music in Firefox, Chrome, Edge, Safari or another supported browser, then choose **Sign in via Browser**.

## Development

```sh
cd native
python -m pip install -e '.[test]'
python -m pytest tests -q
youtube-music-native --fixture   # synthetic data, no account needed
```

Playback needs libmpv, FFmpeg and Deno on `PATH`.

## Packages

Build each package on its own OS:

| Platform | Command | Output |
|---|---|---|
| Arch Linux x86_64 | `./scripts/build-native-arch-package.sh` | `dist/native/youtube-music-native-*.pkg.tar.zst` |
| macOS (Apple Silicon) | `./scripts/build-native-macos.sh` | `dist/native/Tubify-<version>-macos-arm64.dmg` |
| Windows x64 | `./scripts/build-native-windows.ps1` | `dist/native/Tubify-<version>-windows-x64-setup.exe` |

See `platforms/macos` and `platforms/windows` for platform notes. CI is in `.github/workflows/native.yml`. Tagging `native-v<version>` publishes verified packages for all three platforms.

Packaged installations check stable releases daily while running. **Settings → Updates & Troubleshooting** controls automatic checks and offers verified updates. Arch uses pacman with desktop authorization; Windows uses its per-user installer; macOS uses Sparkle. Install version 0.1.2 manually once to receive future in-app updates.
