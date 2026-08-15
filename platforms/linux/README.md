# Arch Linux Release

Linux distribution is intentionally limited to Arch Linux x86_64. The release is a native `youtube-music-app-*.pkg.tar.zst` package, rather than an AppImage with an embedded GStreamer runtime.

Build from a clean checkout on Arch:

```sh
./scripts/build-arch-package.sh --syncdeps --install
```

The package is written to `dist/` and depends on Arch's `webkit2gtk-4.1`, `gst-plugins-base`, `gst-plugins-good`, `gst-plugins-bad`, and `gst-libav`. Verify the media plugins with:

```sh
./scripts/doctor-arch-media.sh
```

Tagging `v<package-version>` runs `.github/workflows/release-linux.yml`, which builds the package in an Arch container and attaches it plus `SHA256SUMS` to the GitHub Release.
