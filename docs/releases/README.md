# Release layout

`.github/workflows/native.yml` tests and packages Arch x86_64, Windows x64 and macOS arm64. Every main build remains downloadable, but only stable `native-vX.Y.Z` releases are offered by the app.

Bump `native/pyproject.toml` and the Arch PKGBUILD together. Tag the checked main commit with the matching version (the updater first ships in `native-v0.1.2`). Tags must be on main and pass the existing performance gate. The pipeline publishes a draft only after all builds/tests pass, uploads every package, source archive, Stream Deck plugin, `SHA256SUMS` and signed macOS `appcast.xml`, then publishes it. Published releases are never overwritten.

The macOS build pins Sparkle 2.10.1 and verifies its distribution SHA-256. `TUBIFY_SPARKLE_PRIVATE_KEY` is a GitHub Actions secret; only `packaging/macos-native/sparkle-public-key.txt` belongs in source. Stable builds fail without the private key. Keep a secure backup of this key before rotating or deleting it; existing clients trust the embedded public key. Signing uses Sparkle's `sign_update --ed-key-file -`, with private material passed on stdin. Update signatures do not provide Apple notarization.

Source launches and unsupported installations use release links. Automatic checks can be disabled; downloads require an explicit update action. Arch installation errors/cancelled authorization are reported on relaunch. Windows displays native installer errors. Sparkle provides native macOS update progress and recovery. All platforms preserve application data and restore playback paused.
