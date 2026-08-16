# Release Layout

This project keeps one shared Tauri app and separates platform packaging into `platforms/*`.

Use tags to create releases:

```sh
git tag v0.1.2
git push origin v0.1.2
```

GitHub Actions will build separate release artifacts:

- macOS: `.app` and `.dmg`
- Windows: `.exe` and `.msi`
- Linux (Arch x86_64): `youtube-music-app-*.pkg.tar.zst` and `SHA256SUMS`

The Linux workflow builds in an Arch Linux container so the package links against the same WebKitGTK and GStreamer stack used by the target system. AppImage, deb, and rpm artifacts are retired for Linux.
