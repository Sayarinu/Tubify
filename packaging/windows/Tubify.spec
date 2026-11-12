# PyInstaller spec for the Tubify Windows x64 app.
import os
import re
from pathlib import Path
import sys
import tomllib

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata
from PyInstaller.utils.win32.versioninfo import FixedFileInfo, StringFileInfo, StringTable, StringStruct, VarFileInfo, VarStruct, VSVersionInfo

ROOT = Path(SPECPATH).resolve().parents[1]
NATIVE = ROOT / "native"
sys.path.insert(0, str(ROOT / "packaging"))
from bundle_contents import needed_entries

# From the TUBIFY_UPDATE_PUBLIC_KEY GitHub variable. The app only runs installers signed by this key.
UPDATE_PUBLIC_KEY = os.environ.get("TUBIFY_UPDATE_PUBLIC_KEY", "").strip()
if not UPDATE_PUBLIC_KEY:
    raise SystemExit("Set TUBIFY_UPDATE_PUBLIC_KEY: gh variable get TUBIFY_UPDATE_PUBLIC_KEY")
VERSION = tomllib.loads((NATIVE / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
# Windows file versions are four numbers: an experimental X.Y.ZbN build is X.Y.Z.N.
version_tuple = tuple(int(part) for part in re.findall(r"\d+", VERSION))
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
analysis = Analysis(
    [str(Path(SPECPATH) / "tubify_entry.py")],
    pathex=[str(NATIVE / "src")],
    datas=copy_metadata("tubify") + collect_data_files("tubify") + collect_data_files("ytmusicapi"),
    hiddenimports=(
        collect_submodules("tubify")
        + collect_submodules("winrt")
        + ["PySide6.QtNetwork", "keyring.backends.Windows"]
    ),
    excludes=["tkinter", "jeepney", "gi", "PySide6.QtTest", "setuptools", "pkg_resources"],
)
# PyInstaller collects every QML module and style Qt provides; keep only what Tubify uses.
analysis.binaries = needed_entries(analysis.binaries)
analysis.datas = needed_entries(analysis.datas)
public_key_file = Path(workpath) / "update-public-key"
public_key_file.write_text(UPDATE_PUBLIC_KEY + "\n", encoding="ascii")
analysis.datas += [("update-public-key", str(public_key_file), "DATA")]
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz, analysis.scripts, [],
    exclude_binaries=True, name="Tubify", console=False,
    version=version_info, icon=os.environ["TUBIFY_ICON"],
)
collected = COLLECT(exe, analysis.binaries, analysis.datas, name="Tubify")
