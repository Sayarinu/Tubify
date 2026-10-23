# LUNE-386 — Release status and local diagnostics

**Settings → Updates and troubleshooting** checks published stable `native-vX.Y.Z` releases only when requested. It excludes wrapper releases, drafts and prereleases. The bounded worker request retains a small public cache; lookup failures explicitly label its last-known result and timestamp rather than claiming the app is current. No automatic update or background polling is installed. Arch installations remain owned by the package manager.

**Save diagnostics** writes an atomic JSON report to a chosen local file. The report allowlists application/dependency/Python/Qt versions, platform/window-system/renderer enums, window dimensions, DPI, app scale and motion/fixture flags. It excludes arbitrary settings, environment variables, account data, track metadata, paths, source URLs and logs. Nothing is uploaded.

For drawing glitches, close the app and launch `youtube-music-native --software-rendering`. A source checkout can use `PYTHONPATH=native/src python -m youtube_music_native --software-rendering`. This affects that launch only; a normal launch restores automatic graphics. It does not reset settings or delete caches/downloads.

## Verification

- 246 native tests and the full Qt/libmpv runtime suite passed on the initial integration base.
- Tests cover native-only version selection, bounded pagination/responses, offline cache/corruption, secret-field exclusion, nonfinite values, atomic export failure and idle/no-worker defaults.
- Real worker/UI export smoke verifies a synthetic 920×620 software-rendered window and modal playback-shortcut isolation.
- An explicit public GitHub lookup on 2026-10-23 returned `native-v0.1.1`; no account/session data was used.
- Platform CI will run on the final stacked PR head. No package upgrades or real user diagnostic exports were performed.

References: [GitHub release API](https://docs.github.com/en/rest/releases/releases#list-releases), [Qt scene graph adaptations](https://doc.qt.io/qt-6/qtquick-visualcanvas-adaptations.html).
