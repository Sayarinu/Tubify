# Native YouTube Music client

Shared Python code for the native Qt client. The first development gate is a repeatable real-account compatibility check, tracked by [LUNE-336](https://linear.app/nouvelle-lune-atelier/issue/LUNE-336/prove-premium-account-access-streaming-and-offline-playback).

The client now connects accounts, renders personalized Home and Explore, and plays music through libmpv. The window remains a development preview while the remaining search, library, expanded-player, downloads and release tickets are completed.

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

Catalog responses use normalized song/album/artist/playlist models. The catalog worker handles provider continuations behind 40-item UI pages, suppresses stale results during navigation and reuses SQLite metadata when the provider is unavailable. Metadata is disposable and limited to 200 recent views, scoped to the account identity; it contains no credentials or signed audio URLs. QML artwork loads asynchronously through a 128 MiB disk cache and can reuse cached images after restart. Neither cache contains durable downloaded audio.

The native player owns the queue, audio-only source selection, transport, seek, volume, shuffle/repeat and autoplay. It checks verified local media before touching credentials or resolving a stream. Extraction runs in a separate worker, prepares the next track, caches sources only until expiry and retries a failed source once. The extraction worker exits after idle time to release memory. Queue order and position survive restart, with playback restored paused; signed audio URLs are never saved. Playback data uses the platform's application-data directory, separate from disposable caches.

Home shows personalized shelves and compact Quick picks; Explore offers new releases, charts, moods and genres. Artwork cards open collections, their play targets begin playback, and collection queues start with the first page while later pages load. Sidebar playlist shortcuts use the connected account. Signing out clears those account views and the extractor's in-memory session while allowing local audio to continue.

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
