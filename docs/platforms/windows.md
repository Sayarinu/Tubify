# Windows

Tubify's Windows installer is built for x64.

## Requirements

A Windows x64 checkout with uv, MSYS2 UCRT64 (`mpv` and `ffmpeg`), Deno and Inno Setup 6. The installer bundles Qt, libmpv, FFmpeg and Deno, so people installing Tubify need nothing else.

## Build

```powershell
$env:TUBIFY_UPDATE_PUBLIC_KEY = gh variable get TUBIFY_UPDATE_PUBLIC_KEY
./scripts/build-native-windows.ps1
```

Outputs the per-user installer `dist/native/Tubify-<version>-windows-x64-setup.exe`, which installs to `%LOCALAPPDATA%\Programs\Tubify`.

## Signing

Installers have no Authenticode signature, so SmartScreen warns on first open. See [Releases](../releases.md#signing-keys).

## System integration

Tubify shows track details in the Windows media flyout, and the media keys, play/pause, next/previous and seeking all work.

## Signing in

Sign-in reuses the YouTube Music sign-in from your browser. Chrome and Edge lock and encrypt their cookies while they are open, so close the browser before signing in, or sign in to YouTube Music in Firefox.

## CI

Pull request CI builds, installs, upgrades, launches and uninstalls the package. It then publishes the installer as the `tubify-windows-x64-installer` workflow artifact.
