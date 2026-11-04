from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer
from PySide6.QtNetwork import QHostAddress, QTcpSocket, QNetworkInterface

import pytest

from youtube_music_native.cast_dial import (
    DIAL_ST, DialServer, app_description, device_description, is_search, launch_fields, local_address_for, parse_request, search_reply,
)

SEARCH = f'M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: "ssdp:discover"\r\nMX: 1\r\nST: {DIAL_ST}\r\n\r\n'.encode()


def test_only_dial_searches_are_answered():
    assert is_search(SEARCH)
    assert is_search(SEARCH.replace(DIAL_ST.encode(), b"ssdp:all"))
    assert not is_search(SEARCH.replace(DIAL_ST.encode(), b"urn:schemas-upnp-org:device:MediaRenderer:1"))
    assert not is_search(b"NOTIFY * HTTP/1.1\r\n\r\n")
    assert not is_search(b"\xff\xfe")
    reply = search_reply("http://192.168.1.5:38008/dd.xml", "udn-1").decode()
    assert "LOCATION: http://192.168.1.5:38008/dd.xml\r\n" in reply and f"ST: {DIAL_ST}\r\n" in reply and f"USN: uuid:udn-1::{DIAL_ST}" in reply


def test_descriptions_escape_the_device_name():
    assert b"<friendlyName>Tubify &lt;b&gt; &amp; co</friendlyName>" in device_description("Tubify <b> & co", "udn")
    assert b"<state>stopped</state>" in app_description(False) and b'rel="run"' not in app_description(False)
    assert b"<state>running</state>" in app_description(True) and b'rel="run"' in app_description(True)


def test_requests_parse_only_when_complete_and_within_limits():
    assert parse_request(b"GET /dd.xml HTTP/1.1\r\nHost: x") is None
    assert parse_request(b"GET /dd.xml?x=1 HTTP/1.1\r\nHost: x\r\n\r\n") == ("GET", "/dd.xml", {"host": "x"}, b"")
    assert parse_request(b"POST /apps/YouTube HTTP/1.1\r\nContent-Length: 10\r\n\r\npairing") is None
    assert parse_request(b"POST /apps/YouTube HTTP/1.1\r\nContent-Length: 7\r\n\r\npairingXX")[3] == b"pairing"
    for bad in (b"GARBAGE\r\n\r\n", b"GET / HTTP/1.1\r\nno colon\r\n\r\n", b"POST / HTTP/1.1\r\nContent-Length: 999999\r\n\r\n", b"GET / HTTP/1.1\r\n" + b"x" * 9000):
        with pytest.raises(ValueError):
            parse_request(bad)
    assert launch_fields(b"pairingCode=abcd-1234&theme=m&v=x") == ("abcd-1234", "m")
    assert launch_fields(b"theme=m") == ("", "m")


def test_only_local_subnet_peers_are_served():
    networks = [(QHostAddress("192.168.1.5"), 24, None), (QHostAddress("10.0.0.2"), 8, None)]
    assert local_address_for(QHostAddress("192.168.1.77"), networks).toString() == "192.168.1.5"
    assert local_address_for(QHostAddress("10.200.1.1"), networks).toString() == "10.0.0.2"
    assert local_address_for(QHostAddress("127.0.0.1"), networks).isLoopback()
    assert local_address_for(QHostAddress("8.8.8.8"), networks) is None
    assert local_address_for(QHostAddress("::ffff:192.168.1.9"), networks).toString() == "192.168.1.5"


def http(port, raw):
    socket, loop, data = QTcpSocket(), QEventLoop(), bytearray()
    socket.readyRead.connect(lambda: data.extend(bytes(socket.readAll().data())))
    socket.disconnected.connect(loop.quit)
    socket.connected.connect(lambda: socket.write(raw))
    QTimer.singleShot(3000, loop.quit)
    socket.connectToHost(QHostAddress("127.0.0.1"), port)
    loop.exec()
    return bytes(data).decode("latin-1")


def test_dial_http_launch_and_stop_over_loopback():
    app = QCoreApplication.instance() or QCoreApplication([])
    server, launches, stops = DialServer("Tubify test", "udn-1", port=0, networks=lambda: []), [], []
    server.launched.connect(lambda code, theme: launches.append((code, theme)))
    server.stopRequested.connect(lambda: stops.append(True))
    assert server.listen_http() == "" and server.port
    description = http(server.port, b"GET /dd.xml HTTP/1.1\r\nHost: x\r\n\r\n")
    assert description.startswith("HTTP/1.1 200") and f"Application-URL: http://127.0.0.1:{server.port}/apps/" in description and "Tubify test" in description
    assert "<state>stopped</state>" in http(server.port, b"GET /apps/YouTube HTTP/1.1\r\n\r\n")
    assert http(server.port, b"POST /apps/YouTube HTTP/1.1\r\nContent-Length: 7\r\n\r\ntheme=m").startswith("HTTP/1.1 400")
    body = b"pairingCode=abcd-1234&theme=m"
    launched = http(server.port, b"POST /apps/YouTube HTTP/1.1\r\nContent-Length: %d\r\n\r\n%s" % (len(body), body))
    assert launched.startswith("HTTP/1.1 201") and f"Location: http://127.0.0.1:{server.port}/apps/YouTube/run" in launched
    assert launches == [("abcd-1234", "m")] and "<state>running</state>" in http(server.port, b"GET /apps/YouTube HTTP/1.1\r\n\r\n")
    assert http(server.port, b"DELETE /apps/YouTube/run HTTP/1.1\r\n\r\n").startswith("HTTP/1.1 200") and stops == [True]
    assert http(server.port, b"GET /etc/passwd HTTP/1.1\r\n\r\n").startswith("HTTP/1.1 404")
    assert http(server.port, b"BROKEN\r\n\r\n").startswith("HTTP/1.1 400")
    server.stop()
    assert not server.port and app


def test_networks_that_appear_after_launch_are_joined():
    app = QCoreApplication.instance() or QCoreApplication([])

    class Interface:
        def __init__(self, name):
            self.name = name

        def flags(self):
            return QNetworkInterface.InterfaceFlag.CanMulticast

    class Socket:
        joined = []

        def joinMulticastGroup(self, _group, interface):
            self.joined.append(interface.name)
            return True

    networks = [(QHostAddress("192.168.1.5"), 24, Interface("wifi"))]
    server = DialServer("Tubify test", "udn-1", port=0, networks=lambda: networks)
    server.udp = Socket()
    assert server.join_networks() and Socket.joined == ["wifi"]
    networks.append((QHostAddress("192.168.1.6"), 24, Interface("wired")))
    server.membership.timeout.emit()
    assert Socket.joined == ["wifi", "wifi", "wired"]
    server.udp = None
