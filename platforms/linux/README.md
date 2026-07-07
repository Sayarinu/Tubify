# Linux Release

Builds Linux AppImage, deb, and rpm packages.

```sh
npm run build:linux
```

Outputs:

- `src-tauri/target/release/bundle/appimage/*.AppImage`
- `src-tauri/target/release/bundle/deb/*.deb`
- `src-tauri/target/release/bundle/rpm/*.rpm`

Notes:

- Build this on Linux.
- Tauri uses WebKitGTK on Linux.
- A private GitHub release workflow is included in `.github/workflows/release-linux.yml`.
