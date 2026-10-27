# Windows Release

Builds the Windows NSIS and MSI installers.

```sh
npm run build:windows
```

Outputs:

- `src-tauri/target/release/bundle/nsis/*.exe`
- `src-tauri/target/release/bundle/msi/*.msi`

Notes:

- Build this on Windows.
- Tauri uses WebView2 on Windows.
- A private GitHub release workflow is included in `.github/workflows/release-windows.yml`.

## Native Tubify client

The native Python/Qt client is packaged separately from the Tauri application. Build its per-user Windows x64 installer from a Windows x64 checkout with uv, MSYS2 UCRT64 (`mpv` and `ffmpeg`), Deno, and Inno Setup 6:

```powershell
./scripts/build-native-windows.ps1
```

The installer is written to `dist/native/Tubify-<version>-windows-x64-setup.exe`. Pull request CI also builds, installs, upgrades, launches, and uninstalls the package, then publishes the installer as the `tubify-windows-x64-installer` workflow artifact for validation. This is separate from the existing Tauri NSIS/MSI release workflow.
