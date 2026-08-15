# YouTube Music App

A lightweight Tauri wrapper that opens YouTube Music in a native desktop window.

## Requirements

- Node.js and npm
- Rust and Cargo
- Tauri's prerequisites for your platform

## Commands

```sh
npm install
npm run dev
npm run build:macos
npm run build:windows
npm run build:linux
```

`npm run build:linux` builds the native executable used by the Arch package. To create and install that package from a clean checkout, use:

```sh
./scripts/build-arch-package.sh --syncdeps --install
```

## Platforms

The source app is cross-platform, but desktop installers are platform-specific:

- macOS: `platforms/macos`
- Windows: `platforms/windows`
- Linux: `platforms/linux`

Build each target on its native OS. GitHub Actions release workflows are included under `.github/workflows/`.

Your YouTube Music login is stored in the app's WebKit data directory, separate from Safari and other browsers.

## Arch Linux

Linux releases target **Arch Linux x86_64**. They install a native Tauri/WebKitGTK executable and use Arch's current GStreamer packages; the former AppImage, deb, and rpm builds are not supported on Arch.

Install the latest release as a normal user:

```sh
release_tag="$(gh release view --repo Sayarinu/YouTube-Music-App --json tagName --jq .tagName)"
mkdir -p youtube-music-app-release
cd youtube-music-app-release
gh release download "$release_tag" --repo Sayarinu/YouTube-Music-App \
  --pattern 'youtube-music-app-*.pkg.tar.zst' \
  --pattern SHA256SUMS
sha256sum -c SHA256SUMS
sudo pacman -U ./youtube-music-app-*.pkg.tar.zst
```

The package pulls in `webkit2gtk-4.1`, `gst-plugins-base`, `gst-plugins-good`, `gst-plugins-bad`, and `gst-libav`, including the MP4, Matroska, H.264, AAC, and Opus support YouTube Music needs. It keeps the existing `com.carter.youtube-music` profile, so signing in again is normally unnecessary.

On Wayland desktops with XWayland available, the packaged launcher selects GTK's X11 backend automatically. This avoids compositor-specific GTK/WebKit protocol errors while retaining the same application profile and functionality.
