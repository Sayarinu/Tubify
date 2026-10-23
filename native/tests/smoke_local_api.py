"""Synthetic QML and real HTTP smoke, including scaled modal layout."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import http.client
import json
from pathlib import Path
import socket
import tempfile
import traceback

from PySide6.QtCore import QObject, QMetaObject, QPointF, QTimer, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest

from youtube_music_native import app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--ui-scale', type=int, default=100)
    options = parser.parse_args()
    original, passed = app.load_window, []

    def load(*args, **kwargs):
        engine = original(*args, **kwargs)
        window = engine.rootObjects()[0]
        shell, player = args[0], args[2]
        api = shell.apiState

        def verify():
            try:
                shell.setUiScale(options.ui_scale)
                window.resize(920, 620)
                window.requestActivate()
                assert not api.enabled and api.backend is None
                with socket.socket() as sock:
                    sock.bind(('127.0.0.1', 0))
                    api.setPort(sock.getsockname()[1])
                dialog = window.findChild(QObject, 'apiSettings')
                QMetaObject.invokeMethod(dialog, 'open')
                for _ in range(300):
                    if dialog.property('opened'):
                        break
                    QTest.qWait(10)
                assert dialog.property('opened'), 'Local API dialog did not finish opening'
                enabled = window.findChild(QObject, 'apiEnabled')
                point = enabled.mapToScene(QPointF(enabled.width()/2, enabled.height()/2)).toPoint()
                QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=point)
                assert api.enabled, 'Local API checkbox click did not enable the service'
                for _ in range(300):
                    if api.active:
                        break
                    QTest.qWait(10)
                assert api.enabled and api.active, (api.enabled, api.active, api.error)
                assert not window.property('playbackShortcuts')
                field = window.findChild(QObject, 'apiClientName')
                field.setProperty('text', 'Synthetic control')
                field.forceActiveFocus()
                scope = window.findChild(QObject, 'apiClientScope')
                scope.setProperty('currentIndex', 1)
                button = window.findChild(QObject, 'apiBeginPairing')
                QMetaObject.invokeMethod(button, 'clicked')
                QTest.qWait(20)
                assert api.pairingCode
                def call(path, method='GET', body=None, token=None):
                    conn = http.client.HTTPConnection('127.0.0.1', api.port, timeout=4)
                    headers = {'Content-Type': 'application/json'}
                    if token:
                        headers['Authorization'] = 'Bearer ' + token
                    conn.request(method, path, json.dumps(body) if body else None, headers)
                    response = conn.getresponse()
                    result = response.status, json.loads(response.read())
                    conn.close()
                    return result
                def finish(future):
                    for _ in range(500):
                        if future.done():
                            return future.result()
                        QTest.qWait(10)
                    raise AssertionError('API request did not finish')
                with ThreadPoolExecutor(max_workers=1) as pool:
                    status, client = finish(pool.submit(call, '/v1/pair', 'POST', {'code': api.pairingCode}))
                    assert status == 200 and client['scope'] == 'control'
                    QTest.qWait(30)
                    assert not api.pairingCode and len(api.clients) == 1
                    status, result = finish(pool.submit(call, '/v1/command', 'POST', {'command': 'pause'}, client['token']))
                    assert status == 200 and result['ok'] and not player.playing
                    status, snapshot = finish(pool.submit(call, '/v1/state', token=client['token']))
                    assert status == 200 and snapshot['playback']['state'] == 'paused'
                    assert api.revokeClient(client['clientId'])
                    assert finish(pool.submit(call, '/v1/state', token=client['token']))[0] == 401
                assert dialog.property('width') * shell.uiScaleFactor < window.width()
                assert dialog.property('height') * shell.uiScaleFactor < window.height()
                if options.output_dir:
                    options.output_dir.mkdir(parents=True, exist_ok=True)
                    assert window.grabWindow().save(str(options.output_dir / 'local-api-920.png'))
                api.setEnabled(False)
                assert not api.active and api.backend is None
                QMetaObject.invokeMethod(dialog, 'close')
                QTest.qWait(30)
                assert not engine.property('qmlWarnings'), engine.property('qmlWarnings')
                passed.append(True)
            except Exception:
                traceback.print_exc()
            finally:
                api.close()
                window.close()
                QGuiApplication.instance().exit(0 if passed else 1)
        QTimer.singleShot(200, verify)
        return engine

    app.load_window = load
    with tempfile.TemporaryDirectory(prefix='youtube-music-local-api-') as folder:
        result = app.main(['--fixture', '--data-dir', folder])
    app.load_window = original
    assert result == 0 and passed
    print('Local API settings, pairing, authenticated Qt command dispatch, revocation and scaling passed.')


if __name__ == '__main__':
    main()
