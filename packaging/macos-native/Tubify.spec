# PyInstaller spec for the native Tubify macOS app bundle (Apple Silicon).
# Build with scripts/build-native-macos.sh; it supplies TUBIFY_ICON and Homebrew helper paths.
import os
from pathlib import Path
import shutil
import tomllib

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).resolve().parents[1]
NATIVE = ROOT / "native"
VERSION = tomllib.loads((NATIVE / "pyproject.toml").read_text())["project"]["version"]
BREW = Path(os.environ.get("HOMEBREW_PREFIX", "/opt/homebrew"))


def helper(name):
    path = shutil.which(name, path=str(BREW / "bin"))
    if not path:
        raise SystemExit(f"{name} is missing; run: brew install mpv ffmpeg deno")
    return (str(Path(path).resolve()), "helpers")


libmpv = BREW / "lib" / "libmpv.dylib"
if not libmpv.exists():
    raise SystemExit("libmpv is missing; run: brew install mpv")

analysis = Analysis(
    [str(Path(SPECPATH) / "tubify_entry.py")],
    pathex=[str(NATIVE / "src")],
    # PyInstaller rewrites these to load from the bundle; macos.prepare_runtime puts them on the search paths.
    binaries=[(str(libmpv.resolve()), "."), helper("ffmpeg"), helper("ffprobe"), helper("deno")],
    datas=collect_data_files("youtube_music_native") + collect_data_files("ytmusicapi"),
    # Worker roles and platform integrations are imported lazily by the launcher.
    hiddenimports=collect_submodules("youtube_music_native") + [
        "PySide6.QtNetwork",
        "MediaPlayer", "AppKit", "Foundation", "keyring.backends.macOS",
    ],
    # Sign-in happens in the user's own browser, so Chromium (QtWebEngine) is never needed.
    excludes=["tkinter", "jeepney", "gi", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick"],
)
# Qt's QML plugin collection drags WebEngine back in; drop it from the bundle entirely.
analysis.binaries = [entry for entry in analysis.binaries if "QtWebEngine" not in entry[0]]
analysis.datas = [entry for entry in analysis.datas if "QtWebEngine" not in entry[0]]
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz, analysis.scripts, [],
    exclude_binaries=True, name="Tubify", console=False,
    target_arch="arm64", codesign_identity=None,
)
collected = COLLECT(exe, analysis.binaries, analysis.datas, name="Tubify")
app = BUNDLE(
    collected,
    name="Tubify.app",
    icon=os.environ.get("TUBIFY_ICON"),
    bundle_identifier="com.carter.youtube-music.native",
    version=VERSION,
    info_plist={
        "CFBundleDisplayName": "Tubify",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "LSMinimumSystemVersion": "12.0",
        "LSApplicationCategoryType": "public.app-category.music",
        "NSHighResolutionCapable": True,
        "CFBundleURLTypes": [{"CFBundleURLName": "com.carter.youtube-music.native", "CFBundleURLSchemes": ["ytmusic-native"]}],
    },
)
