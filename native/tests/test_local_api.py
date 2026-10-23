"""Exercise the real bounded loopback server and the Qt command boundary."""
from concurrent.futures import ThreadPoolExecutor
import http.client
import json
import socket
from threading import Event, Thread
from time import monotonic, sleep
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QCoreApplication

from youtube_music_native.api_access import ApiAccess, ApiError
from youtube_music_native.api_http import ApiBackend, ApiRequest
from youtube_music_native.api_public import load_artwork, metadata, safe_source, validate_command
from youtube_music_native.local_api import LocalApi
from youtube_music_native.shell import ShellController
from test_playback_options import player_at, track


def error(status, callback, *args):
    with pytest.raises(ApiError) as caught:
        callback(*args)
    assert caught.value.status == status


def wait_for(predicate, timeout=3):
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        QCoreApplication.processEvents()
        if predicate():
            return
        sleep(.005)
    assert predicate()


def test_access_pairing_hashes_one_use_expiry_scopes_and_restart(tmp_path):
    now = [100.]
    path = tmp_path / 'clients.json'
    access = ApiAccess(path, clock=lambda: now[0])
    assert not path.exists() and not access.listing()
    error(401, access.pair, 'no-code')
    code = access.begin_pairing('OBS', 'overlay')
    error(401, access.pair, 'é')
    result = access.pair(code)
    assert set(result) == {'token', 'scope', 'clientId'}
    assert result['token'] not in path.read_text() and code not in path.read_text()
    assert len(result['token']) == 43
    assert set(access.listing()[0]) == {'id', 'name', 'scope'}
    digest = access.authenticate('Bearer ' + result['token'])
    error(403, access.authorize, digest, 'control')
    error(401, access.pair, code)
    restored = ApiAccess(path)
    assert restored.authenticate('Bearer ' + result['token']) == digest
    restored.revoke(result['clientId'])
    error(401, restored.authorize, digest)
    code = access.begin_pairing('Deck', 'control')
    now[0] += 121
    error(401, access.pair, code)
    access.begin_pairing('Deck', 'control')
    access.cancel_pairing()
    error(401, access.pair, code)
    for invalid in ('', 'bearer x', 'Bearer ' + 'a'*42, 'Bearer ' + 'a'*44, 'Bearer é'):
        error(401, access.authenticate, invalid)


def test_pairing_attempts_clients_bounds_and_corrupt_state(tmp_path):
    access = ApiAccess(tmp_path / 'clients.json')
    access.begin_pairing('client', 'control')
    for _ in range(10):
        error(401, access.pair, 'wrong')
    error(429, access.pair, 'wrong')
    assert access.pending is None
    for _ in range(32):
        access.create('client', 'overlay')
    error(409, access.create, 'extra', 'control')
    access.revoke()
    assert not access.listing()
    for name, scope in [('', 'overlay'), ('x\ny', 'overlay'), ('x', []), ('x', 'admin')]:
        error(400, access.create, name, scope)
    access.path.write_text('{broken')
    error(503, ApiAccess, access.path)
    access.path.write_text(json.dumps([{'id': 'a'*32, 'name': 'test', 'scope': 'invalid', 'hash': 'b'*64}]))
    error(503, ApiAccess, access.path)
    access.path.write_text('[' * 3000)
    error(503, ApiAccess, access.path)


def test_failed_revocation_does_not_forget_valid_clients(tmp_path, monkeypatch):
    from youtube_music_native import api_access
    access = ApiAccess(tmp_path / 'clients.json')
    result = access.create('client', 'control')
    digest = access.authenticate('Bearer ' + result['token'])
    def fail(*_):
        raise OSError('synthetic')
    monkeypatch.setattr(api_access, 'write_state', fail)
    error(503, access.revoke, result['clientId'])
    assert access.authorize(digest, 'control') == digest


@pytest.fixture
def server(tmp_path):
    access = ApiAccess(tmp_path / 'clients.json')
    overlay = access.create('OBS', 'overlay')
    control = access.create('Deck', 'control')
    calls = []
    def dispatch(request):
        calls.append(request)
        try:
            access.authorize(request.digest, 'control')
            if request.operation == 'command':
                validate_command(request.values)
            request.result = {'ok': True}
        except ApiError as issue:
            request.error = issue
        request.done.set()
    assets = tmp_path / 'assets'
    assets.mkdir()
    for name in ('index.html', 'overlay.js', 'overlay.css'):
        (assets / name).write_text('synthetic public shell')
    backend = ApiBackend(access, dispatch, lambda: None, assets, lambda _: (b'PNG', 'image/png'))
    backend.publish({'version': 1, 'track': {'title': 'Synthetic', 'artwork': '/v1/artwork/' + 'a'*24}}, 'safe')
    ready, port = Event(), []
    def started(_, value, message):
        port.append(value)
        assert not message
        ready.set()
    thread = Thread(target=backend.run, args=(0, started), daemon=True)
    thread.start()
    assert ready.wait(3)
    yield SimpleNamespace(backend=backend, access=access, overlay=overlay, control=control, port=port[0], calls=calls)
    backend.stop()
    thread.join(3)
    assert not thread.is_alive()


def request(server, path='/v1/state', method='GET', token=None, headers=None, body=None):
    conn = http.client.HTTPConnection('127.0.0.1', server.port, timeout=4)
    values = dict(headers or {})
    if token:
        values['Authorization'] = 'Bearer ' + token
    if isinstance(body, dict):
        body = json.dumps(body)
        values.setdefault('Content-Type', 'application/json')
    conn.request(method, path, body, values)
    response = conn.getresponse()
    payload, status, result_headers = response.read(), response.status, dict(response.getheaders())
    conn.close()
    if result_headers.get('Content-Type', '').startswith('application/json'):
        payload = json.loads(payload)
    return status, payload, result_headers


def test_http_auth_scopes_pairing_and_security_headers(server):
    assert server.backend.server.server_address[0] == '127.0.0.1'
    assert request(server)[0] == 401
    assert request(server, token='a'*43)[0] == 401
    status, body, headers = request(server, token=server.overlay['token'])
    assert status == 200 and body['track']['title'] == 'Synthetic'
    assert headers['Cache-Control'] == 'no-store' and headers['Referrer-Policy'] == 'no-referrer'
    assert "default-src 'none'" in headers['Content-Security-Policy']
    assert not any(key.lower().startswith('access-control') for key in headers)
    assert request(server, '/v1/queue', token=server.overlay['token'])[0] == 403
    assert request(server, '/v1/command', 'POST', server.overlay['token'], body={'command': 'next'})[0] == 403
    assert request(server, '/v1/command', 'POST', server.control['token'], body={'command': 'next'})[0] == 200
    assert server.calls[-1].values == {'command': 'next'}
    assert request(server, '/v1/artwork/' + 'a'*24, token=server.overlay['token'])[:2] == (200, b'PNG')
    code = server.access.begin_pairing('new client', 'control')
    status, paired, _ = request(server, '/v1/pair', 'POST', body={'code': code})
    assert status == 200 and paired['scope'] == 'control'
    assert request(server, token=paired['token'])[0] == 200
    server.access.revoke(paired['clientId'])
    assert request(server, token=paired['token'])[0] == 401


@pytest.mark.parametrize('headers', [{'Host': 'attacker.example'}, {'Host': 'localhost:9864'}, {'Origin': 'null'}, {'Origin': 'https://attacker.example'}, {'Sec-Fetch-Site': 'cross-site'}, {'Sec-Fetch-Site': 'same-site'}, {'Transfer-Encoding': 'chunked'}])
def test_http_rejects_cross_origin_rebinding_and_transfer_encoding(server, headers):
    assert request(server, token=server.control['token'], headers=headers)[0] in {400, 403}
    assert not server.calls


@pytest.mark.parametrize('path', ['/v1/state?token=secret', '/v1/queue?limit=201', '/v1/queue?limit=', '/v1/queue?limit=1&limit=2', '/v1/queue?offset=-1', '/v1/events?after=no', '/v1/events?timeout=21', '/v1/events?token=x', '/v1/artwork/../../clients.json', 'http://attacker.example/v1/state'])
def test_http_rejects_query_and_route_abuse(server, path):
    assert request(server, path, token=server.control['token'])[0] in {400, 403, 404}


@pytest.mark.parametrize('body', ['{"command":"next","command":"play"}', '{"command":"seek","position":NaN}', '[]', '{bad', '{"command":"next","extra":true}', '{"command":"volume","value":101}', '{"command":"shuffle","value":1}', '{"command":"navigate","page":"https://example.com"}', '{"command":"openMedia","kind":"song","id":"abcdefghijk"}'])
def test_http_rejects_malformed_commands(server, body):
    assert request(server, '/v1/command', 'POST', server.control['token'], headers={'Content-Type': 'application/json'}, body=body)[0] == 400


def raw(server, message):
    with socket.create_connection(('127.0.0.1', server.port), timeout=4) as sock:
        sock.sendall(message.encode())
        return sock.recv(4096).split(b'\r\n', 1)[0]


def test_http_caps_headers_body_and_rejects_duplicate_headers(server):
    host = f'127.0.0.1:{server.port}'
    assert b'400' in raw(server, f'GET /v1/state HTTP/1.1\r\nHost: {host}\r\nHost: {host}\r\n\r\n')
    assert b'431' in raw(server, f'GET /v1/state HTTP/1.1\r\nHost: {host}\r\nX-Large: ' + 'x'*5000 + '\r\n\r\n')
    assert b'414' in raw(server, f'GET /' + 'x'*2100 + f' HTTP/1.1\r\nHost: {host}\r\n\r\n')
    assert request(server, '/v1/command', 'POST', server.control['token'], headers={'Content-Length': '8193', 'Content-Type': 'application/json'})[0] == 400
    assert request(server, '/v1/command', 'POST', server.control['token'], body='{}')[0] == 415


def test_public_overlay_fixed_assets_and_presentation_options(server):
    for path in ('/overlay/', '/overlay/overlay.js', '/overlay/overlay.css', '/overlay/?layout=poster&preview=1&scale=1.5&art=0&title=1&artist=1&progress=1&transparent=1&paused=hide'):
        assert request(server, path)[0] == 200
    for path in ('/overlay/?token=x', '/overlay/?scale=NaN', '/overlay/?layout=anything', '/overlay/?title=1&title=0', '/overlay/?scale=0', '/overlay/overlay.js?preview=1'):
        assert request(server, path)[0] == 400
    for path in ('/overlay/../clients.json', '/overlay/%2e%2e/clients.json', '/overlay/index.html'):
        assert request(server, path, token=server.control['token'])[0] == 404


def test_events_publish_revocation_disable_and_listener_bound(server):
    backend = server.backend
    digest = server.access.authenticate('Bearer ' + server.overlay['token'])
    with ThreadPoolExecutor(max_workers=4) as pool:
        future = pool.submit(backend.events, digest, backend.revision, 2)
        backend.publish({'version': 1, 'track': None}, '')
        assert future.result(3)['track'] is None
        futures = [pool.submit(backend.events, digest, backend.revision, 2) for _ in range(3)]
        deadline = monotonic() + 1
        while backend.event_slots._value and monotonic() < deadline:
            sleep(.005)
        error(429, backend.events, digest, backend.revision, 0)
        server.access.revoke(server.overlay['clientId'])
        with backend.condition:
            backend.condition.notify_all()
        for future in futures:
            error(401, future.result, 3)
    digest = server.access.authenticate('Bearer ' + server.control['token'])
    assert backend.events(digest, backend.revision, 0)['revision'] == backend.revision
    backend.stop()
    error(503, backend.snapshot, digest)


def test_rate_limit_and_memory_bound(server):
    digest = server.access.authenticate('Bearer ' + server.overlay['token'])
    for _ in range(120):
        server.backend.rate_limit(digest)
    error(429, server.backend.rate_limit, digest)
    for index in range(100):
        server.backend.rate_limit(str(index))
    assert len(server.backend.requests) <= 64


def test_artwork_sources_and_metadata_are_allowlisted(tmp_path):
    root = tmp_path / 'artwork'
    root.mkdir()
    art = root / 'cover.png'
    art.write_bytes(b'\x89PNG\r\n\x1a\nsynthetic')
    assert safe_source(art.as_uri(), root) == art.as_uri()
    assert load_artwork(art.as_uri(), root)[1] == 'image/png'
    for source in ((tmp_path / 'settings.ini').as_uri(), 'file://server/share/a.png', 'https://googlevideo.com/signed?secret=1', 'https://i.ytimg.com@evil.example/a', 'http://i.ytimg.com/a', 'https://i.ytimg.com:444/a', 'https://i.ytimg.com/a#secret', 'data:image/svg+xml,test'):
        assert not safe_source(source, root)
    link = root / 'escape.png'
    try:
        link.symlink_to(tmp_path / 'private.png')
        assert not safe_source(link.as_uri(), root)
    except OSError:
        pass  # Windows CI may not grant symlink privileges.
    art.write_bytes(b'<svg>not raster</svg>')
    error(415, load_artwork, art.as_uri(), root)
    art.write_bytes(b'\xff\xd8\xff' + b'x' * (8*1024*1024))
    error(413, load_artwork, art.as_uri(), root)
    private = {'videoId': 'abcdefghijk', 'title': 'A\nB', 'artists': [{'name': 'Artist'}], 'album': {'name': 'Album'}, 'url': 'signed-private', 'cookies': 'private', 'headers': {'Authorization': 'private'}, 'thumbnail': '/private/path'}
    public = metadata(private)
    assert set(public) == {'videoId', 'title', 'artists', 'album'}
    assert public['title'] == 'AB' and 'private' not in json.dumps(public)
    assert metadata({'artists': 'wrong'})['artists'] == []
    assert not metadata({'id': 'https://private.example/signed'})['videoId']
    assert not metadata({'videoId': '/private/file'})['videoId']


def test_artwork_stale_results_and_revocation_not_returned(server):
    backend = server.backend
    digest = server.access.authenticate('Bearer ' + server.overlay['token'])
    def changed(_):
        backend.publish({'track': None}, 'next')
        return b'png', 'image/png'
    backend.artwork_loader = changed
    error(404, backend.artwork, digest, 'a'*24)
    backend.publish({'track': {'artwork': '/v1/artwork/' + 'b'*24}}, 'current')
    def revoked(_):
        server.access.revoke(server.overlay['clientId'])
        return b'png', 'image/png'
    backend.artwork_loader = revoked
    error(401, backend.artwork, digest, 'b'*24)


def controller(tmp_path):
    player = player_at(tmp_path)
    shell = ShellController(tmp_path / 'settings.ini', fixture={'shelves': []})
    calls = []
    browse = SimpleNamespace(open=lambda media: calls.append(('open', media)), play=lambda media: calls.append(('play', media)), enqueue=lambda media, nxt: calls.append(('enqueue', media, nxt)))
    library = SimpleNamespace(rate=lambda media, rating: calls.append(('rate', rating)))
    api = LocalApi(shell, player, browse, library, SimpleNamespace(connected=True), SimpleNamespace(busy=False), None, tmp_path)
    return api, player, shell, calls


def test_disabled_idle_restarts_release_port_and_command_authority(tmp_path):
    api, player, shell, calls = controller(tmp_path)
    api.start(None)
    assert not api.enabled and not api.active and api.backend is None and not api.pair_timer.isActive()
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    api.setPort(port)
    try:
        for _ in range(3):
            api.setEnabled(True)
            wait_for(lambda: api.active)
            client = api.createClient('local synthetic client', 'control')
            digest = api.access.authenticate('Bearer ' + client['token'])
            req = ApiRequest(api.backend, 'command', {'command': 'pause'}, digest)
            api._dispatch(req)
            assert req.done.is_set() and req.result['ok'] and not player.playing
            req = ApiRequest(api.backend, 'command', {'command': 'play'}, digest)
            api._dispatch(req)
            assert player.playing
            api.beginPairing('pending', 'overlay')
            assert api.pairingCode and api.pair_timer.isActive()
            previous = api.backend
            api.setEnabled(False)
            assert not api.active and not api.pairingCode and not api.pair_timer.isActive()
            req = ApiRequest(previous, 'command', {'command': 'pause'}, digest)
            api._dispatch(req)
            assert req.error.status == 503 and player.playing
        wait_for(lambda: api.retired.closed.is_set())
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(('127.0.0.1', port))
    finally:
        api.close()
        player.close()


def test_queue_projection_commands_and_revoked_or_expired_requests(tmp_path):
    api, player, shell, calls = controller(tmp_path)
    api.backend = ApiBackend(api.access, lambda _: None, lambda: None, tmp_path, lambda _: None)
    client = api.access.create('test', 'control')
    digest = api.access.authenticate('Bearer ' + client['token'])
    player.playTracks([track('a'), track('b'), track('c')])
    player.next()
    player.enqueue([track('dup'), track('dup')])
    req = ApiRequest(api.backend, 'queue', {'offset': 0, 'limit': 100}, digest)
    api._dispatch(req)
    assert req.error is None
    assert req.result['current']['track']['title'] == 'b'
    rows = req.result['items']
    assert [row['group'] for row in rows] == ['queued', 'queued', 'next']
    assert len({row['key'] for row in rows}) == 3 and req.result['total'] == 3
    assert 'a' not in [row['track']['title'] for row in rows]
    api._command({'command': 'volume', 'value': 37})
    assert shell.volume == 37
    api._command({'command': 'repeat', 'mode': 'one'})
    assert player.repeat == 'one'
    api._command({'command': 'shuffle', 'value': True})
    assert player.shuffled
    api._command({'command': 'like'})
    assert calls[-1] == ('rate', 'LIKE')
    api._command({'command': 'navigate', 'page': 'Library'})
    assert shell.page == 'Library'
    api._command({'command': 'enqueue', 'kind': 'song', 'id': 'abcdefghijk', 'next': True})
    assert calls[-1] == ('enqueue', {'kind': 'song', 'id': 'abcdefghijk', 'videoId': 'abcdefghijk'}, True)
    api._command({'command': 'remove', 'key': rows[0]['key']})
    assert len(player.queue.manual) == 1
    error(409, api._command, {'command': 'remove', 'key': 'gone'})
    error(409, api._command, {'command': 'moveToManual', 'key': rows[-1]['key'], 'target': 'gone', 'after': True})
    for expired, revoked in ((True, False), (False, True)):
        if revoked:
            api.access.revoke(client['clientId'])
        req = ApiRequest(api.backend, 'command', {'command': 'pause'}, digest, deadline=0 if expired else monotonic()+5)
        api._dispatch(req)
        assert req.error.status == (503 if expired else 401) and player.playing
    api.close()
    player.close()


def test_offline_download_artwork_and_quality_upgrade_use_native_sources(tmp_path):
    from youtube_music_native.download_view import DownloadView
    api, player, _, _ = controller(tmp_path)
    downloads = DownloadView(tmp_path, fixture=True)
    api.downloads = downloads
    root = tmp_path / 'media' / 'artwork'
    root.mkdir(parents=True)
    low, high = root / 'low.png', root / 'high.png'
    low.write_bytes(b'\x89PNG\r\n\x1a\nlow')
    high.write_bytes(b'\x89PNG\r\n\x1a\nhigh')
    player.play({**track('abcdefghijk'), 'thumbnail': 'https://i.ytimg.com/small', 'largeThumbnail': 'https://i.ytimg.com/large'})
    downloads._artwork['abcdefghijk'] = low.as_uri()
    api.backend = ApiBackend(api.access, lambda _: None, lambda: None, tmp_path, api._load_artwork)
    token = api.access.create('overlay', 'overlay')['token']
    digest = api.access.authenticate('Bearer ' + token)
    api.publish()
    key = api.backend.current['track']['artwork'].rsplit('/', 1)[1]
    assert api.backend.artwork(digest, key)[0].endswith(b'low')
    downloads._large_artwork['abcdefghijk'] = {'url': high.as_uri(), 'width': 1200, 'height': 1200}
    api.publish()
    upgraded = api.backend.current['track']['artwork'].rsplit('/', 1)[1]
    assert upgraded != key and api.backend.artwork(digest, upgraded)[0].endswith(b'high')
    error(404, api.backend.artwork, digest, key)
    api.close()
    downloads.close()
    player.close()


def test_controller_revoke_error_return_and_corrupt_access_reset(tmp_path, monkeypatch):
    from youtube_music_native import api_access
    api, player, _, _ = controller(tmp_path)
    client = api.access.create('test', 'overlay')
    def fail(*_):
        raise OSError('synthetic')
    with monkeypatch.context() as patch:
        patch.setattr(api_access, 'write_state', fail)
        assert not api.revokeClient(client['clientId']) and api.error
    assert api.clients and api.revokeClient(client['clientId']) and not api.clients
    api.close()
    api.client_path.write_text('['*3000)
    broken = LocalApi(api.shell, player, api.browse, api.library, api.account, api.actions, None, tmp_path)
    assert broken.error and broken.access is None
    broken.revokeAll()
    assert broken.access is not None and not broken.error
    broken.close()
    player.close()


def test_api_closes_without_retaining_qt_service(tmp_path):
    import gc
    import weakref
    from PySide6.QtCore import QEvent
    api, player, shell, _ = controller(tmp_path)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        api.setPort(sock.getsockname()[1])
    api.setEnabled(True)
    wait_for(lambda: api.active)
    api.close()
    wait_for(lambda: api.retired.closed.is_set())
    reference = weakref.ref(api)
    api.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    del api
    gc.collect()
    assert reference() is None
    player.close()
