# macOS

Tubify's macOS app is built for Apple Silicon.

## Requirements

An arm64 Mac with Homebrew and uv. The build installs `mpv`, `ffmpeg` and `deno` and bundles them, so the app runs without Homebrew on `PATH`.

## Build

```sh
./scripts/build-native-macos.sh
./scripts/sign-native-macos.sh <version>
```

The first script outputs `dist/native/Tubify-macos-arm64.app` and refuses a checkout with uncommitted changes; pass `--allow-dirty` for a local test build. The second outputs `dist/native/Tubify-<version>-macos-arm64.dmg`.

## Signing

Local builds are ad-hoc signed. Releases are signed with a stable self-signed identity, so keychain approvals survive updates, and are not notarized, so macOS warns on first open. Signing the Sparkle update checks the key with `swift`, which needs the Xcode command-line tools. See [Releases](../releases.md#signing-keys).

## System integration

The bundle registers the `ytmusic-native://` scheme, publishes to Now Playing and accepts the media keys.

## Signing in

Sign-in reuses the YouTube Music sign-in from your default browser, opening it if needed. Chrome-based browsers ask once for Keychain access, and Safari needs Full Disk Access.

## CI

Pull request CI builds and runs the app, signs it with a throwaway identity on a separate machine, and runs the signed app on a third. It then publishes the disk image as the `tubify-macos-arm64` workflow artifact.
