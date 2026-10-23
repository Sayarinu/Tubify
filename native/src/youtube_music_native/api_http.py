"""Bounded loopback HTTP transport. It never reads or mutates Qt objects."""
from collections import deque
from dataclasses import dataclass, field
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import re
import socket
from threading import BoundedSemaphore, Condition, Event, Lock
from time import monotonic
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from .api_access import ApiError

CSP = "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'"
OVERLAY_FILES = {'/overlay/': ('index.html', 'text/html; charset=utf-8'), '/overlay/overlay.js': ('overlay.js', 'text/javascript; charset=utf-8'), '/overlay/overlay.css': ('overlay.css', 'text/css; charset=utf-8')}


@dataclass
class ApiRequest:
    backend: object
    operation: str
    values: dict
    digest: str
    deadline: float = field(default_factory=lambda: monotonic() + 5)
    done: Event = field(default_factory=Event)
    result: object = None
    error: object = None
    cancelled: bool = False


class HeaderReader:
    def __init__(self, stream):
        self.stream, self.total = stream, 0

    def readline(self, size):
        line = self.stream.readline(min(size, 4097))
        self.total += len(line)
        if len(line) > 4096 or self.total > 16384:
            raise http.client.LineTooLong('header')
        return line


def json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


class ApiHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    server_version = 'YouTubeMusicNative'
    sys_version = ''

    def setup(self):
        self.request.settimeout(3)
        super().setup()

    def log_message(self, *_):
        pass

    def parse_request(self):
        if len(self.raw_requestline) > 2048:
            self.requestline, self.request_version = '', 'HTTP/1.1'
            self.send_error(414)
            return False
        stream = self.rfile
        self.rfile = HeaderReader(stream)
        try:
            return super().parse_request()
        finally:
            self.rfile = stream

    def send_error(self, code, message=None, explain=None):
        self.respond(code, {'error': 'HTTP request was rejected.'})

    def respond(self, status, value, content_type='application/json; charset=utf-8'):
        body = value if isinstance(value, bytes) else json.dumps(value, separators=(',', ':'), allow_nan=False).encode()
        self.close_connection = True
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Connection', 'close')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', CSP)
        self.end_headers()
        if getattr(self, 'command', '') != 'HEAD':
            self.wfile.write(body)

    def do_GET(self):
        self.dispatch('GET')

    def do_POST(self):
        self.dispatch('POST')

    def do_OPTIONS(self):
        self.respond(403, {'error': 'Cross-origin access is unavailable.'})

    def dispatch(self, method):
        backend = self.server.backend
        try:
            if backend.stopped.is_set():
                raise ApiError(503, 'API is disabled.')
            expected_host = f'127.0.0.1:{self.server.server_port}'
            for name in ('Host', 'Origin', 'Authorization', 'Content-Length', 'Content-Type', 'Sec-Fetch-Site'):
                if len(self.headers.get_all(name, [])) > 1:
                    raise ApiError(400, 'Duplicate request headers are not accepted.')
            if self.headers.get('Host') != expected_host:
                raise ApiError(403, 'Use the literal loopback API address.')
            origin = self.headers.get('Origin')
            if origin is not None and origin != 'http://' + expected_host:
                raise ApiError(403, 'Foreign browser origins are not accepted.')
            if self.headers.get('Sec-Fetch-Site', 'none') not in {'none', 'same-origin'}:
                raise ApiError(403, 'Cross-site requests are not accepted.')
            if self.headers.get('Transfer-Encoding'):
                raise ApiError(400, 'Transfer encoding is not supported.')
            parsed = urlsplit(self.path)
            if parsed.scheme or parsed.netloc or parsed.fragment or len(self.path) > 2048:
                raise ApiError(400, 'Use a relative API path.')
            path = parsed.path
            if method == 'GET' and path in OVERLAY_FILES:
                self.overlay_query(path, parsed.query)
                name, kind = OVERLAY_FILES[path]
                resource = backend.assets / name
                if not resource.is_file() or resource.stat().st_size > 512 * 1024:
                    raise ApiError(404, 'Overlay files are not installed.')
                self.respond(200, resource.read_bytes(), kind)
                return
            values = self.body() if method == 'POST' else {}
            if method == 'POST' and path == '/v1/pair' and not parsed.query:
                if set(values) != {'code'}:
                    raise ApiError(400, 'Pairing requires only a code from the app.')
                result = backend.access.pair(values['code'])
                backend.notify_clients()
                self.respond(200, result)
                return
            required = 'control' if method == 'POST' or path == '/v1/queue' else 'overlay'
            digest = backend.access.authenticate(self.headers.get('Authorization'), required)
            backend.rate_limit(digest)
            if method == 'GET' and path == '/v1/state' and not parsed.query:
                result = backend.snapshot(digest)
            elif method == 'GET' and path == '/v1/events':
                query = self.query(parsed.query, {'after', 'timeout'})
                after = self.integer(query.get('after', ['0'])[0], 0, 2**53)
                timeout = self.integer(query.get('timeout', ['20'])[0], 0, 20)
                result = backend.events(digest, after, timeout)
            elif method == 'GET' and path == '/v1/queue':
                query = self.query(parsed.query, {'offset', 'limit'})
                result = backend.call('queue', {'offset': self.integer(query.get('offset', ['0'])[0], 0, 1000000), 'limit': self.integer(query.get('limit', ['100'])[0], 1, 200)}, digest)
            elif method == 'GET' and re.fullmatch('/v1/artwork/[a-f0-9]{24}', path) and not parsed.query:
                body, kind = backend.artwork(digest, path.rsplit('/', 1)[1])
                self.respond(200, body, kind)
                return
            elif method == 'POST' and path == '/v1/command' and not parsed.query:
                result = backend.call('command', values, digest)
            else:
                raise ApiError(404, 'API route does not exist.')
            self.respond(200, result)
        except ApiError as error:
            self.respond(error.status, {'error': error.message})
        except (ValueError, TypeError, RecursionError):
            self.respond(400, {'error': 'Invalid request.'})
        except (BrokenPipeError, ConnectionResetError, socket.timeout):
            self.close_connection = True
        except Exception:
            self.respond(503, {'error': 'API request could not complete.'})

    @staticmethod
    def overlay_query(path, raw):
        if not raw:
            return
        if path != '/overlay/':
            raise ApiError(400, 'Asset query parameters are unavailable.')
        values = parse_qs(raw, strict_parsing=True, keep_blank_values=True, max_num_fields=12)
        choices = {'preview': {'1'}, 'layout': {'full', 'compact', 'text', 'badge', 'poster', 'ticker', 'display'}, 'art': {'0', '1'}, 'title': {'0', '1'}, 'artist': {'0', '1'}, 'progress': {'0', '1'}, 'transparent': {'0', '1'}, 'paused': {'hide', 'show'}}
        for key, options in values.items():
            if len(options) != 1:
                raise ApiError(400, 'Repeated overlay option.')
            if key == 'scale':
                scale = float(options[0])
                if not math.isfinite(scale) or not .25 <= scale <= 4:
                    raise ApiError(400, 'Overlay scale must be between 0.25 and 4.')
            elif key not in choices or options[0] not in choices[key]:
                raise ApiError(400, 'Unknown overlay option.')

    @staticmethod
    def integer(value, low, high):
        if not isinstance(value, str) or not value.isascii() or not value.isdigit() or len(value) > 16 or not low <= int(value) <= high:
            raise ApiError(400, 'Query value is outside its allowed range.')
        return int(value)

    @staticmethod
    def query(text, allowed):
        values = parse_qs(text, strict_parsing=True, keep_blank_values=True, max_num_fields=4)
        if set(values) - allowed or any(len(value) != 1 for value in values.values()):
            raise ApiError(400, 'Invalid query parameters.')
        return values

    def body(self):
        length = self.integer(self.headers.get('Content-Length', ''), 1, 8192)
        if self.headers.get('Content-Type', '').split(';', 1)[0].strip().lower() != 'application/json':
            raise ApiError(415, 'Use application/json.')
        value = json.loads(self.rfile.read(length).decode('utf-8'), object_pairs_hook=json_object, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if not isinstance(value, dict):
            raise ApiError(400, 'Use a JSON object.')
        return value


class ApiServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False
    allow_reuse_address = not hasattr(socket, 'SO_EXCLUSIVEADDRUSE')

    def __init__(self, backend, port):
        self.backend, self.slots = backend, BoundedSemaphore(8)
        super().__init__(('127.0.0.1', port), ApiHandler)
        self.timeout = 0.2

    def server_bind(self):
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request, address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.slots.release()

    def handle_error(self, request, address):
        pass


class ApiBackend:
    def __init__(self, access, dispatch, notify_clients, assets, artwork_loader):
        self.access, self.dispatch, self.notify_clients = access, dispatch, notify_clients
        self.assets, self.artwork_loader = Path(assets), artwork_loader
        self.stopped, self.closed, self.condition = Event(), Event(), Condition()
        self.event_slots = BoundedSemaphore(3)
        self.current, self.source, self.revision = {}, '', 0
        self.instance_id = uuid4().hex
        self.rate_lock, self.requests = Lock(), {}
        self.art_lock, self.art_cache = Lock(), None
        self.server = None

    def run(self, port, ready, previous=None):
        try:
            if previous:
                previous.closed.wait(3)
            if self.stopped.is_set():
                return
            self.server = ApiServer(self, port)
            ready(self, self.server.server_port, '')
            while not self.stopped.is_set():
                self.server.handle_request()
        except RuntimeError:
            pass  # Qt may already be destroyed while a worker finishes shutdown.
        except OSError:
            try:
                ready(self, 0, 'The local API port is unavailable. Choose another port or retry.')
            except RuntimeError:
                pass
        finally:
            if self.server:
                self.server.server_close()
            self.stop()
            self.closed.set()

    def stop(self):
        self.stopped.set()
        with self.condition:
            self.condition.notify_all()

    def publish(self, value, source):
        with self.condition:
            if value != self.current or source != self.source:
                self.current, self.source = value, source
                self.revision += 1
                self.condition.notify_all()

    def snapshot(self, digest):
        self.access.authorize(digest)
        with self.condition:
            if self.stopped.is_set():
                raise ApiError(503, 'API is disabled.')
            return {**self.current, 'revision': self.revision, 'instanceId': self.instance_id}

    def events(self, digest, after, timeout):
        if not self.event_slots.acquire(blocking=False):
            raise ApiError(429, 'Too many event listeners. Retry shortly.')
        try:
            def ready():
                self.access.authorize(digest)
                return self.revision > after or self.stopped.is_set()
            with self.condition:
                self.condition.wait_for(ready, timeout)
            return self.snapshot(digest)
        finally:
            self.event_slots.release()

    def rate_limit(self, digest):
        with self.rate_lock:
            now = monotonic()
            if digest not in self.requests and len(self.requests) >= 64:
                self.requests.pop(next(iter(self.requests)))
            history = self.requests.setdefault(digest, deque(maxlen=120))
            while history and history[0] < now - 10:
                history.popleft()
            if len(history) >= 120:
                raise ApiError(429, 'API client request limit reached. Retry shortly.')
            history.append(now)
            if len(self.requests) > 32:
                self.requests = {key: value for key, value in self.requests.items() if value and value[-1] >= now - 10}

    def call(self, operation, values, digest):
        request = ApiRequest(self, operation, values, digest)
        self.dispatch(request)
        if not request.done.wait(max(0, request.deadline - monotonic())):
            request.cancelled = True
            raise ApiError(503, 'The application did not respond in time. Check its window before retrying.')
        if request.error:
            raise request.error
        return request.result

    def artwork(self, digest, key):
        self.access.authorize(digest)
        with self.condition:
            track = self.current.get('track') or {}
            if track.get('artwork') != '/v1/artwork/' + key or self.stopped.is_set():
                raise ApiError(404, 'Artwork is no longer current.')
            source = self.source
        with self.art_lock:
            if not self.art_cache or self.art_cache[0] != key:
                data, kind = self.artwork_loader(source)
                self.art_cache = (key, data, kind)
            _, data, kind = self.art_cache
        self.access.authorize(digest)
        with self.condition:
            if self.source != source or self.stopped.is_set():
                raise ApiError(404, 'Artwork is no longer current.')
        return data, kind
