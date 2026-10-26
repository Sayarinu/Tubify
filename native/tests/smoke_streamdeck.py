"""Exercise the actual Node plugin API client against a synthetic Qt native player."""
import json
from pathlib import Path
import shutil
import socket
import tempfile
import traceback

from PySide6.QtCore import QProcess, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest
from youtube_music_native import app


def main():
    node = shutil.which('node')
    if not node:
        print('Stream Deck API smoke skipped: Node 24 is not installed.')
        return
    original, passed = app.load_window, []
    def load(*args, **kwargs):
        engine = original(*args, **kwargs)
        window, api = engine.rootObjects()[0], args[0].apiState
        def verify():
            process = QProcess()
            try:
                with socket.socket() as sock:
                    sock.bind(('127.0.0.1', 0)); api.setPort(sock.getsockname()[1])
                api.setEnabled(True)
                for _ in range(300):
                    if api.active: break
                    QTest.qWait(10)
                assert api.active, api.error
                api.beginPairing('Synthetic Stream Deck', 'control')
                process.setProgram(node)
                process.setArguments([str(Path(__file__).resolve().parents[1] / 'integrations/streamdeck/tests/native-api-smoke.mjs')])
                process.start()
                assert process.waitForStarted(2000)
                process.write((json.dumps({'port': api.port, 'code': api.pairingCode}) + '\n').encode())
                process.closeWriteChannel()
                output, revoked = '', False
                for _ in range(1800):
                    QTest.qWait(10)
                    output += bytes(process.readAllStandardOutput()).decode()
                    if 'revoke\n' in output and not revoked:
                        assert len(api.clients) == 1
                        assert api.revokeClient(api.clients[0]['id'])
                        revoked = True
                    if process.state() == QProcess.ProcessState.NotRunning: break
                assert process.state() == QProcess.ProcessState.NotRunning
                assert process.exitCode() == 0, bytes(process.readAllStandardError()).decode()
                assert revoked and 'passed\n' in output
                assert not engine.property('qmlWarnings'), engine.property('qmlWarnings')
                passed.append(True)
            except Exception:
                traceback.print_exc()
            finally:
                if process.state() != QProcess.ProcessState.NotRunning:
                    process.kill(); process.waitForFinished(2000)
                api.close(); window.close(); QGuiApplication.instance().exit(0 if passed else 1)
        QTimer.singleShot(300, verify)
        return engine
    app.load_window = load
    with tempfile.TemporaryDirectory(prefix='native-streamdeck-') as folder:
        result = app.main(['--fixture', '--data-dir', folder])
    app.load_window = original
    assert result == 0 and passed
    print('Stream Deck client pairing, actual Qt commands and revocation passed with synthetic data.')


if __name__ == '__main__':
    main()
