# Native YouTube Music client

Shared Python code for the native Qt client. The first development gate is a repeatable real-account compatibility check, tracked by [LUNE-336](https://linear.app/nouvelle-lune-atelier/issue/LUNE-336/prove-premium-account-access-streaming-and-offline-playback).

The portable Qt window and reusable visual shell are tracked by [LUNE-337](https://linear.app/nouvelle-lune-atelier/issue/LUNE-337/establish-the-portable-qt-native-application-and-visual-shell). Account connection is available; catalog integration and playback follow as separate tickets. The window is a development preview.

## Development

Use Python 3.12 or newer and an isolated environment:

```sh
python -m venv .venv
.venv/bin/python -m pip install -e './native[test]'
.venv/bin/python -m pytest native/tests
```

On Windows use `.venv\Scripts\python.exe`. Session import and shared logic work across platforms; the complete network-isolated gate currently targets Linux.

Launch the Qt window with `youtube-music-native`. For repeatable visual checks, `youtube-music-native --fixture --screenshot /tmp/native-music.png` uses synthetic data and exits after saving an image. The ordinary window does not load this fixture. `--data-dir` supplies isolated preferences for development and tests.

The interface bundles the existing music mark and OFL-licensed Roboto fonts, uses native Qt Quick rendering, and keeps provider work outside the GUI thread. CI creates a real window and decodes a generated local WAV through libmpv on Linux, Windows and macOS. These smoke checks do not replace the later full platform-port acceptance work.

## Connect an account

Open the profile button. On Linux, **Use existing Tauri session** imports the signed-in wrapper session without modifying its profile. Alternatively, choose a local [ytmusicapi browser.json export](https://ytmusicapi.readthedocs.io/en/stable/setup/browser.html). The client validates the account before replacing an existing connection.

Sessions are stored in the OS keyring (Secret Service/KWallet on Linux, Credential Manager on Windows, Keychain on macOS), with no plaintext fallback. Unlock the keyring if prompted. A restart restores the saved identity without a network request. An expired session shows a reconnect banner; downloaded media remains available. Sign out removes this client's credentials and cached identity, retaining downloaded music and leaving the wrapper signed in.

Import and reconnect run in a separate process so the window remains responsive. Export files are read only; remove them yourself after import if no longer needed. Never paste session credentials into chat or tickets.

## Account and offline compatibility check

The check requires libmpv, FFmpeg/ffprobe, Deno or a supported Node.js runtime, and Linux `unshare`. Importing the existing Tauri profile also requires system PyGObject and libsoup 3. On Arch these native dependencies are provided by `mpv`, `ffmpeg`, `deno`, `python-gobject` and `libsoup3`. A virtual environment created with `--system-site-packages` can access the system PyGObject bindings.

Select the existing Tauri cookie file explicitly:

```sh
youtube-music-native-check check \
  --tauri-cookies ~/.local/share/com.carter.youtube-music/cookies
```

Alternatively, select a locally created [ytmusicapi browser.json export](https://ytmusicapi.readthedocs.io/en/stable/setup/browser.html):

```sh
youtube-music-native-check check --session /path/to/browser.json
```

The check makes read-only account/catalog requests, streams one library song silently, downloads it to a private temporary directory, validates it, and plays it in a new process with networking disabled. It does not modify the Tauri profile or account library. It requires at least one saved library song.

Provider calls run separately from the native player because ytmusicapi changes the process locale and libmpv requires the C numeric locale. Signed audio URLs and headers pass through process stdin; reports contain stage results only. A pass verifies decoding and playback with null audio output, not audible device output.

The tool prints the private report path. Proof media and reports are retained there for inspection and can be removed after validation. Keep session exports and private account data out of Git and tickets. Automated fixture tests cannot replace this real-account gate.
