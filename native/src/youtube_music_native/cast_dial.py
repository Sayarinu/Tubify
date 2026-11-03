"""Local-network discovery for casting: an SSDP responder and a tiny DIAL server.

Phones find Tubify with an SSDP search, read its device description and then launch the
"YouTube" DIAL app with a pairing code. Nothing else is served. Only peers on a local
subnet are answered, and requests are small and short-lived.
"""

from html import escape
from urllib.parse import parse_qs

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtNetwork import QAbstractSocket, QHostAddress, QNetworkInterface, QTcpServer, QUdpSocket

SSDP_GROUP, SSDP_PORT = "239.255.255.250", 1900
DIAL_ST = "urn:dial-multiscreen-org:service:dial:1"
PREFERRED_PORT = 38008
MAX_REQUEST = 8192
MAX_BODY = 4096
REQUEST_TIMEOUT_MS = 5000


def is_search(datagram):
    """True for an SSDP M-SEARCH looking for DIAL devices (or everything)."""
    try:
        text = datagram.decode("utf-8")
    except UnicodeDecodeError:
        return False
    lines = text.split("\r\n")
    if not lines or not lines[0].upper().startswith("M-SEARCH * HTTP/1.1"):
        return False
    headers = dict(line.split(":", 1) for line in lines[1:] if ":" in line)
    headers = {key.strip().lower(): value.strip() for key, value in headers.items()}
    return headers.get("man", "").strip('"') == "ssdp:discover" and headers.get("st") in {DIAL_ST, "ssdp:all"}


def search_reply(location, udn):
    return (
        "HTTP/1.1 200 OK\r\nCACHE-CONTROL: max-age=1800\r\nEXT:\r\n"
        f"LOCATION: {location}\r\nSERVER: Tubify UPnP/1.1 DIAL/1.7\r\n"
        f"ST: {DIAL_ST}\r\nUSN: uuid:{udn}::{DIAL_ST}\r\n"
        "BOOTID.UPNP.ORG: 1\r\nCONFIGID.UPNP.ORG: 1\r\n\r\n"
    ).encode()


def device_description(name, udn):
    return (
        '<?xml version="1.0" encoding="UTF-8"?><root xmlns="urn:schemas-upnp-org:device-1-0">'
        "<specVersion><major>1</major><minor>0</minor></specVersion><device>"
        "<deviceType>urn:dial-multiscreen-org:device:dial:1</deviceType>"
        f"<friendlyName>{escape(name)}</friendlyName><manufacturer>Nouvelle Lune</manufacturer>"
        f"<modelName>Tubify</modelName><UDN>uuid:{escape(udn)}</UDN>"
        "<serviceList><service><serviceType>urn:dial-multiscreen-org:service:dial:1</serviceType>"
        "<serviceId>urn:dial-multiscreen-org:serviceId:dial</serviceId><controlURL>/none</controlURL>"
        "<eventSubURL>/none</eventSubURL><SCPDURL>/none</SCPDURL></service></serviceList>"
        "</device></root>"
    ).encode()


def app_description(running):
    link = '<link rel="run" href="run"/>' if running else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?><service xmlns="urn:dial-multiscreen-org:schemas:dial" dialVer="1.7">'
        f'<name>YouTube</name><options allowStop="true"/><state>{"running" if running else "stopped"}</state>{link}</service>'
    ).encode()


def parse_request(data):
    """(method, path, headers, body) once a complete request has arrived; None while incomplete; ValueError if invalid."""
    end = data.find(b"\r\n\r\n")
    if end < 0:
        if len(data) > MAX_REQUEST:
            raise ValueError("headers too large")
        return None
    head = data[:end].decode("latin-1").split("\r\n")
    parts = head[0].split(" ")
    if len(parts) != 3 or not parts[2].startswith("HTTP/1."):
        raise ValueError("bad request line")
    headers = {}
    for line in head[1:]:
        key, separator, value = line.partition(":")
        if not separator:
            raise ValueError("bad header")
        headers[key.strip().lower()] = value.strip()
    length = int(headers.get("content-length", "0") or 0)
    if length < 0 or length > MAX_BODY:
        raise ValueError("body too large")
    body = data[end + 4:]
    if len(body) < length:
        return None
    return parts[0].upper(), parts[1].split("?", 1)[0], headers, body[:length]


def launch_fields(body):
    fields = parse_qs(body.decode("utf-8", "replace"), max_num_fields=20)
    return (fields.get("pairingCode") or [""])[0], (fields.get("theme") or [""])[0]


def response(status, body=b"", headers=()):
    reasons = {200: "OK", 201: "Created", 400: "Bad Request", 403: "Forbidden", 404: "Not Found", 405: "Method Not Allowed", 503: "Service Unavailable"}
    lines = [f"HTTP/1.1 {status} {reasons.get(status, 'OK')}", f"Content-Length: {len(body)}", "Connection: close", *[f"{key}: {value}" for key, value in headers]]
    return ("\r\n".join(lines) + "\r\n\r\n").encode() + body


def local_networks():
    """(address, prefix) for each up, non-loopback IPv4 interface address."""
    found = []
    for interface in QNetworkInterface.allInterfaces():
        flags = interface.flags()
        if not (flags & QNetworkInterface.InterfaceFlag.IsUp) or flags & QNetworkInterface.InterfaceFlag.IsLoopBack:
            continue
        for entry in interface.addressEntries():
            address = entry.ip()
            if address.protocol() == QAbstractSocket.NetworkLayerProtocol.IPv4Protocol:
                found.append((address, entry.prefixLength(), interface))
    return found


def local_address_for(peer, networks):
    """Our IPv4 address on the peer's subnet, or None for peers outside every local subnet."""
    peer = QHostAddress(peer.toIPv4Address()) if peer.protocol() == QAbstractSocket.NetworkLayerProtocol.IPv6Protocol and peer.toIPv4Address() else peer
    if peer.isLoopback():
        return QHostAddress(QHostAddress.SpecialAddress.LocalHost)
    for address, prefix, _interface in networks:
        if prefix > 0 and peer.isInSubnet(address, prefix):
            return address
    return None


class DialServer(QObject):
    launched = Signal(str, str)
    stopRequested = Signal()

    def __init__(self, name, udn, parent=None, port=PREFERRED_PORT, networks=local_networks):
        super().__init__(parent)
        self.name, self.udn, self.preferred_port, self.networks = name, udn, port, networks
        self.app_running = False
        self.server = self.udp = None

    @property
    def port(self):
        return self.server.serverPort() if self.server and self.server.isListening() else 0

    def start(self):
        """Listen for DIAL and SSDP; return an error message, or "" on success."""
        self.stop()
        error = self.listen_http() or self.listen_ssdp()
        if error:
            self.stop()
        return error

    def listen_http(self):
        self.server = QTcpServer(self)
        if not self.server.listen(QHostAddress(QHostAddress.SpecialAddress.AnyIPv4), self.preferred_port) and not self.server.listen(QHostAddress(QHostAddress.SpecialAddress.AnyIPv4), 0):
            return "Tubify could not open a local network port."
        self.server.newConnection.connect(self._accept)
        return ""

    def listen_ssdp(self):
        self.udp = QUdpSocket(self)
        bound = self.udp.bind(QHostAddress(QHostAddress.SpecialAddress.AnyIPv4), SSDP_PORT,
                              QAbstractSocket.BindFlag.ShareAddress | QAbstractSocket.BindFlag.ReuseAddressHint)
        joined = False
        if bound:
            for _address, _prefix, interface in self.networks():
                if interface.flags() & QNetworkInterface.InterfaceFlag.CanMulticast:
                    joined = self.udp.joinMulticastGroup(QHostAddress(SSDP_GROUP), interface) or joined
        if not joined:
            return "Tubify could not listen for phones on the local network."
        self.udp.readyRead.connect(self._datagrams)
        return ""

    def stop(self):
        for item in (self.server, self.udp):
            if item is not None:
                item.close()
                item.deleteLater()
        self.server = self.udp = None
        self.app_running = False

    def _datagrams(self):
        networks = self.networks()
        while self.udp is not None and self.udp.hasPendingDatagrams():
            datagram = self.udp.receiveDatagram(2048)
            sender = datagram.senderAddress()
            local = local_address_for(sender, networks)
            if local is None or not is_search(bytes(datagram.data().data())):
                continue
            location = f"http://{local.toString()}:{self.port}/dd.xml"
            self.udp.writeDatagram(search_reply(location, self.udn), sender, datagram.senderPort())

    def _accept(self):
        while self.server is not None and self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            if local_address_for(socket.peerAddress(), self.networks()) is None:
                socket.abort()
                socket.deleteLater()
                continue
            buffer = bytearray()
            timer = QTimer(socket)
            timer.setSingleShot(True)
            timer.timeout.connect(socket.abort)
            timer.start(REQUEST_TIMEOUT_MS)
            socket.readyRead.connect(lambda s=socket, b=buffer: self._read(s, b))
            socket.disconnected.connect(socket.deleteLater)

    def _read(self, socket, buffer):
        buffer.extend(bytes(socket.readAll().data()))
        try:
            request = parse_request(bytes(buffer))
        except ValueError:
            request = ("", "", {}, b"")
        if request is None:
            return
        socket.readyRead.disconnect()
        socket.write(self._respond(socket, *request))
        socket.disconnectFromHost()

    def _respond(self, socket, method, path, headers, body):
        app_url = f"http://{socket.localAddress().toString()}:{self.port}/apps/"
        if method == "GET" and path == "/dd.xml":
            return response(200, device_description(self.name, self.udn), [("Content-Type", "text/xml; charset=utf-8"), ("Application-URL", app_url)])
        if path.rstrip("/") == "/apps/YouTube":
            if method == "GET":
                return response(200, app_description(self.app_running), [("Content-Type", "text/xml; charset=utf-8")])
            if method == "POST":
                code, theme = launch_fields(body)
                if not code:
                    return response(400)
                self.app_running = True
                self.launched.emit(code, theme)
                return response(201, headers=[("Location", app_url + "YouTube/run")])
            return response(405)
        if path == "/apps/YouTube/run" and method == "DELETE":
            self.app_running = False
            self.stopRequested.emit()
            return response(200)
        return response(404 if method else 400)
