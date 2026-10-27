# macOS Release

Builds the macOS `.app` bundle and `.dmg` installer.

```sh
npm run build:macos
```

Outputs:

- `src-tauri/target/release/bundle/macos/YouTube Music.app`
- `src-tauri/target/release/bundle/dmg/YouTube Music_*.dmg`

Notes:

- Uses WKWebView through Tauri.
- Uses a Safari-style user agent so Google sign-in accepts the embedded WebKit engine.
- Requires macOS 11 or newer.

## Native Tubify client (Apple Silicon)

```sh
scripts/build-native-macos.sh
```

Outputs `dist/native/Tubify-macos-arm64.app` and `dist/native/Tubify-<version>-macos-arm64.dmg`. Needs an arm64 Mac with Homebrew and uv; the script installs `mpv`, `ffmpeg` and `deno` and bundles them, so the app runs without Homebrew on `PATH`. Builds are ad-hoc signed for local use, not notarized. The bundle registers the `ytmusic-native://` scheme, publishes to Now Playing and accepts the media keys. Signing in reuses the YouTube Music sign-in from your default browser (opening it if needed); Chrome-based browsers ask once for Keychain access, and Safari needs Full Disk Access.
