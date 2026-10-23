# LUNE-382 — native music links

The app recognizes its own `ytmusic-native` protocol and supported HTTPS YouTube song, playlist, artist and album links. Raw links open a preview. Only an explicit native `play`/`queue` action or an in-app button changes playback or queue state. Artist links open the artist page. Shared links retain validated IDs only; unknown domains, credentials, ports, nested schemes, file paths, command-like values and malformed/oversized requests are rejected.

The preview resolves downloaded metadata first, then the existing catalog worker, and handles stale replies and offline errors. Duplicate OS/browser deliveries within two seconds do not repeat an action. Existing browse/player/queue commands perform every action. The one-instance handoff uses a long-lived process lock and bounded local socket protocol with a private random token. A second launch forwards to the existing instance before constructing any player. macOS FileOpen events use this same preview path.

Arch registration is included in the native desktop entry and validated with `desktop-file-validate`. The package also installs the optional browser userscript. Each browser host starts disabled; the userscript manager menu enables explicit handoff links for that host. No navigation is intercepted or automatically redirected. Windows/macOS bundle association requirements remain with the existing platform port tickets, which currently have no native installer/bundle files in this repository.

## Verification

Synthetic tests cover accepted link shapes, default preview, explicit actions, malformed/duplicate URLs, stale replies, offline downloaded resolution, retry behavior, artist capability limits, actual secondary-process forwarding, startup deferral, wrong IPC token/oversized messages, package fields and userscript opt-in. Qt smoke covers cold startup with a link, unchanged playback on preview, explicit Queue/Play/Open, invalid links and 1600×900, 1280×820 and 920×620 layouts. The userscript passes `node --check` and a fake-DOM behavior check when Node.js is available.

Real desktop association launching, browser userscript-manager installation and account-backed shared links remain user/platform verification. No real-account content or private screenshots are in these tests. See [integration setup](../integrations/README.md) for usage and primary protocol/platform references.
