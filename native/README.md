# Native YouTube Music client

Shared Python code for the native Qt client. The first development gate is a repeatable real-account compatibility check, tracked by [LUNE-336](https://linear.app/nouvelle-lune-atelier/issue/LUNE-336/prove-premium-account-access-streaming-and-offline-playback).

The client connects accounts, renders personalized Home and Explore, searches music, manages the library/playlists, downloads collections and plays music through libmpv. The first release targets Arch Linux/KDE. Windows and macOS packaging is tracked by LUNE-351 and LUNE-352.

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

## Development preview

The redesigned UI uses charcoal surfaces and purple accents, a compact expandable navigation rail, a floating player and artwork headers on playlist/album pages. Queue and lyrics open in the expanded player. Navigation collapses below 1100 pixels; the minimum window remains 920×620.

With the native dependencies installed, run the checkout directly from the repository root:

```sh
PYTHONPATH="$PWD/native/src" python -m youtube_music_native --data-dir /tmp/youtube-music-native-preview
```

Add `--fixture` to explore synthetic content without account requests. The separate data directory holds preview settings, queue, cache and downloads; `/tmp` contents may disappear after reboot. The OS-keyring account is shared with the installed native application, so importing a session or signing out also affects that application. This preview does not install an Arch package.

## Arch package

The separate `youtube-music-native` package uses Arch's Python, PySide6/Qt, libmpv, provider libraries, FFmpeg and Deno packages. It installs a **YouTube Music Native** desktop entry alongside the existing Tauri wrapper. Application data, credentials and downloaded media are retained across package upgrades.

From a clean checkout, build with:

```sh
./scripts/build-native-arch-package.sh --syncdeps --noconfirm
sudo pacman -U ./dist/native/youtube-music-native-*.pkg.tar.zst
```

The build script checks the Python/Arch versions, hashes its Git source archive, runs the Python/Qt/audio checks and creates binary and source packages under `dist/native`. Runtime dependencies stay under pacman management. The clean-container check installs the package, launches the installed entry points and upgrades a temporary package revision while checking saved audio, duplicate collection entries, queue position and settings.

Published native releases use `native-v*` tags and include `SHA256SUMS`. Native publication requires the measured performance gate, and native releases do not replace the wrapper's latest-release designation. Existing wrapper tags and workflows remain separate. Windows/macOS packaging is tracked by LUNE-351 and LUNE-352.

## Connect an account

Open the profile button. On Linux, **Use existing Tauri session** imports the signed-in wrapper session without modifying its profile. Alternatively, choose a local [ytmusicapi browser.json export](https://ytmusicapi.readthedocs.io/en/stable/setup/browser.html). The client validates the account before replacing an existing connection.

Sessions are stored in the OS keyring (Secret Service/KWallet on Linux, Credential Manager on Windows, Keychain on macOS), with no plaintext fallback. Unlock the keyring if prompted. A restart restores the saved identity without a network request. An expired session shows a reconnect banner; downloaded media remains available. Sign out removes this client's credentials and cached identity, retaining downloaded music and leaving the wrapper signed in.

Import and reconnect run in a separate process so the window remains responsive. Export files are read only; remove them yourself after import if no longer needed. Never paste session credentials into chat or tickets.

Catalog responses use normalized song/album/artist/playlist models. The catalog worker handles provider continuations behind 40-item UI pages, suppresses stale results during navigation and reuses SQLite metadata when the provider is unavailable. Metadata is disposable and limited to 200 recent views, scoped to the account identity; it contains no credentials or signed audio URLs. QML artwork loads asynchronously through a 128 MiB disk cache and can reuse cached images after restart. Neither cache contains durable downloaded audio.

The native player owns the queue, audio-only source selection, transport, seek, volume, shuffle/repeat and autoplay. It checks verified local media before touching credentials or resolving a stream. Extraction runs in a separate worker, prepares the next track, caches sources only until expiry and retries a failed source once. A manual selection cancels active preparation so a slow request cannot delay the selected song. The extraction worker exits after idle time to release memory; up to three recent remote sources remain in memory for queue navigation. Queue order and position survive restart, with the current song preloaded paused; an offline preload failure preserves that selection and position. Signed audio URLs are never saved. Playback data uses the platform's application-data directory, separate from disposable caches.

Home shows personalized shelves and compact Quick picks; Explore offers new releases, charts, moods and genres. Artwork cards open collections, their play targets begin playback, and collection queues start with the first page while later pages load. Sidebar playlist shortcuts use the connected account. Signing out clears those account views and the extractor's in-memory session while allowing local audio to continue.

Search includes debounced suggestions, music filters, pagination and stale-response protection. Album pages offer full-album playback, shuffle, library and download controls; artist pages include subscriptions, top songs, releases and mixes. Back navigation restores loaded results, filters and scroll position without another provider request. Library/subscription changes use provider mutation identifiers and update the current view after success. These controls are tested with fake mutations; live page verification makes read-only account requests.

Library sections include playlists, saved songs, albums, artists, subscriptions, liked songs and history. Song/card menus offer queue actions, radio, ratings, saving, playlist addition and downloads. Owned playlists support private creation, renaming, deletion, single-entry removal and reordering, using each occurrence's unique identifier so duplicates remain distinct. Confirmed changes update immediately while the provider's read responses catch up. Empty playlists remain usable. Playback reports online listening after progress without blocking audio; history tracking URLs stay inside the provider worker. The native dialog check verifies that typing spaces does not trigger playback.

Real-account verification covers all library sections and the playlist view. The user-approved private test playlist passed creation, renaming, duplicate addition, movement, single-occurrence removal and deletion; native empty-playlist creation/reopening also passed and its test playlist was deleted. Existing playlists and ratings were not modified by these checks. History writes and ratings use fake-provider tests; the real account's history tracking data was checked read-only. Redacted results are in evidence/linux-library.json.

Downloads shows songs, albums and manual playlist snapshots with progress, cancellation, retry, repair, removal and storage usage. Jobs recover after interruption, resume supported HTTP transfers, retain completed songs on cancellation/failure, and validate audio with FFprobe before publishing it. Images and metadata are retained beside the audio for offline use. Removing a collection retains files referenced by another download; refreshing a snapshot retains its old files until the replacement finishes. Separate local control, online planning and transfer workers keep storage operations responsive during network delays. Local collection lookup happens before provider pagination for both opening and playback; song/card indicators and artwork reuse the durable download index.

A real saved song was downloaded and played through the native controllers in a network-disabled Linux namespace, including album/playlist snapshot playback, shuffle, queue selection and unavailable-song skipping. A second offline process restored paused playback and resumed from disk without catalog or session-import requests. The album/playlist snapshots in this test were synthetic containers referencing the real audio. Evidence is in evidence/linux-downloads-ui.json.

The expanded player retains audio and position while switching views, and includes a virtualized queue with drag handles, occurrence-specific menus and keyboard editing. Use Alt+Up/Down to move a focused queue entry and Delete to remove it. Lyrics load on demand, highlight and seek when timing is available, and remain cached for offline use. The real account returned plain lyrics through the desktop fallback; timed lyrics use synthetic tests. Evidence is in evidence/linux-expanded-player.json.

Press `?` for keyboard shortcuts: Space toggles playback, Shift+N/P changes tracks, arrows seek, M mutes, S/R changes shuffle/repeat, and F/Escape opens/closes the player. Playback shortcuts respect text fields, account/playlist dialogs and menus. `/` or Ctrl+F focuses search.

The visual verification script renders all required views at 1280×820 and 920×620 with synthetic content, checks accessible control names and a 10,000-song list, and can run a mixed-use local-audio soak:

```sh
python native/tests/smoke_visual.py --output-dir /tmp/native-visual-check
```

On Linux, `QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=rhi QSG_RHI_BACKEND=opengl` with `--native-gpu` also verifies rounded artwork without mapping a desktop window. `--soak-seconds 300` adds generated silent audio and repeated navigation. The software renderer checks layout and controls; image masking requires the normal GPU renderer. Evidence and outstanding reference-capture limits are in evidence/linux-verification.json. The performance ticket separately measures latency, resources and a 30-minute soak.

`python native/tests/benchmark_interaction.py --onscreen --output /tmp/native-interaction.json` measures the first rendered frame, visible mute response and five seconds of animated scrolling through 10,000 synthetic songs. `--launch-only` measures just the first frame. The default requires `QT_QPA_PLATFORM=offscreen`; choose `--onscreen` explicitly to use a desktop window. Artwork decoding follows the screen's device pixel ratio.

On Linux, `python native/tests/measure_resources.py --seconds 1830 --output /tmp/native-resources.json -- python native/tests/smoke_visual.py --native-gpu --soak-seconds 1800 --output-dir /tmp/native-soak` samples PSS and CPU across the launched app and all its helper processes. Set the GPU environment above first. The sampler keeps child output in a private local log. Synthetic interaction/soak results are separate from real-account streaming and matched wrapper measurements.

## Account and offline compatibility check

On Linux, MPRIS exposes metadata, transport, position, repeat/shuffle and volume to KDE desktop media controls. D-Bus and logind monitoring live in a Linux module; their I/O runs outside the GUI thread. Sleep interruption retains the queue and position and clears prepared remote sources; wake recovery respects newer user commands. Device errors keep valid local audio intact and allow retry. KDE pauses playback when an output is removed; explicit desktop Play was verified to resume the single native stream. Actual machine sleep/wake verification was deferred at the user's request and remains unverified; simulated recovery and output-change tests do not replace it.

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
