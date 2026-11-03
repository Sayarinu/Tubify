# macOS

## Tubify for macOS (Apple Silicon)

```sh
scripts/build-native-macos.sh
```

Outputs `dist/native/Tubify-macos-arm64.app` and `dist/native/Tubify-<version>-macos-arm64.dmg`.

The script refuses a checkout with uncommitted changes; pass `--allow-dirty` for a local test build.

- **Requirements:** an arm64 Mac with Homebrew and uv. The script installs `mpv`, `ffmpeg` and `deno` and bundles them, so the app runs without Homebrew on `PATH`.
- **Signing:** builds are ad-hoc signed for local use, not notarized. When `TUBIFY_SPARKLE_PRIVATE_KEY` is set, the script also signs the Sparkle update and checks the key with `swift`, so the Xcode command-line tools must be installed.
- **System integration:** the bundle registers the `ytmusic-native://` scheme, publishes to Now Playing and accepts the media keys.
- **Signing in:** reuses the YouTube Music sign-in from your default browser, opening it if needed. Chrome-based browsers ask once for Keychain access, and Safari needs Full Disk Access.
