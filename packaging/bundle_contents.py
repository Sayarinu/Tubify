"""Decide which Qt files the Windows and macOS bundles ship, and check finished bundles.

Tubify imports a handful of QML modules and always uses the Basic Controls style, so everything
else Qt provides only adds install time. Linux uses the system's Qt and needs none of this.

Check a finished bundle: python packaging/bundle_contents.py BUNDLE_DIR --max-files N --max-mb N
"""

import argparse
import os
from pathlib import Path
import re
import sys

# Spelled by module so Qt6WebEngineCore.dll, libQt6Pdf.so.6 and QtCharts.framework all match.
UNNEEDED_QT_LIBRARY = re.compile(
    r"^(lib)?Qt6?("
    r"3D|Bluetooth|Charts|DataVisualization|Designer|Graphs|Help|HttpServer|LabsAnimation|LabsSharedImage|LabsStyleKit|LabsSynchronizer|"
    r"LabsWavefrontMesh|Location|Multimedia|Nfc|Pdf|Positioning|QmlDesignSupport|QmlLocalStorage|QmlXmlListModel|Quick3D|"
    r"QuickControls2(FluentWinUI3|Fusion|Imagine|Material|Native|Universal|Windows)|QuickNativeStyle|QuickShapesDesignHelpers|"
    r"QuickDesigner|QuickParticles|QuickScene2D|QuickScene3D|QuickTest|QuickTimeline|QuickVectorImage|RemoteObjects|Scxml|Sensors|SerialBus|"
    r"SerialPort|Sql|StateMachine|Test|TextToSpeech|UiTools|VirtualKeyboard|WebChannel|WebEngine|WebSockets|WebView"
    r")",
)
# Under PySide6's qml folder, the only modules Tubify's QML and Qt's file dialogs import.
NEEDED_QML_MODULES = ("Qt/labs/folderlistmodel", "Qt/labs/qmlmodels", "QtCore", "QtQml", "QtQuick")
UNNEEDED_QUICK_MODULES = {
    "LocalStorage", "NativeStyle", "Particles", "Pdf", "Scene2D", "Scene3D", "Timeline", "tooling", "VectorImage", "VirtualKeyboard",
}
NEEDED_CONTROLS_FOLDERS = {"Basic", "impl"}
UNNEEDED_QT_PLUGINS = {"designer", "generic", "qmltooling", "sqldrivers"}
# Read only by development tools, never when the app runs.
UNNEEDED_QML_SUFFIXES = (".metainfo", ".qmltypes")
QT_ROOT = re.compile(r"(?:^|/)PySide6/(?:Qt/)?(?P<kind>qml|plugins|translations)(?:/(?P<rest>.*))?$")


def _qml_file_is_needed(path):
    if path.endswith(UNNEEDED_QML_SUFFIXES):
        return False
    if "/" not in path:
        return True
    if not any(path == module or path.startswith(module + "/") for module in NEEDED_QML_MODULES):
        return False
    parts = path.split("/")
    if parts[0] == "QtQml" and len(parts) > 2 and parts[1] in {"StateMachine", "XmlListModel"}:
        return False
    # QtQuick/Dialogs/quickimpl/qml/+Material and the like are per-style file dialog variants.
    if any(part.startswith("+") for part in parts):
        return False
    if parts[0] != "QtQuick" or len(parts) < 3:
        return True
    if parts[1] in UNNEEDED_QUICK_MODULES:
        return False
    return parts[1] != "Controls" or len(parts) < 4 or parts[2] in NEEDED_CONTROLS_FOLDERS


def is_needed(path):
    """Whether a file at this path, relative to anywhere in a bundle, belongs in it."""
    path = str(path).replace("\\", "/")
    if "webengine" in path.lower() or any(UNNEEDED_QT_LIBRARY.match(part) for part in path.split("/")):
        return False
    match = QT_ROOT.search(path)
    if not match:
        return True
    rest = match["rest"] or ""
    if match["kind"] == "translations":
        return False
    if match["kind"] == "plugins":
        return rest.split("/")[0] not in UNNEEDED_QT_PLUGINS
    return _qml_file_is_needed(rest)


def needed_entries(entries):
    """Filter a PyInstaller TOC, whose entries start with the path inside the bundle."""
    return [entry for entry in entries if is_needed(entry[0])]


def problems(root, max_files, max_mb):
    """List what a finished bundle has that it should not: unneeded files or too much in total."""
    root, unneeded, count, size = Path(root), [], 0, 0
    for folder, _folders, names in os.walk(root):
        for name in names:
            path = Path(folder, name)
            count += 1
            size += path.lstat().st_size
            if not is_needed(path.relative_to(root).as_posix()):
                unneeded.append(path.relative_to(root).as_posix())
    found = [f"Unneeded: {path}" for path in sorted(unneeded)]
    mb = size / 1048576
    print(f"Bundle holds {count} files, {mb:.0f} MB (limits: {max_files} files, {max_mb} MB).")
    if count > max_files:
        found.append(f"{count} files is over the limit of {max_files}.")
    if mb > max_mb:
        found.append(f"{mb:.0f} MB is over the limit of {max_mb} MB.")
    return found


def main(arguments=None):
    parser = argparse.ArgumentParser(description="Fail if a finished bundle ships more than Tubify needs.")
    parser.add_argument("root")
    parser.add_argument("--max-files", type=int, required=True)
    parser.add_argument("--max-mb", type=int, required=True)
    options = parser.parse_args(arguments)
    found = problems(options.root, options.max_files, options.max_mb)
    print("\n".join(found[:40]))
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
