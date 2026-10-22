# YouTube Music native client specification

Build a native desktop music client that closely matches YouTube Music and uses fewer resources than the current web wrapper. Ship Arch Linux/KDE first with shared Python/PySide6 and Qt Quick/QML code for later Windows and macOS releases.

Project: [YouTube Music Native Client](https://linear.app/nouvelle-lune-atelier/project/youtube-music-native-client-1fd71f68c65b).

## Required experience

The approved post-release direction is recorded in the [native QoL roadmap](native-qol-roadmap.md), beginning with LUNE-367. Preserve the existing twelve presets and custom themes; Classic remains the default and the user's selected theme is retained. LUNE-355's charcoal/lavender palette remains available as Midnight Violet. Shared foreground, surface, accent and derived neutral progress-track roles replace hardcoded colors. Bundled Roboto, consistent item bounds/insets, visible keyboard focus and accessible controls apply throughout.

Keep the compact navigation rail and expandable sidebar, responsive browsing, and the 92 pixel floating bottom player with content reserved above it. Preserve a 920 by 620 minimum. Playlist/album pages retain artwork headers, collection actions and virtualized track tables. Artwork selects adequate physical resolution for its size and DPR, with large local originals and asynchronous cache upgrades. Bounded optional blur has a software-rendering fallback.

Queue and Lyrics become independent right docks: content, Lyrics, Queue when both are open; Lyrics is rightmost when alone. Keep at least 480 logical pixels for central content and 280 per dock. Below that available width, use a single tabbed dock while remembering both requested open states and widths for restoration. The player remains visible. The far-right player button and F toggle an in-window immersive player that hides browsing navigation; Escape restores route, scroll and focus. This does not enter OS fullscreen.

Required views are Home, Explore, search, library, playlist, album, artist, immersive player, queue, lyrics and Downloads. Reuse queue/lyrics surfaces across browsing and immersive playback. Lyrics use primary text for the active line or plain text, readable secondary context, real timestamp seeking and follow-current-line behavior; manual scrolling suspends follow for six seconds with an explicit Follow lyrics action. Optional external providers are covered by the roadmap.

Synthetic checks cover 1600 by 900, 1280 by 820 and 920 by 620, dock combinations, scaling/DPR and focus/loading/error states. The original reference inventory below records historical v0.1.0 verification, not completed verification of the new roadmap or a pixel-parity requirement. Keep private reference screenshots outside the repository.

Required account behavior for the user's single Premium account:

- Personalized Home shelves, Explore charts/moods/genres, music search/suggestions/filters and artist/album pages.
- Library contents, saved music, subscriptions, playlist shortcuts and ratings.
- Playlist create/rename/delete, add/remove/reorder and correct handling of duplicate entries.
- Native audio-only playback, seek, previous/next, volume/mute, shuffle, repeat, radio/autoplay, online history and an editable queue.
- In-window immersive player, independent Queue/Lyrics docks and available lyrics, with seeking/highlighting only when real timing is returned.
- Persist window/sidebar preferences, volume, queue and position; restore playback paused after restart.
- Media keys, familiar keyboard shortcuts and KDE media controls; shortcuts must respect text-entry focus.

Videos, podcasts, casting, uploads, free-account behavior, automatic playlist download synchronization and crossfade remain outside the initial release scope. The post-release roadmap adds optional desktop/integration features; LUNE-388 evaluates native casting feasibility only and does not authorize a casting implementation.

### Priority manual queue (LUNE-356)

The queue surface pins Now playing above one virtualized scrolling area containing Queued songs, its compact drop target, and Next from [source name]. History is retained for playback and persistence but is not rendered. The manual section has no fixed height cap or separate scrollbar. Add to queue appends to the manual group; Play next prepends. Albums/playlists are gathered asynchronously in full, using downloaded metadata first, then inserted atomically in action order. Failures discard that batch and show a retry explanation. Clear queued songs cancels unfinished additions as well as pending manual entries.

Explicit new playback replaces source/history and starts the selected song, preserving pending manual additions. Shuffle/repeat-all affect only the source; repeat-one retains its current behavior. Manual additions play once. Previous follows actual selection history without re-enqueuing consumed manual entries; after three seconds it restarts the current song. Next consumes pending manual entries before the source. Selection of a later manual entry skips earlier manual entries; source selection keeps manual additions. Preserve reordering within pending groups and source-to-manual drag, with stable keys for duplicates and equivalent keyboard operations. Empty enqueue selects paused; enqueue while paused stays paused.

Transport, prefetch and MPRIS share the same next-entry calculation. Pagination and autoplay append to the source explicitly. Unknown sources use “Next up”. Snapshot version 2 stores the source name, source, manual, current and history; version 1 migrates losslessly into the source and restores paused. Synthetic tests cover these transitions, async cancellation/error/order, migration, offline playback, keyboard/drag editing and real worker/libmpv playback.

## Downloads and offline behavior

A single song, album or playlist can be downloaded with its metadata, artwork and collection order. Playlist downloads are manual snapshots; repeating Download refreshes the snapshot.

Every playback entry point checks for a completed local asset before resolving a remote source. Downloaded audio always plays from disk, even while online, without stream resolution or audio-network requests for that track. An offline restart must not require authentication refresh. Downloads are retained across app restarts and upgrades until explicitly removed.

Provide progress, cancellation, retry, offline browsing, removal and storage usage. Persist jobs and preserve completed tracks after failure. Resume partial media when supported; otherwise restart only that track. Validate and atomically finalize each asset before marking it ready. Share audio files between collections and retain them while any downloaded collection or individually saved song references them.

Handle disk-full, missing and corrupt files clearly without losing other completed downloads. Damaged files receive a repair indication and can fall back to streaming when online. Offline queues skip unavailable items with a visible explanation. Local playback/queue operations remain available; account mutations require connectivity. Cache lyrics when already available without making them a download prerequisite.

## Architecture and portability

- Native rendering: Qt 6, Qt Quick/QML, PySide6. Use virtualized list views, asynchronous artwork and bounded caches; keep network, SQLite work and extraction off the GUI thread.
- Catalog: ytmusicapi with small normalized MediaItem, Collection and paginated-result models. Preserve provider mutation identifiers and continuation tokens inside the catalog module. Run provider requests in a separate worker process: ytmusicapi changes process locale, while libmpv requires the C numeric locale. QML does not consume raw provider responses.
- Authentication: guided local browser-session import and secure OS keyring storage. The user has explicitly authorized reusing the existing Tauri session for migration/proof. Keep credentials out of source, fixtures, process arguments, logs and tickets. Expiry produces a reconnect banner without blocking local audio.
- Source resolution/downloads: yt-dlp managed workers, yt-dlp-ejs, Deno and FFmpeg/ffprobe. Preserve the best available authenticated audio-only format without routine transcoding. Cache remote sources only until expiry and retry expired resolution once.
- Playback: libmpv through python-mpv. The app owns LocalFile/RemoteStream selection, queue state and upcoming-track preparation. Do not load the YouTube website for playback.
- Persistence: SQLite metadata and durable downloads in Qt's standard app-data directory, separate from replaceable artwork caches. Store secrets only through secure keyring backends.
- Keep catalog, playback/source selection and downloads behind small interfaces with fixture/fake adapters for tests. There is no hosted backend. LUNE-383 adds an optional authenticated loopback-only HTTP/event interface, disabled by default, with separate read-only overlay and playback-control scopes; it never exposes account sessions or signed media URLs.
- Use Qt standard paths/settings. Keep OS media controls, secure-storage integration and packaging out of shared application logic.
- Run early Linux/Windows/macOS launch and local-audio smoke checks. Later ports reuse the UI, catalog, storage and playback code and validate platform-specific dependencies on real machines.

The native application lives under native/ while the current Tauri wrapper remains available. The first Linux release uses a separate youtube-music-native package, separate application data and native-v* tags.

## Compatibility gate

Before substantial UI implementation, prove authenticated catalog access, audio-only streaming, downloading, and replay in a new process with networking disabled using the user's real imported session. Save a redacted compatibility report. Fixture tests alone cannot pass this gate. Required unsupported features or unavailable playback formats are explicit blockers.

Initial access testing must be read-only against the account. Playlist mutation tests later use clearly named reversible test content.

## Verification and performance

Use sanitized provider fixtures, synthetic visual content and generated/local licensed audio in committed tests. Keep private account screenshots and session files outside the repository.

Test pagination, stale search responses, provider errors, duplicate playlist entries, queue transitions, shuffle/repeat, expired sessions/sources, download interruption/restart, corrupt media, disk-full, shared-file removal, mixed offline queues, suspend/resume and update preservation.

Assert across all playback entry points that downloaded audio starts without stream resolution or fetching its audio. Repeat after an offline restart and with expired credentials.

The planning sample measured approximately 537 MiB proportional-set memory across four current-wrapper processes during a 10 second visible-playback interval on Arch/KDE Wayland. This is preliminary evidence, not a controlled benchmark; the running wrapper may differ from main.

Establish matched wrapper/native baselines on the same machine, content, account, window and network. Count all app workers. Measure repeated cold/warm launches, track starts/skips, a scrolling scenario, minimized playback and a 30 minute mixed-use soak.

| Area | Release target |
| --- | --- |
| Scrolling | Approximately 60 fps; p95 frame time at most 16.7 ms |
| Local controls | Visible response within 100 ms |
| Interactive shell | At most 2 seconds cold and 1 second warm |
| Downloaded audio start | At most 250 ms |
| Steady playback memory | At most 300 MiB PSS and at least 40 percent below matched wrapper baseline |
| Minimized CPU | Average at most 2 percent of one logical core |
| Streaming startup and skips | No worse than matched wrapper baseline |

Fix missed targets before the Linux release and attach actual results. Visual checks cover 1280 by 820 and 920 by 620 layouts, focus, loading, empty and retry states.

## Reference inventory

| Reference | Evidence and follow-up |
| --- | --- |
| Home/sidebar/search/shelves/bottom player | Running app inspected during planning; private capture is outside the repository |
| Explore/search/library | Explore and Library captured privately; search input inspected through accessibility. Native fixture layouts checked at both sizes; direct search-results screenshot comparison remains unavailable |
| Playlist/album/artist | Album/artist private references and playlist accessibility geometry inspected; native layouts checked at both sizes. Full-width artist artwork, circular cards and bounded retry messages verified; direct playlist screenshot comparison remains unavailable |
| Expanded player/queue/lyrics | Expanded artwork/queue/tab geometry inspected through accessibility; native layouts checked at both sizes, with queue keyboard editing and missing/timed lyric tests. KDE denied targeted window capture, so direct screenshot comparison remains unavailable |
| Downloads | New view following the existing visual language |
| Performance | Preliminary memory sample only; controlled baseline belongs to the verification work |

The historical verification checklist and limitations are recorded in native/evidence/linux-verification.json; these results do not establish completion of the post-release QoL acceptance matrix. Synthetic rendering checks cover every required view, keyboard/accessibility behavior and a virtualized 10,000-song list. Reference geometry and inspected captures support close visual parity, but the unavailable reference screenshots prevent a complete pixel comparison. Actual machine sleep/wake remains deferred at the user's request; simulated recovery is reported separately.

## Linear delivery

The original delivery issues are listed below. The [native QoL roadmap ticket table](native-qol-roadmap.md#linear-tickets-and-dependency-order) records the actual assigned LUNE-367 through LUNE-388 issues, titles, blocking relations and acceptance matrix. Branches use the identifier exactly; commits use the identifier followed by a change-specific message. Issue titles and identifiers must not be replaced by planning placeholders.

| Issue | Actual ticket title |
| --- | --- |
| [LUNE-335](https://linear.app/nouvelle-lune-atelier/issue/LUNE-335/publish-the-native-client-specification-and-reference-baseline) | Publish the native client specification and reference baseline |
| [LUNE-336](https://linear.app/nouvelle-lune-atelier/issue/LUNE-336/prove-premium-account-access-streaming-and-offline-playback) | Prove Premium account access, streaming and offline playback |
| [LUNE-337](https://linear.app/nouvelle-lune-atelier/issue/LUNE-337/establish-the-portable-qt-native-application-and-visual-shell) | Establish the portable Qt native application and visual shell |
| [LUNE-338](https://linear.app/nouvelle-lune-atelier/issue/LUNE-338/implement-secure-session-import-and-reconnect-handling) | Implement secure session import and reconnect handling |
| [LUNE-339](https://linear.app/nouvelle-lune-atelier/issue/LUNE-339/implement-catalog-models-pagination-and-local-metadata-caching) | Implement catalog models, pagination and local metadata caching |
| [LUNE-340](https://linear.app/nouvelle-lune-atelier/issue/LUNE-340/implement-native-playback-queue-management-and-stream-resolution) | Implement native playback, queue management and stream resolution |
| [LUNE-341](https://linear.app/nouvelle-lune-atelier/issue/LUNE-341/reproduce-personalized-home-and-explore-views) | Reproduce personalized Home and Explore views |
| [LUNE-342](https://linear.app/nouvelle-lune-atelier/issue/LUNE-342/implement-music-search-artist-pages-and-album-pages) | Implement music search, artist pages and album pages |
| [LUNE-343](https://linear.app/nouvelle-lune-atelier/issue/LUNE-343/implement-library-playlist-editing-ratings-and-listening-history) | Implement library, playlist editing, ratings and listening history |
| [LUNE-344](https://linear.app/nouvelle-lune-atelier/issue/LUNE-344/implement-expanded-player-queue-editing-lyrics-and-shortcuts) | Implement expanded player, queue editing, lyrics and shortcuts |
| [LUNE-345](https://linear.app/nouvelle-lune-atelier/issue/LUNE-345/implement-durable-download-jobs-and-storage-management) | Implement durable download jobs and storage management |
| [LUNE-346](https://linear.app/nouvelle-lune-atelier/issue/LUNE-346/implement-downloads-views-and-local-first-playback-everywhere) | Implement Downloads views and local-first playback everywhere |
| [LUNE-347](https://linear.app/nouvelle-lune-atelier/issue/LUNE-347/implement-kde-media-integration-and-suspend-recovery) | Implement KDE media integration and suspend recovery |
| [LUNE-348](https://linear.app/nouvelle-lune-atelier/issue/LUNE-348/verify-visual-parity-accessibility-and-failure-recovery) | Verify visual parity, accessibility and failure recovery |
| [LUNE-349](https://linear.app/nouvelle-lune-atelier/issue/LUNE-349/tune-responsiveness-resource-usage-and-playback-latency) | Tune responsiveness, resource usage and playback latency |
| [LUNE-350](https://linear.app/nouvelle-lune-atelier/issue/LUNE-350/package-and-release-the-arch-native-client) | Package and release the Arch native client |
| [LUNE-355](https://linear.app/nouvelle-lune-atelier/issue/LUNE-355) | Redesign the native client with purple accents and artwork-led collection pages |
| [LUNE-356](https://linear.app/nouvelle-lune-atelier/issue/LUNE-356) | Add a priority manual queue ahead of the playback source |
| [LUNE-357](https://linear.app/nouvelle-lune-atelier/issue/LUNE-357) | Polish native icons and circular profile and artist artwork |
| [LUNE-351](https://linear.app/nouvelle-lune-atelier/issue/LUNE-351/port-and-package-the-native-client-for-windows) | Port and package the native client for Windows |
| [LUNE-352](https://linear.app/nouvelle-lune-atelier/issue/LUNE-352/port-and-package-the-native-client-for-macos) | Port and package the native client for macOS |

The Linear issues contain milestones, blocking relations, acceptance criteria and verification requirements. M0 is complete, including the real-account compatibility gate recorded in native/evidence/linux-compatibility.json. Windows and macOS are later delivery milestones, while portability checks start during the native foundation.

## Git and release workflow

Fetch the latest origin/main and create each ticket branch directly from it. The branch name is exactly the assigned identifier, for example LUNE-335. Do not use agent/* branches as bases, create descriptive branch suffixes or stack work on unmerged ticket branches.

Commit subjects follow LUNE-335 - Change-specific message, using the current ticket's identifier. Every PR targets main. Merge through the PR only after its work is complete, review concerns are resolved and all required checks pass for the current head. Do not push implementation changes directly to main.

The current Tauri application remains available during native development and the initial separate-package release. Google interface changes remain an ongoing maintenance dependency.

## Upstream references

- [Qt Quick performance](https://doc.qt.io/qt-6.8/qtquick-performance.html)
- [ytmusicapi capabilities](https://ytmusicapi.readthedocs.io/en/stable/)
- [Browser-session authentication](https://ytmusicapi.readthedocs.io/en/stable/setup/browser.html)
- [yt-dlp dependencies and embedding](https://github.com/yt-dlp/yt-dlp)
- [python-mpv](https://github.com/jaseg/python-mpv)

- [YTMDesktop official feature overview](https://ytmdesktop.github.io/)
- [YTMDesktop2 official feature documentation](https://youtube-music.app/docs/features/)
