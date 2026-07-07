# Release Layout

This project keeps one shared Tauri app and separates platform packaging into `platforms/*`.

Use tags to create releases:

```sh
git tag v0.1.0
git push origin v0.1.0
```

GitHub Actions will build separate release artifacts:

- macOS: `.app` and `.dmg`
- Windows: `.exe` and `.msi`
- Linux: `.AppImage`, `.deb`, and `.rpm`

Because Tauri packages native installers, each platform is built on a matching GitHub runner.
