"""Opt-in local API boundary; Qt owns commands and publishes public snapshots."""
from itertools import islice
from pathlib import Path
from threading import Thread
from time import monotonic

from PySide6.QtCore import QObject, Property, QSettings, QTimer, Signal, Slot, Qt
from PySide6.QtGui import QGuiApplication

from .api_access import ApiAccess, ApiError
from .api_http import ApiBackend
from .api_public import artwork_key, load_artwork, metadata, number, safe_source, validate_command
from .playback import write_state


class LocalApi(QObject):
    changed = Signal()
    requested = Signal(object)
    serverReady = Signal(object, int, str)
    clientsChanged = Signal()

    def __init__(self, shell, player, browse, library, account, actions, downloads, data_dir, parent=None):
        super().__init__(parent)
        self.shell, self.player, self.browse, self.library = shell, player, browse, library
        self.account, self.actions, self.downloads = account, actions, downloads
        self.settings = QSettings(str(Path(data_dir) / 'settings.ini'), QSettings.Format.IniFormat)
        self.client_path = Path(data_dir) / 'api-clients.json'
        self.artwork_root = Path(player.data_dir) / 'media' / 'artwork'
        self._enabled = self.settings.value('localApiEnabled', False, type=bool)
        try:
            self._port = max(1024, min(65535, int(self.settings.value('localApiPort', 9864))))
        except (TypeError, ValueError):
            self._port = 9864
        self.backend, self.access, self.window = None, None, None
        self.retired = None
        self._active, self._closed = False, False
        self._error, self._code = '', ''
        try:
            self.access = ApiAccess(self.client_path)
        except ApiError as error:
            self._error = error.message
        self.pair_timer = QTimer(self)
        self.pair_timer.setSingleShot(True)
        self.pair_timer.timeout.connect(self.cancelPairing)
        self.requested.connect(self._dispatch, Qt.ConnectionType.QueuedConnection)
        self.serverReady.connect(self._ready, Qt.ConnectionType.QueuedConnection)
        self.clientsChanged.connect(self._clients_changed, Qt.ConnectionType.QueuedConnection)
        player.changed.connect(self.publish)
        player.positionChanged.connect(self.publish)
        shell.volumeChanged.connect(self.publish)
        shell.pageChanged.connect(self.publish)
        if downloads:
            downloads.changed.connect(self.publish)
        for owner in (account, actions):
            if hasattr(owner, 'changed'):
                owner.changed.connect(self.publish)

    def start(self, window):
        self.window = window
        if self._enabled:
            self._start()

    @Property(bool, notify=changed)
    def enabled(self):
        return self._enabled

    @Property(bool, notify=changed)
    def active(self):
        return self._active

    @Property(int, notify=changed)
    def port(self):
        return self._port

    @Property(str, notify=changed)
    def baseUrl(self):
        return f'http://127.0.0.1:{self._port}' if self._active else ''

    @Property(str, notify=changed)
    def overlayUrl(self):
        return self.baseUrl + '/overlay/' if self.baseUrl else ''

    @Property(str, notify=changed)
    def error(self):
        return self._error

    @Property(str, notify=changed)
    def pairingCode(self):
        return self._code

    @Property('QVariantList', notify=changed)
    def clients(self):
        return self.access.listing() if self.access else []

    @Slot(bool)
    def setEnabled(self, value):
        if self._closed:
            return
        self._enabled = bool(value)
        self.settings.setValue('localApiEnabled', self._enabled)
        self.settings.sync()
        self._stop()
        if self._enabled:
            self._start()
        self.changed.emit()

    @Slot(int)
    def setPort(self, value):
        if self._enabled or not 1024 <= value <= 65535:
            return
        self._port = value
        self.settings.setValue('localApiPort', value)
        self.settings.sync()
        self.changed.emit()

    @Slot()
    def retry(self):
        if self._enabled and not self._closed:
            self._stop()
            self._start()

    def _start(self):
        if not self.access:
            return
        self._error = ''
        self.backend = ApiBackend(self.access, self.requested.emit, self.clientsChanged.emit, Path(__file__).parent / 'assets' / 'overlay', self._load_artwork)
        self.publish()
        Thread(target=self.backend.run, args=(self._port, self.serverReady.emit, self.retired), name='local-api', daemon=True).start()
        self.retired = None

    def _load_artwork(self, source):
        return load_artwork(source, self.artwork_root)

    @Slot(object, int, str)
    def _ready(self, backend, port, error):
        if backend is not self.backend or self._closed:
            return
        self._active, self._error = bool(port), error
        self.changed.emit()

    def _stop(self):
        self.cancelPairing()
        if self.backend:
            self.backend.stop()
            self.retired = self.backend
            self.backend = None
        self._active = False

    @Slot(str, str, result='QVariantMap')
    def createClient(self, name, scope):
        if not self._active or not self.access or self._closed:
            self._error = 'Enable the local API before pairing a client.'
            self.changed.emit()
            return {}
        try:
            result = self.access.create(name, scope)
            self._error = ''
            self.changed.emit()
            return result
        except ApiError as error:
            self._error = error.message
            self.changed.emit()
            return {}

    @Slot(str, str)
    def beginPairing(self, name, scope):
        if not self._active or not self.access or self._closed:
            return
        try:
            self._code = self.access.begin_pairing(name, scope)
            self.pair_timer.start(120000)
            self._error = ''
        except ApiError as error:
            self._error = error.message
        self.changed.emit()

    @Slot()
    def cancelPairing(self):
        self.pair_timer.stop()
        self._code = ''
        if self.access:
            self.access.cancel_pairing()
        self.changed.emit()

    @Slot()
    def copyPairingCode(self):
        if self._code:
            QGuiApplication.clipboard().setText(self._code)

    @Slot(str, result=bool)
    def revokeClient(self, identifier):
        if self.access:
            try:
                self.access.revoke(identifier)
                self._error = ''
                self._clients_changed()
                return True
            except ApiError as error:
                self._error = error.message
        self.changed.emit()
        return False

    @Slot()
    def revokeAll(self):
        try:
            if self.access:
                self.access.revoke()
            else:
                write_state(self.client_path, '[]')
                self.access = ApiAccess(self.client_path)
            self._error = ''
            self._clients_changed()
        except (ApiError, OSError):
            self._error = 'API access could not be reset. Check local storage and retry.'
        self.changed.emit()

    @Slot()
    def _clients_changed(self):
        self._code = ''
        self.pair_timer.stop()
        if self.backend:
            with self.backend.condition:
                self.backend.condition.notify_all()
        self.changed.emit()

    @Slot()
    def publish(self):
        if not self.backend or self._closed:
            return
        track = self.player.currentTrack
        public = metadata(track) if self.player.hasTrack else None
        source = ''
        if public:
            if self.downloads:
                identifier = track.get('videoId') or track.get('id')
                self.downloads.ensureArtwork(track, 600)
                source = self.downloads.largeArtwork.get(identifier, {}).get('url', '')
                source = source or self.downloads.artwork.get(identifier, '') or self.downloads.artworkSource(track, 600)
            source = safe_source(source or track.get('largeThumbnail') or track.get('thumbnail'), self.artwork_root)
            public['artwork'] = '/v1/artwork/' + artwork_key(source) if source else ''
        queue = self.player.queue
        value = {'version': 1, 'playback': {'state': 'stopped' if self.player.stopped else 'playing' if self.player.wantsPlayback else 'paused', 'position': number(self.player.position), 'duration': number(self.player.duration), 'volume': self.shell.volume, 'shuffle': self.player.shuffled, 'repeat': self.player.repeat}, 'track': public, 'navigation': {'page': self.shell.page}, 'capabilities': {'play': self.player.hasTrack, 'seek': self.player.hasTrack and self.player.duration > 0, 'next': queue.peek() is not None or self.player.hasTrack and self.player.autoplay and self.player.radio_worker is not None, 'previous': self.player.hasTrack and (bool(queue.history) or self.player.position > 3), 'rate': self.player.hasTrack and not self.actions.busy and (self.account.connected or self.shell.fixtureMode)}}
        self.backend.publish(value, source)

    @Slot(object)
    def _dispatch(self, request):
        try:
            if request.backend is not self.backend or self._closed or request.cancelled or monotonic() >= request.deadline:
                raise ApiError(503, 'API request expired or the API was disabled.')
            self.access.authorize(request.digest, 'control')
            if request.operation == 'queue':
                current = self.player.queue.current
                rows = (({'key': entry['key'], 'group': group, 'track': metadata(entry['track'])}) for group, entries in (('queued', self.player.queue.manual), ('next', self.player.queue.remaining)) for entry in entries)
                offset, limit = request.values['offset'], request.values['limit']
                request.result = {'current': {'key': current['key'], 'track': metadata(current['track'])} if current else None, 'items': list(islice(rows, offset, offset + limit)), 'offset': offset, 'total': len(self.player.queue.manual) + len(self.player.queue.remaining)}
            else:
                self._command(request.values)
                self.publish()
                request.result = {'ok': True, 'revision': self.backend.revision}
        except ApiError as error:
            request.error = error
        except Exception:
            request.error = ApiError(400, 'The command could not be applied.')
        finally:
            request.done.set()

    def _command(self, values):
        command = validate_command(values)
        methods = {'play': 'resume', 'pause': 'pause', 'stop': 'stop', 'toggle': 'togglePlayback', 'next': 'next', 'previous': 'previous', 'clearQueue': 'clearManualQueue'}
        if command in methods:
            getattr(self.player, methods[command])()
        elif command == 'seek':
            self.player.seek(values['position'])
        elif command == 'volume':
            self.shell.setVolume(values['value'])
        elif command == 'mute':
            self.shell.toggleMute()
        elif command == 'shuffle':
            self.player.setShuffle(values['value'])
        elif command == 'repeat':
            self.player.setRepeat(values['mode'])
        elif command == 'cycleRepeat':
            self.player.handleAction('repeat')
        elif command in {'like', 'dislike'}:
            if not self.player.hasTrack or self.actions.busy or not (self.account.connected or self.shell.fixtureMode):
                raise ApiError(409, 'Track ratings are currently unavailable.')
            self.library.rate(self.player.currentTrack, 'LIKE' if command == 'like' else 'DISLIKE')
        elif command == 'navigate':
            self.shell.navigate(values['page'])
        elif command == 'search':
            self.shell.search(values['query'])
        elif command == 'show':
            if self.window:
                self.window.showNormal()
                self.window.raise_()
                self.window.requestActivate()
        elif command in {'select', 'remove', 'move', 'moveToManual'}:
            if not any(entry['key'] == values['key'] for entry in self.player.queue.entries):
                raise ApiError(409, 'Queue occurrence is no longer available.')
            if command == 'select': self.player.selectKey(values['key'])
            elif command == 'remove': self.player.removeKey(values['key'])
            elif command == 'move': self.player.moveKey(values['key'], values['direction'])
            else:
                if values['target'] and not any(entry['key'] == values['target'] for entry in self.player.queue.manual):
                    raise ApiError(409, 'Manual queue target is no longer available.')
                self.player.moveToManual(values['key'], values['target'], values['after'])
        else:
            media = {'kind': values['kind'], 'id': values['id']}
            if media['kind'] == 'song':
                media['videoId'] = values['id']
            if command == 'openMedia': self.browse.open(media)
            elif command == 'playMedia': self.browse.play(media)
            elif command == 'enqueue': self.browse.enqueue(media, values['next'])

    def close(self):
        self._closed = True
        self._stop()
