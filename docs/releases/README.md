# Release layout

`.github/workflows/native.yml` tests and packages Linux x86_64, Windows x64 and macOS arm64.

**Every push to main is a release, versioned by the size of its changes.** A `version` job in the workflow finds the newest `native-vX.Y.Z` tag on main and bumps it by the largest change merged since:

| Label on a merged PR | Bump | Example |
|---|---|---|
| none (default) | small change, patch | 0.1.1 → 0.1.2 |
| **Feature** | feature, minor | 0.1.7 → 0.2.0 |
| **Major Release** | major | 0.4.2 → 1.0.0 |

The "Release size" check on every PR shows the bump it will cause. It warns, without blocking, when a title that reads like a feature has no label. `scripts/native-release-version.py` stamps the chosen version into `native/pyproject.toml` and the Arch PKGBUILD in a local, unpushed CI commit, so every package is built as that version. Main runs are serialized so each bumps the version the previous one published. After all builds and tests pass, the pipeline publishes `native-v<version>` with the Windows, macOS and Linux app packages, `SHA256SUMS` and the signed macOS `appcast.xml`. `scripts/native-release-notes.py` writes short notes from the titles of the PRs merged since the previous release: **New** for Feature and Major Release PRs, **Improvements and fixes** for the rest, then a download table. The in-app update popup shows only the changes. The pacman package is published as `Tubify-<version>-linux-x86_64.pkg.tar.zst`. Releases include only the desktop app builds; the Arch source package is built only to test upgrades in CI. Published releases are never overwritten.

To jump to a specific version, raise it in `native/pyproject.toml` and the PKGBUILD together; a declared version higher than the computed one wins. A manual `native-vX.Y.Z` tag on a main commit still builds exactly X.Y.Z (it must match pyproject and pass the performance gate). Older `main-build-*` releases are kept for download but are not offered as updates.

The macOS build pins Sparkle 2.10.1 and verifies its distribution SHA-256. `TUBIFY_SPARKLE_PRIVATE_KEY` is a GitHub Actions secret; only `packaging/macos-native/sparkle-public-key.txt` belongs in source. Stable builds fail without the private key. Keep a secure backup of this key before rotating or deleting it; existing clients trust the embedded public key. The secret stores a 64-byte seed/public-key pair. `native/sign_update.py` extracts the 32-byte seed expected by Sparkle's `sign_update --ed-key-file -`, passes it only on stdin and verifies the generated signature before returning it. The actual vendor tool is checked against RFC 8032 before packaging. Update signatures do not provide Apple notarization.

Source launches and unsupported installations use release links. Automatic checks can be disabled; downloads require an explicit update action. Linux installation errors and cancelled authorization are reported on relaunch. Windows displays native installer errors. Sparkle provides native macOS update progress and recovery. All platforms preserve application data and restore playback paused.
