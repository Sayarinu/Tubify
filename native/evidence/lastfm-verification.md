# LUNE-381 — optional Last.fm delivery

Last.fm is disabled initially. The app uses a separate provider worker, started only for an explicit settings action or an enabled connection. Playback never waits for Last.fm. Disabled listening stops the sampling/retry timers and closes that worker.

## User flow

Open Settings → Last.fm. Supply a Last.fm API key and shared secret, save them to the system keyring, choose Sign in, approve access in the browser, then choose Complete sign-in. Enable listening updates separately. Sign in again replaces an expired session. Sign out disables updates, removes app/session/token credentials from the keyring and clears queued listens. No Last.fm application credentials are bundled with this build.

## Listening and delivery

The service samples playback progress against monotonic elapsed time. Seeks, buffering, pauses and long gaps do not add listening time. Tracks of 30 seconds or less are excluded. Default qualification is 50% of a song or four minutes, whichever comes first; users can increase the percentage to 100%. Repeat-one starts another listen, while source/device recovery at a nonzero position retains the existing listen. Long-pause resumption refreshes Now Playing without a second scrobble for that listen.

Each qualified listen has a unique local identity and the original start timestamp. A bounded, account-scoped atomic JSON spool retains unacknowledged listens through immediate shutdown and restart; its single disk writer drains on exit without waiting for the network. Only public scrobble metadata goes into the spool. SQLite retains at most 1,000 unsubmitted listens, oldest first for delivery, and 1,000 completed identities to suppress local duplicate submissions; completed metadata is removed. Account changes and logout clear old pending data. Transient failures retain the same identity/timestamp for retry. Last.fm exposes no client idempotency-key parameter, so a lost response after remote acceptance cannot establish exactly-once delivery; retries preserve the identical recording and start timestamp. Failed Now Playing requests are not automatically retried.

Only artist, track, album, duration and start time reach Last.fm. No YouTube session, video URL, signed audio URL or download path is sent. API errors are mapped to fixed messages rather than logging response bodies or credentials. Credentials, pending approval tokens and session keys stay in the OS keyring; the browser receives only the documented approval URL.

## Verification

The current parent plus this patch passes 339 native pytest checks, including 29 Last.fm checks, and the complete Qt/runtime smoke suite. Synthetic checks cover desktop token/session auth, form POST signatures, non-200 protocol errors, safe messages, invalid credentials and repair, offline restart/retry/order, queue bounds, invalid sessions and reauthentication, account changes, duplicate acknowledgement, all listening-time exclusions, repeat behavior and percentage thresholds. Qt smoke exercises the settings dialog at 1600×900, 1280×820 and 920×620 with 80%, 100% and 150% content scaling, focus visibility after resizing, opt-in controls, secret-field clearing and shortcut isolation. No real account was authorized and no live scrobble was submitted during verification. Real browser approval, OS keyring persistence and profile delivery remain an explicit user-account check.

## Primary references

- [Desktop authentication](https://www.last.fm/api/desktopauth)
- [Scrobbling protocol and retry handling](https://www.last.fm/api/scrobbling)
- [track.scrobble parameters](https://www.last.fm/api/show/track.scrobble)
- [track.updateNowPlaying parameters](https://www.last.fm/api/show/track.updateNowPlaying)
