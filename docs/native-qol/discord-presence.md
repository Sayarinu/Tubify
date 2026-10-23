# LUNE-380 — Optional Discord presence

Enable **Discord presence** from Settings, create a Discord application, and save its public numeric Application ID. No bot token or Discord password is needed. Presence and the optional public YouTube Music button default off. Pause, disable and exit clear the activity; missing Discord never blocks audio.

The Qt local socket client searches standard Discord IPC endpoints, including the Flatpak runtime directory. It uses nonblocking framed JSON, bounded frames and deadlines, latest-state coalescing, a 15-second update interval and at most five automatic connection attempts before explicit Retry. Only song title, artist, playback timestamps and an optional validated public watch link leave the app. Artwork URLs, local file paths, account data and signed sources are excluded. Fixture mode never connects.

## Verification

- Seven focused protocol/controller tests, including a real synthetic local socket server: fragmented frames, handshake, ACK/coalescing, ping, oversized/deeply nested input, stalled endpoint fallback, pause/disable and retry limits.
- Native suite passed (208 tests before the additional malformed-frame regression); full Qt/libmpv runtime suite passed.
- Real QML dialog smoke at 920×620: explicit opt-in, Application ID, status and text-entry shortcut isolation.
- A live Discord account/client presence has not been verified. User-owned Application ID and desktop-client availability remain runtime prerequisites; platform IPC paths are covered synthetically.

Primary protocol references: [Discord RPC documentation](https://github.com/discord/discord-api-docs/blob/main/developers/topics/rpc.mdx), [official IPC framing reference](https://github.com/discord/discord-rpc/blob/master/documentation/hard-mode.md), [finding an Application ID](https://support-dev.discord.com/hc/en-us/articles/360028717192-Where-can-I-find-my-Application-Team-Server-ID).
