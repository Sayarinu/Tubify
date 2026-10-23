# Native music links and browser handoff

The native app recognizes `ytmusic-native://open?url=<encoded HTTPS YouTube URL>` and the explicit `play` and `queue` actions. Raw supported HTTPS links and `open` show a preview without changing playback. Song and collection previews offer Play and Add to queue; artist links open their page to choose music. `watch?v=…&list=…` refers to the selected song; use `/playlist?list=…` for the collection. Tracking parameters are discarded. Native links do not accept file paths, executable commands, arbitrary domains or other protocols.

From a source checkout:

```sh
PYTHONPATH=native/src python -m youtube_music_native.app 'https://music.youtube.com/watch?v=abcdefghijk'
```

Use a real song ID when trying an account. A second launch with the same data directory forwards links to the existing window. The handoff uses a same-user local socket, a private random token and a process lock; it never creates a second player. macOS URL-open events use the same validator and preview flow.

## Optional browser userscript

Install `browser-handoff.user.js` in a userscript manager. In the manager menu, choose **Toggle native handoff on [host]** separately for each desired host. Every host starts disabled. Supported music pages then offer explicit Open in Native, Play and Queue links. Nothing redirects automatically, intercepts normal browsing or reads your account credentials. The native app must be installed with protocol registration. Removing the userscript removes browser integration.

## Protocol registration

The Arch package installs `x-scheme-handler/ytmusic-native` in its desktop entry, with `youtube-music-native -- %u`. Desktop environments update their MIME cache through normal package hooks. Users may choose the handler in their desktop's preferred-application settings. This change does not modify the Tauri package's association.

Windows and macOS package association belongs to the existing LUNE-351/LUNE-352 ports. Their installer requirements are:

- Windows: register `HKCU\Software\Classes\ytmusic-native` with `URL Protocol` and a quoted `shell\open\command` of `"<installed executable>" -- "%1"`; remove the app-owned keys on uninstall. Do not interpolate URLs into a shell command.
- macOS: add a `CFBundleURLTypes` entry with `CFBundleURLSchemes = [ytmusic-native]` to the native app bundle's `Info.plist`. `QFileOpenEvent` forwards cold/warm URL events through the same app handler. The current repository has no native Windows installer or macOS app bundle to amend.

References: [Qt file-open events](https://doc.qt.io/qt-6/qfileopenevent.html), [Qt local socket permissions](https://doc.qt.io/qt-6/qlocalserver.html), [Qt process locks](https://doc.qt.io/qt-6/qlockfile.html), [desktop Exec fields](https://specifications.freedesktop.org/desktop-entry/latest/exec-variables.html), [Windows application registration](https://learn.microsoft.com/en-us/windows/win32/shell/app-registration), [Apple URL type keys](https://developer.apple.com/library/archive/documentation/General/Reference/InfoPlistKeyReference/Articles/CoreFoundationKeys.html).

Open one URL per launch or handoff. Multiple URLs are rejected so an earlier Play or Queue action cannot be silently replaced by a later URL in the same launch.
