<div align="center">

<img src="native/src/youtube_music_native/assets/music.svg" alt="Tubify" width="96" height="96">

# Tubify

**A fast desktop app for YouTube Music.**

Your library, playlists and recommendations in a real desktop app with offline downloads, synced lyrics, music videos and full media-key support, without a browser tab.

[![Latest release](https://img.shields.io/github/v/release/Sayarinu/Tubify?label=release&sort=semver)](https://github.com/Sayarinu/Tubify/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/Sayarinu/Tubify/total)](https://github.com/Sayarinu/Tubify/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
![Platforms](https://img.shields.io/badge/platforms-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)

[**Download**](#download) · [Features](#features) · [Getting started](#getting-started) · [FAQ](#faq)

</div>

---

## Features

### Listening
- **Home, Explore, charts, and moods & genres**, with a consistent home layout that doesn't reshuffle every visit.
- **Search** with a top result, songs, videos, artists, albums and playlists, each in its own section.
- **Music videos** play right in the full-screen player, with a Song/Video switch.
- **Radio that keeps going.** When a playlist, album or artist finishes, Tubify continues with a matching radio and skips songs you've already heard.
- **A queue that makes sense.** Play next, add to queue, drag to reorder, shuffle, repeat, and a history of what you played.
- **Synced lyrics** in a side panel or full screen, from LRCLIB, Unison and Better Lyrics, with line, word or syllable highlighting.

### Your library
- Playlists, songs, albums, artists, subscriptions, liked songs and listening history.
- Create, rename and edit playlists; like and dislike songs; save albums and follow artists.
- **Sort any playlist or album** by title, artist, album or length.

### Offline
- **Download** songs, albums and playlists to listen without a connection.
- Downloads play first automatically, even when you're signed out or offline.

### Made for the desktop
- **Media keys** and the system now-playing controls on Windows, macOS and Linux (MPRIS).
- **Global keyboard shortcuts**, a mini player in the system tray, launch at login, and recovery after sleep.
- **Sleep timer**, a natural volume curve, stereo-to-surround speaker fill, and an option to skip disliked songs.

### Look and feel
- 12 built-in themes (including Catppuccin, Dracula, Nord, Gruvbox, Tokyo Night, Rosé Pine and Solarized), plus a custom theme editor with import and export.
- An artwork-led full-screen player, smooth transitions, adjustable interface scale and a Reduce Motion option.

### Connections
- **Discord** Rich Presence and **Last.fm** scrobbling.

### Always up to date
- Tubify checks for new releases and shows an **update icon** in the top right when one is ready. One click installs it and relaunches the app, keeping your settings, queue and downloads.

## Download

Get the latest version from the **[Releases page](https://github.com/Sayarinu/Tubify/releases/latest)**.

| Platform | File | Requirements |
|---|---|---|
| **Windows** | `Tubify-<version>-windows-x64-setup.exe` | Windows 10 or 11, 64-bit |
| **macOS** | `Tubify-<version>-macos-arm64.dmg` | macOS 12 or later, Apple silicon |
| **Linux** | `Tubify-<version>-linux-x86_64.pkg.tar.zst` | x86_64 Linux with pacman |

<details>
<summary><b>Windows</b></summary>

Run the installer. It installs for your user account only, without administrator rights, and adds Tubify to the Start menu. If Windows SmartScreen warns about an unrecognized app, choose **More info → Run anyway**.

</details>

<details>
<summary><b>macOS</b></summary>

Open the disk image and drag **Tubify** to **Applications**. Tubify isn't notarized by Apple yet, so the first time you open it, Control-click the app, choose **Open**, then confirm. Alternatively, open it from **System Settings → Privacy & Security → Open Anyway**.

</details>

<details>
<summary><b>Linux</b></summary>

```sh
sudo pacman -U Tubify-<version>-linux-x86_64.pkg.tar.zst
```

pacman installs everything Tubify needs. In-app updates install without a password for administrators (members of `wheel`) signed in at the machine. Tubify checks that each update is a newer release signed with its release key before installing it. Other accounts are asked for an administrator password. The first update from a version without this feature asks for your password one last time.

</details>

## Getting started

1. Sign in to [YouTube Music](https://music.youtube.com) in your usual browser (Firefox, Chrome, Edge, Safari and others are supported).
2. Open Tubify and choose **Sign in via Browser**. Tubify reuses that sign-in; you never type your password into Tubify.
3. Start listening. Open the queue and lyrics panels from the player bar, and choose the expanded-player arrow for the full-screen view.

> **Tip:** Chrome and Edge lock their sign-in data while they're running on Windows. If sign-in fails, close the browser and try again, or sign in with Firefox.

## Updates

Tubify checks for new releases automatically. When one is available, an update icon with a dot appears in the top right. Click it to see what's new and choose **Update & Restart**. You can turn off automatic checks in **Settings → Updates & Troubleshooting**.

## FAQ

**Do I need YouTube Music Premium?**
No. Tubify works with any Google account that can use YouTube Music.

**Is my account safe?**
Tubify reuses your browser's existing sign-in and keeps the session in your system's secure storage: Windows Credential Manager, the macOS Keychain or your Linux keyring. Your music data goes only to YouTube, and to Discord, Last.fm or lyrics services if you turn those on. Diagnostics are saved locally and never uploaded.

**Something doesn't look right. What can I do?**
Settings → Updates & Troubleshooting can save a privacy-safe diagnostics report. Please include it when you [open an issue](https://github.com/Sayarinu/Tubify/issues).

**Can I build it myself?**
Yes. See [Building from source](docs/building.md).

## Contributing

Bug reports, ideas and pull requests are welcome. Please open an [issue](https://github.com/Sayarinu/Tubify/issues) first for larger changes. Development setup is in [docs/building.md](docs/building.md).

## License

Tubify is free and open-source software under the [MIT License](LICENSE).

Tubify releases also include third-party components, such as Qt, mpv, FFmpeg and yt-dlp, each under its own license. Some, like the bundled mpv and FFmpeg builds, are GPL. See [Third-party notices](native/src/youtube_music_native/assets/THIRD_PARTY_NOTICES.md); the app also shows these under **Settings → Updates & Troubleshooting → Open-Source Licenses**.

## Disclaimer

Tubify is an independent, unofficial project. It is not affiliated with, endorsed by or sponsored by Google LLC or YouTube. YouTube and YouTube Music are trademarks of Google LLC. Please use Tubify in line with YouTube's Terms of Service.
