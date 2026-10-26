"""Real native settings and authenticated OBS assets using synthetic playback only."""
import argparse
import http.client
import json
from pathlib import Path
import socket
import tempfile
import traceback
from urllib.parse import parse_qs, urlsplit

from PySide6.QtCore import QObject, QMetaObject, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest

from youtube_music_native import app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--ui-scale', type=int, default=150)
    options = parser.parse_args()
    original, passed = app.load_window, []

    def load(*args, **kwargs):
        engine = original(*args, **kwargs)
        window = engine.rootObjects()[0]
        shell = args[0]
        api, obs = shell.apiState, shell.obsState

        def verify():
            try:
                shell.setUiScale(options.ui_scale)
                window.resize(920, 620)
                window.requestActivate()
                with socket.socket() as sock:
                    sock.bind(('127.0.0.1', 0))
                    api.setPort(sock.getsockname()[1])
                api.setEnabled(True)
                for _ in range(300):
                    if api.active:
                        break
                    QTest.qWait(10)
                assert api.enabled and api.active, (api.enabled, api.active, api.error)
                dialog = window.findChild(QObject, 'obsSettings')
                QMetaObject.invokeMethod(dialog, 'open')
                for _ in range(300):
                    if dialog.property('opened'):
                        break
                    QTest.qWait(10)
                QTest.qWait(60)  # Let the shared page layout settle after resizing/scaling.
                assert dialog.property('opened'), 'OBS dialog did not finish opening'
                assert not window.property('playbackShortcuts')
                assert dialog.property('width') * shell.uiScaleFactor < window.width()
                assert dialog.property('height') * shell.uiScaleFactor < window.height()
                button = window.findChild(QObject, 'obsGenerate')
                QMetaObject.invokeMethod(button, 'clicked')
                QTest.qWait(30)
                assert obs.hasSource and api.clients[0]['scope'] == 'overlay'
                parts = urlsplit(obs.source_url())
                token = parse_qs(parts.fragment)['token'][0]
                assert token not in parts.query

                def get(path, bearer=''):
                    conn = http.client.HTTPConnection('127.0.0.1', api.port, timeout=3)
                    headers = {'Authorization': 'Bearer ' + bearer} if bearer else {}
                    conn.request('GET', path, headers=headers)
                    response = conn.getresponse()
                    status, body, response_headers = response.status, response.read(), dict(response.getheaders())
                    conn.close()
                    return status, body, response_headers

                for layout in ('full', 'compact', 'text', 'badge', 'poster', 'ticker', 'display'):
                    obs.setOption('layout', layout)
                    public_url = urlsplit(obs.source_url(preview=True))
                    status, body, headers = get(public_url.path + '?' + public_url.query)
                    assert status == 200 and b'overlay.js' in body
                    assert "default-src 'none'" in headers['Content-Security-Policy']
                    assert headers['Referrer-Policy'] == 'no-referrer'
                for asset in ('overlay.js', 'overlay.css'):
                    assert get('/overlay/' + asset)[0] == 200
                status, body, _ = get('/v1/state', token)
                assert status == 200 and json.loads(body)['version'] == 1
                assert get('/v1/queue', token)[0] == 403
                assert get('/overlay/?token=not-allowed')[0] == 400
                assert get('/overlay/?preview=1', '')[0] == 200
                obs.revoke()
                assert not obs.hasSource and not obs.hasClient
                assert get('/v1/state', token)[0] == 401
                obs.setOption('layout', 'full')
                QTest.qWait(70)
                if options.output_dir:
                    options.output_dir.mkdir(parents=True, exist_ok=True)
                    assert window.grabWindow().save(str(options.output_dir / 'obs-settings-920.png'))
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
    with tempfile.TemporaryDirectory(prefix='youtube-music-obs-') as folder:
        result = app.main(['--fixture', '--data-dir', folder])
    app.load_window = original
    assert result == 0 and passed
    print('OBS native settings, seven layouts, CSP, read-only scope, revocation and scaled modal passed.')


if __name__ == '__main__':
    main()
