Native Python/PySide6 and QML client for Arch Linux x86_64 with audio-only playback, Home/Explore/search, library and playlist management, queue/lyrics, durable downloads and KDE media controls.

Download the `youtube-music-native-*.pkg.tar.zst` file and `SHA256SUMS`, verify with `sha256sum --ignore-missing -c SHA256SUMS`, then install with `sudo pacman -U ./youtube-music-native-*.pkg.tar.zst`. Arch supplies Qt, libmpv, FFmpeg, Deno and provider dependencies. The source package is included for rebuilding.

The native package installs alongside `youtube-music-app`, uses separate application data and retains downloads across upgrades. Connect through the profile button using the existing Tauri session or a local browser-session export. Credentials remain in the OS keyring.

Actual hardware sleep/wake verification was deferred by the user. Windows and macOS packages remain later milestones; shared code receives early CI checks on both platforms.
