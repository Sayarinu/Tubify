# PyInstaller spec for the Tubify macOS app bundle (Apple Silicon).
# Build with scripts/build-native-macos.sh; it supplies TUBIFY_ICON and Homebrew helper paths.
import importlib.util
import os
from pathlib import Path
import shutil
import sys
import tomllib

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

ROOT = Path(SPECPATH).resolve().parents[1]
NATIVE = ROOT / "native"
sys.path.insert(0, str(ROOT / "packaging"))
from bundle_contents import needed_entries

VERSION = tomllib.loads((NATIVE / "pyproject.toml").read_text())["project"]["version"]
# Sparkle's feed lives in this build's own release; the tag comes from the app's shared rule.
_updates_spec = importlib.util.spec_from_file_location("tubify_updates", NATIVE / "src/tubify/updates/updates.py")
_updates = importlib.util.module_from_spec(_updates_spec)
_updates_spec.loader.exec_module(_updates)
release_tag = _updates.release_tag
BREW = Path(os.environ.get("HOMEBREW_PREFIX", "/opt/homebrew"))
# From the TUBIFY_UPDATE_PUBLIC_KEY GitHub variable.
UPDATE_PUBLIC_KEY = os.environ.get("TUBIFY_UPDATE_PUBLIC_KEY", "").strip()
if not UPDATE_PUBLIC_KEY:
    raise SystemExit("Set TUBIFY_UPDATE_PUBLIC_KEY: gh variable get TUBIFY_UPDATE_PUBLIC_KEY")


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
    datas=copy_metadata("tubify") + collect_data_files("tubify") + collect_data_files("ytmusicapi"),
    # Worker roles and platform integrations are imported lazily by the launcher.
    hiddenimports=collect_submodules("tubify") + [
        "PySide6.QtNetwork",
        "MediaPlayer", "AppKit", "Foundation", "keyring.backends.macOS",
    ],
    excludes=["tkinter", "jeepney", "gi", "PySide6.QtTest", "setuptools", "pkg_resources"],
)
# PyInstaller collects every QML module and style Qt provides; keep only what Tubify uses.
analysis.binaries = needed_entries(analysis.binaries)
analysis.datas = needed_entries(analysis.datas)
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
    bundle_identifier="studio.nouvellelune.tubify",
    version=VERSION,
    info_plist={
        "CFBundleDisplayName": "Tubify",
        "SUPublicEDKey": UPDATE_PUBLIC_KEY,
        "SUFeedURL": "https://github.com/Sayarinu/Tubify/releases/download/" + release_tag(VERSION) + "/appcast.xml",
        "SUEnableAutomaticChecks": False,
        "SUAutomaticallyUpdate": False,
        "SUAllowsAutomaticUpdates": False,
        "SUEnableSystemProfiling": False,
        "SUVerifyUpdateBeforeExtraction": True,
        # Finder shows X.Y.Z; Sparkle compares CFBundleVersion, where X.Y.ZbN sorts before X.Y.Z.
        "CFBundleShortVersionString": VERSION.split("b")[0],
        "CFBundleVersion": VERSION,
        "LSMinimumSystemVersion": "12.0",
        "LSApplicationCategoryType": "public.app-category.music",
        "NSHighResolutionCapable": True,
        "CFBundleURLTypes": [{"CFBundleURLName": "studio.nouvellelune.tubify", "CFBundleURLSchemes": ["ytmusic-native"]}],
        # Mobile Sync (off by default) answers SSDP/DIAL discovery on the local network.
        "NSLocalNetworkUsageDescription": "Tubify uses your local network so the YouTube Music app on your phone can cast to it, when you turn on Cast from Phone.",
    },
)
