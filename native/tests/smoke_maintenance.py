"""Render maintenance controls and export an allowlisted report through the real worker."""
import json
from pathlib import Path
import tempfile
import time
import traceback

from PySide6.QtCore import QObject, QMetaObject, QTimer, Qt, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest

from youtube_music_native import app


def main():
    original, passed = app.load_window, []
    with tempfile.TemporaryDirectory(prefix="youtube-music-maintenance-") as folder:
        report = Path(folder) / "diagnostics.json"
        def load(*args, **kwargs):
            engine = original(*args, **kwargs)
            window, shell, player = engine.rootObjects()[0], args[0], args[2]
            def verify():
                try:
                    shell.setUiScale(150)
                    window.resize(920, 620)
                    service = shell.maintenanceState
                    assert service._worker is None and service.status == "Not checked"
                    dialog = window.findChild(QObject, "maintenanceSettings")
                    QMetaObject.invokeMethod(dialog, "open")
                    QTest.qWait(50)
                    assert dialog.property("visible") and dialog.property("height") * shell.uiScaleFactor < window.height()
                    service.exportDiagnostics(QUrl.fromLocalFile(str(report)))
                    deadline = time.monotonic() + 10
                    while service.busy and time.monotonic() < deadline:
                        QTest.qWait(20)
                    assert report.exists() and service.exportStatus == "Diagnostics saved locally.", service.exportStatus
                    result = json.loads(report.read_text())
                    assert result["width"] == 920 and result["softwareRequested"] and result["fixture"]
                    assert result["renderer"] == "Software" and result["uiScale"] == 150
                    assert not any(key in result for key in ("account", "track", "paths", "settings", "logs"))
                    playing = player.playing
                    QTest.keyClick(window, Qt.Key.Key_Space)
                    assert player.playing == playing
                    assert not engine.property("qmlWarnings"), engine.property("qmlWarnings")
                    QMetaObject.invokeMethod(dialog, "close")
                    passed.append(True)
                except Exception:
                    traceback.print_exc()
                finally:
                    window.close()
                    QGuiApplication.instance().exit(0 if passed else 1)
            QTimer.singleShot(200, verify)
            return engine
        app.load_window = load
        try:
            result = app.main(["--fixture", "--software-rendering", "--data-dir", folder])
            assert result == 0 and passed
        finally:
            app.load_window = original
    print("Maintenance idle state, native dialog and worker diagnostics export passed.")


if __name__ == "__main__":
    main()
