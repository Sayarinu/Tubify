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

## Platforms

The source app is cross-platform, but desktop installers are platform-specific:

- macOS: `platforms/macos`
- Windows: `platforms/windows`
- Linux: `platforms/linux`

Build each target on its native OS. GitHub Actions release workflows are included under `.github/workflows/`.

Your YouTube Music login is stored in the app's WebKit data directory, separate from Safari and other browsers.
