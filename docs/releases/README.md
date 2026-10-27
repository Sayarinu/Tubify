# Release Layout

Tubify is released from the shared native client in `native/`. Platform packaging lives in `packaging/*-native` and `scripts/build-native-*`.

Tag a release whose version matches `native/pyproject.toml`:

```sh
git tag native-v0.1.1
git push origin native-v0.1.1
```

`.github/workflows/native-release-linux.yml` builds, installs and upgrades the Arch package in a clean Arch container. It then publishes the package and `SHA256SUMS` to a GitHub Release.

`.github/workflows/native.yml` builds the macOS DMG and the Windows installer on every pull request and uploads them as workflow artifacts (`tubify-macos-arm64`, `tubify-windows-x64-installer`).
