"""Pairing and revocation for the loopback API; only random token hashes persist."""
from collections import deque
import hashlib
import hmac
import json
from pathlib import Path
import re
import secrets
from threading import RLock
from time import monotonic
from uuid import uuid4

from .playback import write_state

SCOPES = {'overlay', 'control'}


class ApiError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message
        super().__init__(message)


class ApiAccess:
    def __init__(self, path, clock=monotonic):
        self.path, self.clock = Path(path), clock
        self.lock = RLock()
        self.clients = {}
        self.pending = None
        self.attempts = deque(maxlen=20)
        try:
            if self.path.is_file():
                if self.path.stat().st_size > 32768:
                    raise ValueError()
                rows = json.loads(self.path.read_text(encoding='utf-8'))
                if not isinstance(rows, list) or len(rows) > 32:
                    raise ValueError()
                for row in rows:
                    if not isinstance(row, dict) or set(row) != {'id', 'name', 'scope', 'hash'} or not re.fullmatch('[a-f0-9]{32}', row['id']) or not re.fullmatch('[a-f0-9]{64}', row['hash']):
                        raise ValueError()
                    self.validate(row['name'], row['scope'])
                    self.clients[row['id']] = row
        except (OSError, ValueError, TypeError, KeyError, RecursionError, ApiError):
            raise ApiError(503, 'Saved API clients could not be read. Revoke all clients to reset access.') from None

    @staticmethod
    def validate(name, scope):
        if not isinstance(name, str) or not name.strip() or len(name) > 64 or any(ord(char) < 32 for char in name) or not isinstance(scope, str) or scope not in SCOPES:
            raise ApiError(400, 'Choose a client name and an overlay or control scope.')

    def _save(self, clients):
        try:
            write_state(self.path, json.dumps(list(clients.values()), separators=(',', ':')))
        except OSError:
            raise ApiError(503, 'API clients could not be saved. Retry after checking local storage.') from None
        self.clients = clients

    def listing(self):
        with self.lock:
            return [{'id': row['id'], 'name': row['name'], 'scope': row['scope']} for row in self.clients.values()]

    def create(self, name, scope):
        self.validate(name, scope)
        with self.lock:
            if len(self.clients) >= 32:
                raise ApiError(409, 'Revoke an old client before pairing another.')
            token, identifier = secrets.token_urlsafe(32), uuid4().hex
            row = {'id': identifier, 'name': name.strip(), 'scope': scope, 'hash': hashlib.sha256(token.encode()).hexdigest()}
            self._save({**self.clients, identifier: row})
            return {'clientId': identifier, 'token': token, 'scope': scope}

    def begin_pairing(self, name, scope):
        self.validate(name, scope)
        with self.lock:
            code = secrets.token_urlsafe(18)
            self.pending = {'code': code, 'name': name, 'scope': scope, 'deadline': self.clock() + 120, 'attempts': 0}
            return code

    def cancel_pairing(self):
        with self.lock:
            self.pending = None

    def pair(self, code):
        with self.lock:
            now = self.clock()
            while self.attempts and self.attempts[0] < now - 60:
                self.attempts.popleft()
            if len(self.attempts) >= 10:
                raise ApiError(429, 'Too many pairing attempts. Try again in a minute.')
            self.attempts.append(now)
            pending = self.pending
            if not pending or now >= pending['deadline']:
                self.pending = None
                raise ApiError(401, 'Pairing code is missing or expired. Generate a new code in the app.')
            pending['attempts'] += 1
            if not isinstance(code, str) or not code.isascii() or len(code) > 64 or not hmac.compare_digest(pending['code'], code):
                if pending['attempts'] >= 10:
                    self.pending = None
                raise ApiError(401, 'Pairing code is invalid.')
            result = self.create(pending['name'], pending['scope'])
            self.pending = None
            return result

    def authenticate(self, header, required='overlay'):
        if not isinstance(header, str) or not header.startswith('Bearer ') or not re.fullmatch('[A-Za-z0-9_-]{43}', header[7:]):
            raise ApiError(401, 'A paired Bearer token is required.')
        digest = hashlib.sha256(header[7:].encode()).hexdigest()
        return self.authorize(digest, required)

    def authorize(self, digest, required='overlay'):
        with self.lock:
            row = next((row for row in self.clients.values() if hmac.compare_digest(row['hash'], digest)), None)
            if not row:
                raise ApiError(401, 'API client is unknown or revoked.')
            if required == 'control' and row['scope'] != 'control':
                raise ApiError(403, 'This action requires playback control permission.')
            return digest

    def revoke(self, identifier=None):
        with self.lock:
            self._save({key: row for key, row in self.clients.items() if identifier is not None and key != identifier})
            self.pending = None
