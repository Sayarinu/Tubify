# PyInstaller spec for the native Tubify Windows x64 app.
import json
import os
from pathlib import Path
import tomllib

from PyInstaller.utils.hooks import collect_data_files, collect_submodules
from PyInstaller.utils.win32.versioninfo import FixedFileInfo, StringFileInfo, StringTable, StringStruct, VarFileInfo, VarStruct, VSVersionInfo

ROOT = Path(SPECPATH).resolve().parents[1]
NATIVE = ROOT / "native"
VERSION = tomllib.loads((NATIVE / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
version_tuple = tuple(int(part) for part in VERSION.split("."))
version_tuple = (version_tuple + (0, 0, 0, 0))[:4]
version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=version_tuple, prodvers=version_tuple, OS=0x40004, fileType=1),
    kids=[StringFileInfo([StringTable("040904B0", [
        StringStruct("CompanyName", "Nouvelle Lune Atelier"),
        StringStruct("FileDescription", "Tubify"),
        StringStruct("ProductName", "Tubify"),
        StringStruct("FileVersion", VERSION),
        StringStruct("ProductVersion", VERSION),
        StringStruct("InternalName", "Tubify"),
        StringStruct("OriginalFilename", "Tubify.exe"),
    ])]), VarFileInfo([VarStruct("Translation", [1033, 1200])])],
)
manifest = Path(os.environ["TUBIFY_BINARY_MANIFEST"])
BINARY_ITEMS = json.loads(manifest.read_text(encoding="utf-8"))
binaries = [(row["source"], row["destination"]) for row in BINARY_ITEMS]

analysis = Analysis(
    [str(Path(SPECPATH) / "tubify_entry.py")],
    pathex=[str(NATIVE / "src")],
    binaries=binaries,
    datas=collect_data_files("youtube_music_native") + collect_data_files("ytmusicapi"),
    hiddenimports=(
        collect_submodules("youtube_music_native")
        + collect_submodules("winrt")
        + ["PySide6.QtNetwork", "keyring.backends.Windows"]
    ),
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
    version=version_info, icon=os.environ["TUBIFY_ICON"],
)
collected = COLLECT(exe, analysis.binaries, analysis.datas, name="Tubify")
