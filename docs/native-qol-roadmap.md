# Native client quality-of-life roadmap

Approved implementation baseline: 2026-10-22. Delivery starts with [LUNE-367](https://linear.app/nouvelle-lune-atelier/issue/LUNE-367/publish-native-qol-roadmap-and-revised-player-specification).

This document records the approved native adaptation of [YTMDesktop](https://ytmdesktop.app/) and [YTMDesktop2](https://youtube-music.app/), together with the requested player, queue, lyrics and visual corrections. It specifies planned behavior; a listed feature is not evidence that our client already ships it. The [native client specification](native-client-spec.md) remains authoritative for account access, local-first audio, storage, portability and release gates.

## Existing baseline and reconciliation

The foundation branch started from freshly fetched main; later QoL branches follow the scoped stacked-PR workflow below. The foundation baseline is 293042a (LUNE-365, native 0.1.1); it includes ad0f0e0 (LUNE-364). The real-account compatibility gate is already recorded as passed in [linux-compatibility.json](../native/evidence/linux-compatibility.json). This roadmap does not substitute fixture success for further real-account or hardware verification.

The original LUNE-364 checkout had six modified tracked files. A read-only comparison of its working diff against that branch and fetched main found:

| Local changes | Disposition on main |
| --- | --- |
| Artist navigation, name fallback and track metadata enrichment in browse.py | Already represented; main additionally bounds the metadata fallback attempt, observes player track changes and propagates large artwork. |
| Artist identifier and album normalization in catalog.py | Already represented; main additionally retains largeThumbnail. |
| Removal of an explicit queue subtitle in ExpandedPane.qml | Superseded by the shared queue component; retain the current row metadata rendering. |
| Keyboard and accessibility artist links in MediaCard.qml | Already represented; main uses the live theme controller. |
| Player artwork sizing, title/artist metadata flow, album link, ratings and elapsed/duration alignment in PlayerBar.qml | Already represented; main additionally exposes the queue dock and updated live theme bindings. |
| Artist/album links and row click layering in SongRow.qml | Already represented; main additionally has queue drag handling, separate album metadata and queue-specific controls. |

No local edit was copied, discarded, staged, reset or stashed. The complete old patch must not be replayed: it would replace newer metadata safeguards, theme bindings and queue behavior. Preserve those six local files for the owner to reconcile separately. Private screenshots and account data are not part of this evidence.

## Source comparison and native disposition

Research date: 2026-10-22. The requested second site belongs to Venipa/YTMDesktop2, not Pear Desktop. Reference releases are [YTMDesktop v2.0.12](https://github.com/ytmdesktop/ytmdesktop/releases/tag/v2.0.12) and [YTMDesktop2 v1.8.6](https://github.com/Venipa/ytmdesktop2/releases/tag/v1.8.6). Documentation and default-branch source also identify capabilities whose release/platform support must be checked in their implementation tickets. This is a behavior comparison, not a request to copy their Electron rendering or DOM hooks.

| Capability | YTMDesktop | YTMDesktop2 | Native disposition |
| --- | --- | --- | --- |
| Startup and window lifecycle | Login startup, tray close/menu, saved window/player state | Login startup, minimized startup, tray close, active-display placement | LUNE-377/378: optional tray/lifecycle controls with reachable-window fallback. [A1] [B1] [B19] |
| Track notifications | Configurable song-change notifications | Desktop media surfaces and tray player | LUNE-378: optional notifications and consistent success/error feedback. [A1] |
| Playback continuity | Resume context, optionally paused | Uses embedded player continuity | Preserve existing durable queue/position and paused restoration. [A1] |
| Sleep timer | 5/10/15/30/45/60 minutes, cancel, pause at expiration | Not established by current feature docs | LUNE-375. [A2] |
| Audio convenience | Nonlinear volume, speaker fill | Exponential volume; experimental skip disliked tracks | LUNE-375 and capability-gated LUNE-387. [A1] [B2] |
| Library actions | Player-bar library/playlist shortcuts | Standard service actions | LUNE-375 reuses existing native account commands. [A2] |
| Appearance | Custom CSS, zoom, always-visible volume, Linux tray icon styles | Bundled/custom CSS/SCSS, live reload, artwork background, optional blur | Keep native presets/custom theme format; LUNE-368/376 supplies equivalent appearance control without CSS injection. [A1] [B3] |
| DPI and scale | App zoom | OS DPI plus independent content zoom | LUNE-376: 80–150% in 5% steps, with OS DPR independent. [B4] |
| Keyboard | Configurable global transport, ratings and volume | Additional play/pause, seeking, shuffle/repeat; validation/reset; Wayland portal | LUNE-379, preserving local text-entry/modal guards. [A1] [B5] |
| Desktop media | Tray transport, taskbar buttons/progress | Native media bridge, taskbar controls/progress, macOS Touch Bar | Reuse existing MPRIS; isolate platform adapters in LUNE-377/379 and existing Windows/macOS port tickets. [A3] [B6] [B18] |
| Compact player | Tray menu | Pinnable/movable tray player with artwork, controls, seek, ratings and expandable queue | LUNE-377. Old standalone mini-player was removed in 1.4.0. [B1] [B7] |
| Lyrics | Native service lyrics through its wrapper | Multiple timed providers, provider order, real word/syllable timing, seeking, follow behavior, styles | LUNE-372/374, using the approved provider policy below. [B8] |
| Navigation/sharing | Companion integration | App deep links, play/queue/open choices, optional browser userscript | LUNE-382 with preview by default and an app-specific protocol. [B9] [B20] |
| Discord | Rich Presence, linked metadata | Configurable presence/buttons | LUNE-380, disabled initially. [A4] [B10] |
| Last.fm | Account authorization and scrobble percentage | Now Playing, repeat-aware scrobbles, counterpart deduplication, long-pause refresh and re-auth | LUNE-381 with listening-duration accounting and OS keyring. [A1] [B11] |
| Local automation | Companion server, authorization/revocation | HTTP/WS controls, metadata/artwork, navigation/queue, pairing/revocation | LUNE-383, opt-in loopback only, separate read/control scopes. [A1] [B12] [B21] |
| OBS | Possible through companion clients | First-party overlay layouts and preview | LUNE-384 after API. [B13] |
| Stream Deck | Possible through companion clients | First-party paired hardware plugin | LUNE-385 after API; physical-device verification separate. [B14] |
| Artwork and performance | Wrapper image/loading behavior | Shared thumbnail cache, art-derived colors, lower background CPU, auto-closing toasts | LUNE-369 resolution-aware cache; bounded work and feedback across tickets. [B2] [B15] |
| Updates/diagnostics | Update UI; current source auto-updates Windows | Channels, progress/release notes, logs, optional crash reporting | LUNE-386 respects package-manager ownership; local redacted diagnostics, no hosted telemetry. [A3] [B16] |
| Video quality | Embedded service playback | Preferred resolution up to 4K | Excluded: native client remains audio-only. [B2] |
| Casting | Not established in current feature list | Experimental Chromecast/mDNS | LUNE-388 feasibility report only; no casting implementation implied. [B2] |
| Mobile remote | Companion ecosystem | QR pairing explicitly coming soon | Excluded from parity delivery; do not represent a planned upstream feature as shipped. [B17] |

No verified current reference establishes ad blocking, SponsorBlock, equalizer, crossfade or offline music downloads as additions from these two exact projects. Existing native downloads remain required, independently of this comparison. Both repositories expose licenses ([YTMDesktop GPL-3.0](https://github.com/ytmdesktop/ytmdesktop/blob/development/LICENSE), [YTMDesktop2 CC0-1.0](https://github.com/Venipa/ytmdesktop2/blob/master/LICENSE)); retain native implementations and review any proposed code reuse separately.

## Approved player and visual contracts

### Theme and geometry — LUNE-368

Keep all twelve current presets, custom themes and the version-1 import/export format. The existing Classic default and each user's selected theme remain intact. Replace the hardcoded purple unfilled seek/volume track with one derived progressTrack role; filled progress and thumb use the active accent. Derive by blending surface toward primary foreground, starting at 35% foreground and increasing by one percentage point until track-to-surface contrast reaches at least 3:1. Use the black/white direction with adequate contrast if a custom palette cannot reach the target. This is a runtime role, not a persisted theme-schema addition.

Expected values for unchanged built-in palettes:

| Theme | Neutral progressTrack |
| --- | --- |
| Classic | #6F6F6F |
| Classic Light | #909090 |
| Midnight Violet | #6C6B74 |
| Catppuccin Mocha | #777C93 |
| Dracula | #808289 |
| Nord | #898E99 |
| Gruvbox Dark | #8B816E |
| Solarized Dark | #647F7F |
| Tokyo Night | #6A718F |
| Rosé Pine | #706E84 |
| Solarized Light | #718886 |
| Catppuccin Latte | #808397 |

Navigation selected/hover/focus backgrounds and the active marker must share explicit item bounds and insets. The selected state follows the current route. Align icons, labels, rounded backgrounds and marker at supported sidebar widths; distinguish hover from selection. Reuse shared spacing, text and focus roles across player, menus and docks.

### Artwork — LUNE-369

Preserve provider variants and their dimensions through normalized catalog items, queues and downloaded metadata. Pick the smallest adequate physical resolution for rendered size times DPR; fall back to the largest available image. Use known album/song IDs for metadata enrichment. Large player artwork must use large originals rather than stretching a small card cache.

Existing smaller local images remain the immediate/offline fallback. Upgrade them online asynchronously and finalize atomically without downloading audio again. Never replace better art with a lower-quality or stale-track response. Retain bounded cache behavior and durable downloaded artwork. Validate 60, 300 and 1200 pixel variants, multiple DPRs and offline fallback.

### Independent docks — LUNE-370

Queue and Lyrics have separate player-bar toggles and close buttons. Persist requested open states and user-resized widths. The left-to-right order is browsing content, Lyrics, Queue; Lyrics occupies the far right when Queue is closed. Keep the bottom player visible and retain route, scroll and playback state through toggles.

Both docks require at least 480 logical pixels for central content and 280 for each dock after navigation and effective UI scale are accounted for. If that cannot fit, show one dock with Queue/Lyrics tabs and the most recently activated tab. Retain both requested states and widths so side-by-side presentation returns when space permits. No competing nested outer scrollbars. Load/follow lyrics according to the visible dock or immersive lyric surface, not an obsolete full-page route.

### Queue — LUNE-371

Pin Now playing above a single virtualized scrolling list. Inside that list show Queued songs (manual entries), a 48–56 pixel queue drop target, then Next from [source] or Next up. Manual entries take their natural list space; remove the fixed height cap and inner scrolling region. Align section headers, artwork, title/artist/album, duration, drag target and action controls using the shared spacing system.

Do not render Previously played anywhere in the queue. Preserve history storage, snapshot migration, Previous behavior, consumed-manual semantics, shuffle/repeat, duplicate entry keys and local-first playback. Preserve source-to-manual drag, reorder within pending groups, keyboard equivalents, deletion and clear-queue cancellation of pending additions. This is a view restructuring, not a new playback algorithm.

### Lyrics — LUNE-372/374

Share one lyric component between dock and immersive player. Active timed lines and plain lyrics use primary foreground; surrounding timed lines use readable secondary foreground. Use real cue timestamps for click, Enter or Space seeking; plain lyrics are not seek targets. Center the current line on opening, seeking, resizing and resuming follow.

Wheel/trackpad, scrollbar drag and keyboard scrolling suspend follow for six seconds after the last manual interaction. Show a Follow lyrics action that resumes immediately. Follow resumes automatically after the timeout. Keep focus and deliberate user scrolling stable; honor reduced motion. Provide compact source/sync labels, loading, plain-only, offline, unavailable and retry states; reject responses for stale tracks.

External providers are disabled until opted in. Default lookup priority is native timed lyrics, LRCLIB, Unison, Better Lyrics, with native plain lyrics as fallback; allow provider reorder/toggle. Use human YouTube captions only when available. Approximate matches default off. Word/syllable effects require genuine supplied timing; never synthesize word timing from a line duration. Optional timestamps, display styles and auto-open must be explicit settings, not automatic new defaults.

Keep network/parsing off the GUI thread, cache available results for offline use and keep API keys in the OS keyring. Better Lyrics currently requires an unavailable-to-new-users API key for uncached songs; failure must fall through to other providers. Fixture success proves parser/UI behavior only; report actual provider coverage separately.

### Immersive player — LUNE-373

The far-right player button and existing F shortcut toggle an immersive stage within the application window. Do not invoke OS fullscreen. Hide browsing navigation while showing large sharp artwork, track title, artist/album links, the persistent bottom transport and shared optional docks. Keep a single playback instance. Escape restores the previous browsing route, scroll position and focus. Local shortcut guards continue to protect typing and modal interaction.

## Subsequent QoL delivery and defaults

| Area | Required behavior and default |
| --- | --- |
| Listening (LUNE-375) | Sleep timer presets 5/10/15/30/45/60 minutes, visible status/cancel and pause at expiration. Nonlinear volume and transition-time skip-disliked default off; skipping must terminate safely when no eligible track remains. Add timestamp seek preview and convenient library/playlist actions through existing commands. |
| Appearance (LUNE-376) | Content scale 80–150% in 5% steps, default 100%, independent of OS DPR. Recompute dock fit. Persist optional artwork background/blur and reduced-motion settings; restore windows within connected displays. |
| Tray (LUNE-377) | Optional pinnable/movable popup with metadata, art, transport, ratings, seek, volume and expandable queue, backed by the same player. Clamp position to available displays and keep main-window access when tray capability is unavailable. |
| Lifecycle (LUNE-378) | Autostart, minimized startup, close-to-tray and track notifications opt-in. Close exits by default; session restoration stays paused. Errors persist until actionable resolution; successful actions use transient feedback. |
| Global shortcuts (LUNE-379) | Disabled until enabled. Support transport, seek, volume, ratings, shuffle/repeat; detect duplicate/reserved/unavailable bindings, clear/reset. Use platform adapters, Wayland portal capability feedback and existing MPRIS fallback. |
| Discord (LUNE-380) | Off by default; public track metadata, playback state and optional buttons. Bounded reconnect and idle behavior; missing Discord never blocks playback. |
| Last.fm (LUNE-381) | Off by default; authorization/logout/re-auth with keyring credentials. Account for actual listening time, configurable threshold, seeks/skips/long pauses/offline state, repeat-one and deduplication. Do not reuse the YouTube listening-history threshold. |
| Deep links (LUNE-382) | App-specific registered protocol, validated YouTube song/playlist/artist URLs, cold/warm-start handling and Open/Play/Queue preview by default. Optional browser handoff has per-host control. One playback instance; no arbitrary commands. |
| API (LUNE-383) | Off by default; loopback only. Explicit pairing/revocation, read-only overlay scope separate from playback-control scope, bounded input and origin handling. Expose normalized metadata/artwork/state and existing playback/navigation/queue commands with event updates. Never expose session headers, cookies or signed media URLs. |
| OBS (LUNE-384) | API-dependent read-only tokens; full/compact/text/badge/poster/ticker/display layouts; artwork/title/artist/progress/transparency/scale, preview/copy URL and revoke. Handle idle, pause and disconnection. |
| Stream Deck (LUNE-385) | Paired API client for transport/ratings/shuffle/repeat/volume/track information; reconnect and revoke. Package for supported Windows/macOS hosts; label real hardware verification separately. |
| Maintenance (LUNE-386) | Release status and local redacted diagnostic export. Arch updates remain owned by the package manager. No hosted telemetry. Preserve settings/downloads and separate native/wrapper releases. |
| Speaker fill (LUNE-387) | Verify libmpv capability first; optional and disabled by default, exposed only where supported. Preserve normal output/channel/device recovery; distinguish synthetic mapping from real audio verification. |
| Chromecast (LUNE-388) | Feasibility report only: native audio, discovery, authenticated and local-file playback, control/security/platform/dependency constraints, measurable go/no-go. A later decision is required before full implementation. |

Desktop integration additions must have no background network or active service work while disabled. Use Qt standard paths/settings and isolated platform adapters; reuse OS credential storage. Do not add the reference apps' custom CSS injection, embedded-web CPU patches or adjacent key-file encryption to native rendering. Blur must remain optional and bounded, with a software-rendering fallback.

## Interfaces and compatibility

Extend the existing theme controller with a derived progressTrack property; preserve theme format version 1. Extend shell state with independent dock intent/widths, active compact-dock tab and immersive state. UI state changes must not replace catalog navigation or playback ownership.

Keep queue/history snapshot version 2 unless a ticket demonstrates a necessary migration. Build a virtualized queue display projection from existing stable entry keys rather than deleting history or mutating source ordering to hide it. Keep one transport/prefetch/MPRIS next-entry authority.

Carry artwork candidates/dimensions and best local resolution alongside existing thumbnail fields, tolerating older cache/download records. Lyric results distinguish plain, line-timed and word/syllable-timed data, provenance and track identity. Optional providers and integrations use worker/service boundaries and the same playback commands; they do not expose raw provider sessions to QML or external clients.

No hosted backend is required. The later authenticated loopback API is an explicit addition to the initial no-HTTP design, and it is unavailable while disabled. Existing Tauri code, native package identity, durable downloads and audio-only playback remain intact.

## Linear tickets and dependency order

These are actual assigned issues. Blocking relations below were read from Linear after creation. Foundation documents the shared contract; the table records functional dependencies for theme/artwork, docks, queue/lyrics, immersive playback and later integrations. Each issue is delivered through its own branch and PR in the user-approved stack described below.

| Issue | Assigned title | Blocked by |
| --- | --- | --- |
| [LUNE-367](https://linear.app/nouvelle-lune-atelier/issue/LUNE-367/publish-native-qol-roadmap-and-revised-player-specification) | Publish native QoL roadmap and revised player specification | — |
| [LUNE-368](https://linear.app/nouvelle-lune-atelier/issue/LUNE-368/unify-theme-aware-progress-tracks-and-navigation-alignment) | Unify theme-aware progress tracks and navigation alignment | — |
| [LUNE-369](https://linear.app/nouvelle-lune-atelier/issue/LUNE-369/preserve-resolution-aware-artwork-and-upgrade-offline-covers) | Preserve resolution-aware artwork and upgrade offline covers | — |
| [LUNE-370](https://linear.app/nouvelle-lune-atelier/issue/LUNE-370/add-independent-responsive-lyrics-and-queue-docks) | Add independent responsive Lyrics and Queue docks | LUNE-368 |
| [LUNE-371](https://linear.app/nouvelle-lune-atelier/issue/LUNE-371/unify-queue-scrolling-while-retaining-playback-history) | Unify queue scrolling while retaining playback history | LUNE-370 |
| [LUNE-372](https://linear.app/nouvelle-lune-atelier/issue/LUNE-372/make-lyric-panels-readable-and-reliably-follow-playback) | Make lyric panels readable and reliably follow playback | LUNE-370 |
| [LUNE-373](https://linear.app/nouvelle-lune-atelier/issue/LUNE-373/build-artwork-led-immersive-player-inside-the-app-window) | Build artwork-led immersive player inside the app window | LUNE-371, LUNE-368, LUNE-372, LUNE-369 |
| [LUNE-374](https://linear.app/nouvelle-lune-atelier/issue/LUNE-374/add-optional-timed-lyric-providers-and-genuine-timing-styles) | Add optional timed lyric providers and genuine timing styles | LUNE-372 |
| [LUNE-375](https://linear.app/nouvelle-lune-atelier/issue/LUNE-375/add-sleep-timer-and-everyday-playback-conveniences) | Add sleep timer and everyday playback conveniences | LUNE-373 |
| [LUNE-376](https://linear.app/nouvelle-lune-atelier/issue/LUNE-376/add-content-scaling-and-reduced-motion-appearance-options) | Add content scaling and reduced-motion appearance options | LUNE-373 |
| [LUNE-377](https://linear.app/nouvelle-lune-atelier/issue/LUNE-377/add-pinnable-tray-player-backed-by-native-playback) | Add pinnable tray player backed by native playback | LUNE-373 |
| [LUNE-378](https://linear.app/nouvelle-lune-atelier/issue/LUNE-378/add-desktop-startup-behavior-and-track-notifications) | Add desktop startup behavior and track notifications | LUNE-377 |
| [LUNE-379](https://linear.app/nouvelle-lune-atelier/issue/LUNE-379/add-configurable-global-media-shortcuts) | Add configurable global media shortcuts | LUNE-377 |
| [LUNE-380](https://linear.app/nouvelle-lune-atelier/issue/LUNE-380/add-optional-discord-listening-presence) | Add optional Discord listening presence | LUNE-373 |
| [LUNE-381](https://linear.app/nouvelle-lune-atelier/issue/LUNE-381/add-optional-lastfm-now-playing-and-scrobbling) | Add optional Last.fm Now Playing and scrobbling | LUNE-373 |
| [LUNE-382](https://linear.app/nouvelle-lune-atelier/issue/LUNE-382/add-native-music-deep-links-and-optional-browser-handoff) | Add native music deep links and optional browser handoff | LUNE-373 |
| [LUNE-383](https://linear.app/nouvelle-lune-atelier/issue/LUNE-383/add-authenticated-loopback-playback-api) | Add authenticated loopback playback API | LUNE-373 |
| [LUNE-384](https://linear.app/nouvelle-lune-atelier/issue/LUNE-384/add-local-obs-now-playing-overlays-and-preview) | Add local OBS now-playing overlays and preview | LUNE-383 |
| [LUNE-385](https://linear.app/nouvelle-lune-atelier/issue/LUNE-385/add-paired-stream-deck-playback-integration) | Add paired Stream Deck playback integration | LUNE-383 |
| [LUNE-386](https://linear.app/nouvelle-lune-atelier/issue/LUNE-386/add-release-status-and-redacted-native-diagnostics) | Add release status and redacted native diagnostics | LUNE-373 |
| [LUNE-387](https://linear.app/nouvelle-lune-atelier/issue/LUNE-387/evaluate-and-add-optional-native-speaker-fill) | Evaluate and add optional native speaker fill | LUNE-375 |
| [LUNE-388](https://linear.app/nouvelle-lune-atelier/issue/LUNE-388/evaluate-native-chromecast-audio-compatibility) | Evaluate native Chromecast audio compatibility | LUNE-373 |

On 2026-10-22 the user explicitly requested stacked GitHub PRs for LUNE-367–LUNE-388 and no merges until user verification. This is a scoped exception to the repository's usual direct-from-main, main-target-only and no-unmerged-stacking rules. LUNE-367 is based on and targets main. Each later ticket branch builds on the preceding ticket branch in the rollout stack, and its PR targets that branch. Functional prerequisites must already be present in the stack; they do not need to merge before dependent work begins.

Keep branch names exactly LUNE-NNN and commit subjects LUNE-NNN - Change-specific message. Do not merge any rollout PR until the user has verified the changes and authorizes merging. Review concerns must still be resolved and required checks must pass for the current head before an authorized merge. Do not push implementation changes directly to main. The default repository workflow continues to apply outside this rollout.

## Acceptance matrix

| Area | Required checks |
| --- | --- |
| Theme/navigation | All twelve expected neutral tracks; >=3:1 track/surface contrast; extreme custom colors and import/export compatibility; route/hover/focus alignment at supported sidebar widths. |
| Layout | 1600×900, 1280×820 and 920×620; closed/Queue/Lyrics/both docks; resize across the 480+280+280 content threshold; saved widths and requested states; persistent player; UI scales 80/100/150% and multiple DPRs. |
| Queue | Empty/manual-only/source-only/mixed/long/duplicate data; no visible history; pinned current entry; one scrollbar; source-to-manual drag, keyboard reorder, delete, clear/cancellation and Previous/repeat/shuffle/snapshot regressions. |
| Lyrics | Plain/line/word timing, missing/error/offline; click and keyboard seeking; current-line centering on open/resize/seek; each manual scroll input pauses six seconds; Follow action; reduced motion; stale result rejection and provider fallback. |
| Immersive/artwork | In-window transition and Escape restore route/scroll/focus; one player; 60/300/1200 pixel candidates, DPR, local fallback, atomic online upgrade without audio redownload, stale/lower-quality prevention; GPU and software rendering. |
| Listening/lifecycle | Timer cancel/expiry; volume mapping; skip-disliked exhaustion; paused restoration; tray unavailable/removed; login/close/minimized behavior opt-in; window placement on changed displays. |
| Integration/privacy | Disabled idle behavior; failed service cannot block playback; keyring access; API auth, scopes, revocation, origins and bounded input; malformed links; no credentials/session/signed media data in logs, exports or fixtures. |
| Existing behavior | Downloaded audio bypasses resolver/audio network online and after offline restart with expired credentials; catalog/library/playlist mutations, duplicate tracks, queue semantics, durable downloads and Tauri wrapper remain intact. |
| Release evidence | Targeted regression tests and required native CI for each code ticket; applicable synthetic visual checks and existing performance budgets. Record real-account, KDE/Wayland, Windows/macOS, tray, audio and Stream Deck hardware coverage separately. |

Use sanitized fixtures, generated/local licensed audio and synthetic screenshots in committed checks. Private account screenshots stay outside commits, logs and tickets. Documentation-only LUNE-367 is checked for diff cleanliness, source/issue link consistency and contradictions; it does not claim new runtime verification.

## Primary sources

[A1]: https://github.com/ytmdesktop/ytmdesktop/blob/development/src/renderer/windows/settings/Settings.vue
[A2]: https://github.com/ytmdesktop/ytmdesktop/blob/development/src/renderer/ytmview/scripts/playerbarcontrols.script.js
[A3]: https://github.com/ytmdesktop/ytmdesktop/blob/development/src/main/index.ts
[A4]: https://github.com/ytmdesktop/ytmdesktop/releases
[B1]: https://youtube-music.app/docs/features/tray-view/
[B2]: https://youtube-music.app/docs/features/ui-enhancements/
[B3]: https://youtube-music.app/docs/features/themes/
[B4]: https://youtube-music.app/docs/features/display/
[B5]: https://youtube-music.app/docs/features/shortcuts/
[B6]: https://github.com/Venipa/ytmdesktop2/blob/master/apps/ytmdesktop2/src/main/trpc/routers/mediaControl/service.ts
[B7]: https://github.com/Venipa/ytmdesktop2/blob/master/apps/ytmdesktop2/src/renderer/src/components/trayview/tray-queue-list.tsx
[B8]: https://youtube-music.app/docs/features/lyrics/
[B9]: https://youtube-music.app/docs/features/shared-links/
[B10]: https://youtube-music.app/docs/features/discord/
[B11]: https://youtube-music.app/docs/features/lastfm/
[B12]: https://youtube-music.app/docs/api/routes/
[B13]: https://youtube-music.app/docs/features/obs/
[B14]: https://youtube-music.app/docs/integrations/streamdeck/
[B15]: https://youtube-music.app/docs/internals/thumbnail-cache/
[B16]: https://github.com/Venipa/ytmdesktop2/blob/master/apps/ytmdesktop2/src/renderer/src/routes/_settings/about.tsx
[B17]: https://youtube-music.app/docs/integrations/remote/
[B18]: https://github.com/Venipa/ytmdesktop2/blob/master/apps/ytmdesktop2/src/main/trpc/routers/touchbar/service.ts
[B19]: https://github.com/Venipa/ytmdesktop2/blob/master/apps/ytmdesktop2/src/renderer/src/routes/_settings/index.tsx
[B20]: https://youtube-music.app/docs/features/userscript/
[B21]: https://youtube-music.app/docs/api/authentication/
