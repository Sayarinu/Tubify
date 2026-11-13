<div align="center">

<img src="native/src/tubify/assets/music.svg" alt="Tubify" width="96" height="96">

# Tubify

**A fast desktop app for YouTube Music.**

Your library, playlists and recommendations in a real desktop app with offline downloads, synced lyrics, music videos and full media-key support, without a browser tab.

[![Latest release](https://img.shields.io/github/v/release/Sayarinu/Tubify?label=stable&display_name=release)](https://github.com/Sayarinu/Tubify/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/Sayarinu/Tubify/total)](https://github.com/Sayarinu/Tubify/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
![Platforms](https://img.shields.io/badge/platforms-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)

[**Download**](#download) · [Features](#features) · [Guide](https://github.com/Sayarinu/Tubify/wiki) · [FAQ](#faq)

</div>

---

## Features

- **Browse** Home, Explore, charts, and moods and genres.
- **Search** songs, videos, artists, albums and playlists.
- **Music videos** in the full-screen player.
- **Endless radio** that carries on after a playlist or album ends.
- **Queue** with play next, reordering, shuffle, repeat and history.
- **Synced lyrics**, in a side panel or full screen.
- **Your library**: playlists, likes, albums, artists and history, with editing and sorting.
- **Offline downloads**, optionally saved as tagged audio files.
- **Local Music** from folders on your computer.
- **Media keys**, system now-playing controls and global shortcuts.
- **Mini player** in the system tray.
- **Sleep timer** and audio options.
- **Themes**, including a custom theme editor.
- **Discord** and **Last.fm** connections.
- **Automatic updates**, with an optional Experimental channel.

## Download

Get the latest version from the **[Releases page](https://github.com/Sayarinu/Tubify/releases/latest)**.

| System | File |
|---|---|
| **Windows** 10 or 11, 64-bit | `Tubify-<version>-windows-x64-setup.exe` |
| **macOS** 12 or later, Apple silicon | `Tubify-<version>-macos-arm64.dmg` |
| **Linux** x86_64 with pacman | `Tubify-<version>-linux-x86_64.pkg.tar.zst` |

Then open Tubify and choose **Sign in via Browser**. It reuses your YouTube Music sign-in from your browser, so you never type your password into Tubify.

Install steps, first-launch warnings and sign-in tips for each system are in the **[guide](https://github.com/Sayarinu/Tubify/wiki/Installing-Tubify)**.

## FAQ

**Do I need YouTube Music Premium?**
No. Tubify works with any Google account that can use YouTube Music.

**Is my account safe?**
Tubify reuses your browser's existing sign-in and keeps the session in your system's secure storage: Windows Credential Manager, the macOS Keychain or your Linux keyring. Your music data goes to YouTube. To find synced lyrics, the title, artist, album, duration and video ID of songs whose lyrics you open also go to LRCLIB, Unison and Better Lyrics by default; you can turn this off in Settings. Discord and Last.fm receive music data only if you turn them on. Diagnostics are saved locally and never uploaded.

**Something doesn't look right. What can I do?**
Settings → Troubleshooting can save a privacy-safe diagnostics report. Please include it when you [open an issue](https://github.com/Sayarinu/Tubify/issues).

**Can I build it myself?**
Yes. See [Building from Source](https://github.com/Sayarinu/Tubify/wiki/Building-from-Source).

## Contributing

Bug reports, ideas and pull requests are welcome. Please open an [issue](https://github.com/Sayarinu/Tubify/issues) first for larger changes. Development setup is in the [guide](https://github.com/Sayarinu/Tubify/wiki/Building-from-Source).

## License

Tubify is free and open-source software under the [MIT License](LICENSE).

Tubify releases also include third-party components, such as Qt, mpv, FFmpeg and yt-dlp, each under its own license. Some, like the bundled mpv and FFmpeg builds, are GPL. See [Third-party notices](native/src/tubify/assets/THIRD_PARTY_NOTICES.md); the app also shows these under **Settings → Updates → Open-Source Licenses**.

## Disclaimer

Tubify is an independent, unofficial project. It is not affiliated with, endorsed by or sponsored by Google LLC or YouTube. YouTube and YouTube Music are trademarks of Google LLC. Please use Tubify in line with YouTube's Terms of Service.
