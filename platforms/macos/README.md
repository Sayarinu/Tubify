# macOS Release

Builds the macOS `.app` bundle and `.dmg` installer.

```sh
npm run build:macos
```

Outputs:

- `src-tauri/target/release/bundle/macos/YouTube Music.app`
- `src-tauri/target/release/bundle/dmg/YouTube Music_*.dmg`

Notes:

- Uses WKWebView through Tauri.
- Uses a Safari-style user agent so Google sign-in accepts the embedded WebKit engine.
- Requires macOS 11 or newer.
