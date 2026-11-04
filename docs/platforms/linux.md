# Linux

Tubify's Linux package is built for x86_64 systems that use pacman.

## Requirements

An x86_64 system with `makepkg` and pacman. The package depends on the system's Qt, mpv and FFmpeg, so pacman installs them.

## Build

```sh
./scripts/build-native-linux-package.sh
```

Outputs `dist/native/youtube-music-native-*.pkg.tar.zst`, published as `Tubify-<version>-linux-x86_64.pkg.tar.zst`.

## Signing

Releases sign the package with the Ed25519 update key and publish the signature beside it. The package's update helper installs an update without a password only when this signature verifies and the version is newer. See [Releases](../releases.md#signing-keys).

## System integration

The package installs a desktop entry and publishes playback controls over MPRIS.

## Signing in

Sign-in reuses the YouTube Music sign-in from your browser.

## CI

Pull request CI builds the package, installs it, and tests upgrading to it. It then publishes it as the `native-linux-package` workflow artifact.
