# Windows

## Native Tubify client (x64)

From a Windows x64 checkout with uv, MSYS2 UCRT64 (`mpv` and `ffmpeg`), Deno and Inno Setup 6:

```powershell
./scripts/build-native-windows.ps1
```

The per-user installer is written to `dist/native/Tubify-<version>-windows-x64-setup.exe`. It installs to `%LOCALAPPDATA%\Programs\Tubify` and bundles Qt, libmpv, FFmpeg and Deno, so nothing else needs to be installed.

Tubify shows track details in the Windows media flyout, and the media keys, play/pause, next/previous and seeking all work. Sign-in reuses the YouTube Music sign-in from your browser. Chrome and Edge lock and encrypt their cookies while they are open, so close the browser before signing in, or sign in to YouTube Music in Firefox.

Pull request CI builds, installs, upgrades, launches and uninstalls the package. It then publishes the installer as the `tubify-windows-x64-installer` workflow artifact.
