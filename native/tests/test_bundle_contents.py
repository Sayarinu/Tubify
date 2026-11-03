import importlib.util
from pathlib import Path
import re

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("bundle_contents", ROOT / "packaging" / "bundle_contents.py")
bundle_contents = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle_contents)
is_needed = bundle_contents.is_needed
SOURCE = ROOT / "native" / "src" / "youtube_music_native"


@pytest.mark.parametrize("path", [
    r"PySide6\Qt6WebEngineCore.dll",
    r"PySide6\QtWebEngineProcess.exe",
    r"PySide6\resources\qtwebengine_resources.pak",
    "PySide6/Qt/lib/QtWebEngineCore.framework/Versions/A/QtWebEngineCore",
    "PySide6/Qt/lib/libQt6Pdf.so.6",
    r"PySide6\Qt6Charts.dll",
    r"PySide6\Qt6QuickControls2FluentWinUI3.dll",
    r"PySide6\qml\QtQuick3D\qmldir",
    r"PySide6\qml\QtQuick\Controls\Material\Button.qml",
    r"PySide6\qml\QtQuick\Controls\FluentWinUI3\qmldir",
    r"PySide6\qml\QtQuick\Dialogs\quickimpl\qml\+Material\FileDialog.qml",
    r"PySide6\qml\QtQuick\Particles\qmldir",
    r"PySide6\qml\QtQuick\plugins.qmltypes",
    r"PySide6\qml\QtQml\StateMachine\qmldir",
    r"PySide6\translations\qtbase_de.qm",
    "PySide6/Qt/translations/qtbase_de.qm",
    r"PySide6\plugins\sqldrivers\qsqlite.dll",
])
def test_unneeded_files_are_left_out(path):
    assert not is_needed(path)


@pytest.mark.parametrize("path", [
    r"PySide6\Qt6Core.dll",
    r"PySide6\Qt6Quick.dll",
    r"PySide6\Qt6QuickControls2.dll",
    r"PySide6\Qt6QuickControls2Basic.dll",
    r"PySide6\Qt6QuickControls2Impl.dll",
    r"PySide6\Qt6Svg.dll",
    "PySide6/Qt/lib/QtQuick.framework/Versions/A/QtQuick",
    r"PySide6\qml\QtQuick\qmldir",
    r"PySide6\qml\QtQuick\Controls\qmldir",
    r"PySide6\qml\QtQuick\Controls\Basic\Button.qml",
    r"PySide6\qml\QtQuick\Controls\impl\qmldir",
    r"PySide6\qml\QtQuick\Dialogs\quickimpl\qml\FileDialog.qml",
    r"PySide6\qml\Qt\labs\folderlistmodel\qmldir",
    r"PySide6\plugins\platforms\qwindows.dll",
    r"PySide6\plugins\imageformats\qsvg.dll",
    r"helpers\ffmpeg.exe",
    r"youtube_music_native\qml\Main.qml",
    r"youtube_music_native\assets\Roboto-Bold.ttf",
])
def test_needed_files_stay(path):
    assert is_needed(path)


def test_every_qml_import_is_bundled():
    modules = set()
    for path in (SOURCE / "qml").glob("*.qml"):
        modules.update(re.findall(r"^import +(Qt[\w.]*)", path.read_text(encoding="utf-8"), re.M))
    assert "QtQuick.Controls" in modules
    missing = [module for module in modules if not is_needed("PySide6/qml/" + module.replace(".", "/") + "/qmldir")]
    assert not missing, f"Add these to packaging/bundle_contents.py: {missing}"


def test_every_python_qt_module_is_bundled():
    modules = set()
    for path in SOURCE.glob("*.py"):
        modules.update(re.findall(r"PySide6\.(Qt\w+)", path.read_text(encoding="utf-8")))
    assert "QtQuick" in modules
    missing = [module for module in modules if not is_needed(f"PySide6/{module}.pyd") or not is_needed(f"PySide6/Qt6{module[2:]}.dll")]
    assert not missing, f"Add these to packaging/bundle_contents.py: {missing}"


def test_needed_entries_filters_a_pyinstaller_table():
    entries = [("PySide6/Qt6Core.dll", "source", "BINARY"), ("PySide6/Qt6WebEngineCore.dll", "source", "BINARY")]
    assert bundle_contents.needed_entries(entries) == entries[:1]


def test_finished_bundle_check_reports_unneeded_files_and_limits(tmp_path, capsys):
    (tmp_path / "PySide6").mkdir()
    (tmp_path / "PySide6" / "Qt6Core.dll").write_bytes(b"x" * 1024)
    arguments = [str(tmp_path), "--max-files", "1", "--max-mb", "1"]
    assert bundle_contents.main(arguments) == 0
    (tmp_path / "PySide6" / "Qt6WebEngineCore.dll").write_bytes(b"x")
    assert bundle_contents.main(arguments) == 1
    output = capsys.readouterr().out
    assert "Unneeded: PySide6/Qt6WebEngineCore.dll" in output and "over the limit of 1." in output
