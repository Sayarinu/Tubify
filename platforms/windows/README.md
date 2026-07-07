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
