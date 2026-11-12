# Linux

Tubify's Linux package is built for x86_64 systems that use pacman.

## Requirements

An x86_64 system with `makepkg` and pacman. The package depends on the system's Qt, mpv and FFmpeg, so pacman installs them.

## Build

```sh
./scripts/build-native-linux-package.sh
```

Outputs `dist/native/tubify-*.pkg.tar.zst`, published as `Tubify-<version>-linux-x86_64.pkg.tar.zst`.

## Upgrading from before 1.0

Before 1.0 the package was called `youtube-music-native`. The `tubify` package replaces it: the PKGBUILD lists `youtube-music-native` in `provides`, `conflicts` and `replaces`. The old update helper only installs packages named `youtube-music-native`, so the in-app update can't move an older install to 1.0. Install the 1.0 package once by hand with `sudo pacman -U` and let pacman remove `youtube-music-native`. Settings, downloads and sign-in are kept: on first launch Tubify moves its folders from the old `YouTubeMusicNative/youtube-music-native` names to `Tubify/tubify`, and the login stays in the system keyring. Later updates install from the app again.

## Signing

Releases sign the package with the Ed25519 update key and publish the signature beside it. The package's update helper installs an update without a password only when this signature verifies and the version is newer. See [Releases](../releases.md#signing-keys).

## System integration

The package installs a desktop entry and publishes playback controls over MPRIS.

## Signing in

Sign-in reuses the YouTube Music sign-in from your browser.

## CI

Pull request CI builds the package, installs it over a stand-in `youtube-music-native` package, and tests upgrading to it. It then publishes it as the `native-linux-package` workflow artifact.
