"""A YouTube Lounge screen session: pairing, the bind long-poll and outgoing state messages.

The Lounge protocol is what TVs use when a phone casts to them. It is undocumented and
can change without notice (see LUNE-470). Tokens, session IDs, screen IDs and device data
stay inside this module: they never reach logs, status text or exceptions.
"""

import json
import random
import re
import time
import uuid
from urllib.parse import urlencode

from PySide6.QtCore import QByteArray, QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

BASE = "https://www.youtube.com/api/lounge"
SCREEN_APP = "tubify"
RETRY_MS = (2000, 5000, 15000, 30000, 60000)
POLL_TIMEOUT_MS = 330000
REQUEST_TIMEOUT_MS = 20000
TOKEN_MARGIN_S = 24 * 3600
MAX_FRAME_BUFFER = 1 << 20
DEVICE_INFO = json.dumps({
    "brand": "Nouvelle Lune", "model": "Tubify", "year": 0, "os": "Desktop", "osVersion": "", "chipset": "",
    "clientName": "TVHTML5", "dialAdditionalDataSupportLevel": "unsupported", "mdxDialServerType": "MDX_DIAL_SERVER_TYPE_UNKNOWN",
}, separators=(",", ":"))


class FrameParser:
    """Split the bind stream ("<length>\\n<json array>" repeated) into (aid, name, payload) messages."""

    def __init__(self):
        self.buffer = ""
        self.decoder = json.JSONDecoder()

    def feed(self, text):
        self.buffer += text
        if len(self.buffer) > MAX_FRAME_BUFFER:
            self.buffer = ""
            raise ValueError("Lounge frame too large")
        messages = []
        while True:
            match = re.match(r"\s*(\d+)\n", self.buffer)
            if not match:
                break
            try:
                value, end = self.decoder.raw_decode(self.buffer, match.end())
            except json.JSONDecodeError:
                break
            self.buffer = self.buffer[end:]
            for item in value if isinstance(value, list) else []:
                if isinstance(item, list) and len(item) == 2 and isinstance(item[0], int) and isinstance(item[1], list) and item[1] and isinstance(item[1][0], str):
                    body = item[1]
                    messages.append((item[0], body[0], body[1] if len(body) == 2 else body[1:] if len(body) > 2 else None))
        return messages


def encode_messages(ofs, messages):
    """Form fields for sending (name, payload) messages in one bind POST."""
    form = {"count": len(messages), "ofs": ofs}
    for index, (name, payload) in enumerate(messages):
        form[f"req{index}__sc"] = name
        for key, value in (payload or {}).items():
            form[f"req{index}_{key}"] = value
    return form


class LoungeSession:
    """Session values for the bind URL; the network-free half of the Lounge client."""

    def __init__(self, device_id, name, theme="m"):
        self.device_id, self.name, self.theme = device_id, name, theme
        self.token, self.token_expiry = "", 0.
        self.reset()

    def reset(self):
        self.sid = self.gsessionid = ""
        self.rid, self.aid, self.ofs = random.randint(41000, 49999), 0, 0

    @property
    def bound(self):
        return bool(self.token and self.sid and self.gsessionid)

    def common(self):
        return {
            "device": "LOUNGE_SCREEN", "id": self.device_id, "obfuscatedGaiaId": "", "name": self.name, "app": SCREEN_APP,
            "theme": self.theme, "capabilities": "dsp,mic,dpa,ntb", "cst": "m", "mdxVersion": 2, "loungeIdToken": self.token,
            "VER": 8, "v": 2, "zx": uuid.uuid4().hex[:12], "t": 1,
        }

    def query(self, kind):
        params = self.common()
        if kind == "init":
            params.update(deviceInfo=DEVICE_INFO, RID=self.rid, CVER=1)
            self.rid += 1
        elif kind == "send":
            params.update(deviceInfo=DEVICE_INFO, SID=self.sid, RID=self.rid, AID=self.aid, gsessionid=self.gsessionid)
            self.rid += 1
        else:
            params.update(RID="rpc", SID=self.sid, CI=0, AID=self.aid, gsessionid=self.gsessionid, TYPE="xmlhttp")
        return urlencode(params)

    def absorb(self, messages):
        """Track AIDs and session values; return the messages meant for the player."""
        commands = []
        for aid, name, payload in messages:
            self.aid = max(self.aid, aid)
            if name == "c" and isinstance(payload, list) and payload and isinstance(payload[0], str):
                self.sid = payload[0]
            elif name == "S" and isinstance(payload, str):
                self.gsessionid = payload
            elif name not in {"noop", "c", "S"}:
                commands.append((name, payload if isinstance(payload, dict) else {}))
        return commands


class Lounge(QObject):
    """Keeps one screen session bound and forwards commands; reconnects with backoff."""

    command = Signal(str, "QVariantMap")
    connected = Signal()
    stateChanged = Signal(str)

    def __init__(self, settings, name, parent=None, network=None, clock=time.time):
        super().__init__(parent)
        self.settings, self.clock = settings, clock
        device_id = str(settings.value("cast/deviceId", "") or "")
        if not re.fullmatch(r"[0-9a-f-]{36}", device_id):
            device_id = str(uuid.uuid4())
            settings.setValue("cast/deviceId", device_id)
        self.session = LoungeSession(device_id, name)
        self.network = network or QNetworkAccessManager(self)
        self.parser = FrameParser()
        self._poll_reply = self._send_reply = None
        self._requests = set()
        self._outbox, self._running, self._failures = [], False, 0
        self.retry = QTimer(self)
        self.retry.setSingleShot(True)
        self.retry.timeout.connect(self._connect)

    # --- Public -----------------------------------------------------------------------------
    @property
    def screen_id(self):
        value = str(self.settings.value("cast/screenId", "") or "")
        return value if re.fullmatch(r"[A-Za-z0-9_-]{8,64}", value) else ""

    @property
    def ready(self):
        return self._running and self.session.bound

    def start(self):
        if not self._running:
            self._running, self._failures = True, 0
            self._connect()

    def stop(self):
        self._running = False
        self.retry.stop()
        for reply in [self._poll_reply, self._send_reply, *self._requests]:
            if reply is not None:
                reply.abort()
        self._poll_reply = self._send_reply = None
        self._requests.clear()
        self._outbox.clear()
        self.session.reset()
        self.stateChanged.emit("stopped")

    def rename(self, name):
        self.session.name = name
        if self._running:
            self.stop()
            self.start()

    def forget(self):
        """Drop this screen's identity; a new one is created on the next connection, with no phones paired."""
        running = self._running
        self.stop()
        self.settings.remove("cast/screenId")
        self.session.token, self.session.token_expiry = "", 0
        if running:
            self.start()

    def send(self, name, payload=None):
        if self.ready:
            self._outbox.append((name, {key: str(value) for key, value in (payload or {}).items()}))
            self._flush()

    def register_pairing_code(self, code, done):
        """Link a phone that launched us over DIAL; done(bool) reports the result."""
        if not (self._running and self.screen_id and re.fullmatch(r"[A-Za-z0-9-]{4,64}", code or "")):
            done(False)
            return
        self._post(f"{BASE}/pairing/register_pairing_code", {
            "access_type": "permanent", "app": SCREEN_APP, "pairing_code": code, "screen_id": self.screen_id,
            "screen_name": self.session.name, "device_id": self.session.device_id,
        }, lambda status, body: done(status == 200))

    # --- Connection steps -------------------------------------------------------------------
    def _connect(self):
        if not self._running:
            return
        self.stateChanged.emit("connecting")
        if not self.screen_id:
            self._get(f"{BASE}/pairing/generate_screen_id", self._screen_created)
        elif not self.session.token or self.session.token_expiry - self.clock() < TOKEN_MARGIN_S:
            self._post(f"{BASE}/pairing/get_lounge_token_batch", {"screen_ids": self.screen_id}, self._token_received)
        else:
            self._bind()

    def _screen_created(self, status, body):
        screen = body.strip()
        if status != 200 or not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", screen):
            return self._fail()
        self.settings.setValue("cast/screenId", screen)
        self._connect()

    def _token_received(self, status, body):
        try:
            screen = json.loads(body)["screens"][0]
            token, expiry = str(screen["loungeToken"]), int(screen.get("expiration", 0)) / 1000
        except (ValueError, KeyError, IndexError, TypeError):
            token, expiry = "", 0
        if status != 200 or not token:
            if status in {400, 404}:
                self.settings.remove("cast/screenId")
            return self._fail()
        self.session.token, self.session.token_expiry = token, expiry or self.clock() + 13 * 86400
        self._connect()

    def _bind(self):
        self.session.reset()
        self.parser = FrameParser()
        self._post(f"{BASE}/bc/bind?{self.session.query('init')}", {"count": 0}, self._bound)

    def _bound(self, status, body):
        try:
            commands = self.session.absorb(self.parser.feed(body)) if status == 200 else []
        except ValueError:
            commands = []
        if not self.session.bound:
            if status in {401, 403}:
                self.session.token = ""
            return self._fail()
        self._failures = 0
        self.stateChanged.emit("ready")
        self.connected.emit()
        for name, payload in commands:
            self.command.emit(name, payload)
        self._poll()

    def _poll(self):
        if not self.ready:
            return
        if self.session.token_expiry - self.clock() < TOKEN_MARGIN_S:
            self.session.token = ""
            self._connect()
            return
        self.parser = FrameParser()
        request = self._request(f"{BASE}/bc/bind?{self.session.query('poll')}", POLL_TIMEOUT_MS)
        reply = self.network.get(request)
        self._poll_reply = reply
        reply.readyRead.connect(lambda: self._polled_data(reply))
        reply.finished.connect(lambda: self._poll_finished(reply))

    def _polled_data(self, reply):
        if reply is not self._poll_reply:
            return
        try:
            commands = self.session.absorb(self.parser.feed(bytes(reply.readAll().data()).decode("utf-8", "replace")))
        except ValueError:
            reply.abort()
            return
        for name, payload in commands:
            self.command.emit(name, payload)

    def _poll_finished(self, reply):
        reply.deleteLater()
        if reply is not self._poll_reply:
            return
        self._poll_reply = None
        if not self._running:
            return
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute) or 0
        if reply.error() == QNetworkReply.NetworkError.NoError:
            self._poll()
        elif status in {400, 404, 410}:
            self._connect_after_session_loss()
        elif status in {401, 403}:
            self.session.token = ""
            self._connect_after_session_loss()
        else:
            self._fail()

    def _connect_after_session_loss(self):
        self.session.reset()
        self._connect()

    def _flush(self):
        if self._send_reply is not None or not self._outbox or not self.ready:
            return
        batch, self._outbox = self._outbox[:20], self._outbox[20:]
        form = encode_messages(self.session.ofs, batch)
        self.session.ofs += len(batch)
        url = f"{BASE}/bc/bind?{self.session.query('send')}"
        self._send_reply = self._post(url, form, self._sent, track=False)

    def _sent(self, status, body):
        self._send_reply = None
        if status in {400, 404, 410} and self._running:
            self._outbox.clear()
            self._connect_after_session_loss()
            return
        self._flush()

    def _fail(self):
        if not self._running:
            return
        self.session.reset()
        delay = RETRY_MS[min(self._failures, len(RETRY_MS) - 1)]
        self._failures += 1
        self.stateChanged.emit("retrying")
        self.retry.start(delay)

    # --- HTTP -------------------------------------------------------------------------------
    def _request(self, url, timeout=REQUEST_TIMEOUT_MS):
        request = QNetworkRequest(QUrl(url))
        request.setTransferTimeout(timeout)
        request.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader, "Tubify")
        return request

    def _get(self, url, done):
        reply = self.network.get(self._request(url))
        return self._watch(reply, done, True)

    def _post(self, url, form, done, track=True):
        request = self._request(url)
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/x-www-form-urlencoded")
        reply = self.network.post(request, QByteArray(urlencode(form).encode()))
        return self._watch(reply, done, track)

    def _watch(self, reply, done, track):
        if track:
            self._requests.add(reply)

        def finished():
            self._requests.discard(reply)
            reply.deleteLater()
            if not self._running:
                return
            status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute) or 0
            body = bytes(reply.readAll().data()).decode("utf-8", "replace") if reply.error() == QNetworkReply.NetworkError.NoError else ""
            done(int(status) if reply.error() == QNetworkReply.NetworkError.NoError else int(status or 0) or -1, body)
        reply.finished.connect(finished)
        return reply
