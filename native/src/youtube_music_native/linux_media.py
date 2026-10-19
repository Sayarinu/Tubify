"""Linux MPRIS and logind transport; Qt state is accessed only through signals."""

from queue import SimpleQueue, Empty
import math
import selectors
import socket
from threading import Event, Lock, Thread
from uuid import uuid4

from PySide6.QtCore import QObject, Signal
from jeepney import DBusAddress, new_error, new_method_return, new_signal
from jeepney.bus_messages import message_bus, MatchRule
from jeepney.io.blocking import open_dbus_connection
from jeepney.low_level import HeaderFields as H, MessageType


ROOT = "org.mpris.MediaPlayer2"
PLAYER = ROOT + ".Player"
PROPERTIES = "org.freedesktop.DBus.Properties"
PATH = "/org/mpris/MediaPlayer2"
ROOT_VALUES = {"CanQuit": ("b", True), "CanRaise": ("b", True), "HasTrackList": ("b", False), "Identity": ("s", "YouTube Music Native"), "DesktopEntry": ("s", "youtube-music-native"), "SupportedUriSchemes": ("as", []), "SupportedMimeTypes": ("as", [])}
PLAYER_TYPES = {"PlaybackStatus": "s", "LoopStatus": "s", "Rate": "d", "Shuffle": "b", "Metadata": "a{sv}", "Volume": "d", "Position": "x", "MinimumRate": "d", "MaximumRate": "d", "CanGoNext": "b", "CanGoPrevious": "b", "CanPlay": "b", "CanPause": "b", "CanSeek": "b", "CanControl": "b"}
WRITABLE = {"LoopStatus", "Rate", "Shuffle", "Volume"}
METHODS = {"Next": "", "Previous": "", "Pause": "", "PlayPause": "", "Stop": "", "Play": "", "Seek": "x", "SetPosition": "ox", "OpenUri": "s"}


def introspection():
    root = ''.join(f'<property name="{name}" type="{kind}" access="read"/>' for name, (kind, _) in ROOT_VALUES.items())
    player = ''.join(f'<property name="{name}" type="{kind}" access="{"readwrite" if name in WRITABLE else "read"}"/>' for name, kind in PLAYER_TYPES.items())
    methods = ''.join('<method name="' + name + '">' + ''.join(f'<arg type="{kind}" direction="in"/>' for kind in signature) + '</method>' for name, signature in METHODS.items())
    return f'''<node><interface name="{ROOT}">{root}<method name="Raise"/><method name="Quit"/></interface>
<interface name="{PLAYER}">{player}{methods}<signal name="Seeked"><arg type="x"/></signal></interface>
<interface name="{PROPERTIES}"><method name="Get"><arg type="s" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="out"/></method><method name="GetAll"><arg type="s" direction="in"/><arg type="a{{sv}}" direction="out"/></method><method name="Set"><arg type="s" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="in"/></method><signal name="PropertiesChanged"><arg type="s"/><arg type="a{{sv}}"/><arg type="as"/></signal></interface>
<interface name="org.freedesktop.DBus.Introspectable"><method name="Introspect"><arg type="s" direction="out"/></method></interface>
<interface name="org.freedesktop.DBus.Peer"><method name="Ping"/></interface></node>'''


def reply(message, snapshot):
    """Validate public D-Bus calls and return a response plus a GUI command."""
    fields = message.header.fields
    interface, member, signature = fields.get(H.interface), fields.get(H.member), fields.get(H.signature, "")
    error = "UnknownMethod"
    if fields.get(H.path) != PATH:
        error = "UnknownObject"
    elif interface == "org.freedesktop.DBus.Introspectable" and member == "Introspect" and not signature:
        return new_method_return(message, "s", (introspection(),)), None
    elif interface == "org.freedesktop.DBus.Peer" and member == "Ping" and not signature:
        return new_method_return(message), None
    elif interface == ROOT and member in {"Raise", "Quit"} and not signature:
        return new_method_return(message), (member, [])
    elif interface == PLAYER and member in METHODS:
        if signature == METHODS[member]:
            return new_method_return(message), (member, list(message.body))
        error = "InvalidArgs"
    elif interface == PROPERTIES:
        expected = {"Get": "ss", "GetAll": "s", "Set": "ssv"}.get(member)
        if expected and signature == expected:
            values = ROOT_VALUES if message.body[0] == ROOT else {name: (PLAYER_TYPES[name], value) for name, value in snapshot.items()} if message.body[0] == PLAYER else None
            if values is None:
                error = "UnknownInterface"
            elif member == "GetAll":
                return new_method_return(message, "a{sv}", (values,)), None
            elif message.body[1] not in values:
                error = "UnknownProperty"
            elif member == "Get":
                return new_method_return(message, "v", (values[message.body[1]],)), None
            elif message.body[0] != PLAYER or message.body[1] not in WRITABLE:
                error = "PropertyReadOnly"
            else:
                name, (kind, value) = message.body[1:]
                valid = kind == PLAYER_TYPES[name]
                if name == "LoopStatus":
                    valid = valid and value in {"None", "Track", "Playlist"}
                if name in {"Rate", "Volume"}:
                    valid = valid and math.isfinite(value)
                if valid:
                    return new_method_return(message), ("Set" + name, [value])
                error = "InvalidArgs"
        else:
            error = "InvalidArgs"
    return new_error(message, "org.freedesktop.DBus.Error." + error, "s", ("This media operation is unavailable.",)), None


class LinuxBus(QObject):
    command = Signal(str, list)
    preparingForSleep = Signal(bool)
    availabilityChanged = Signal(bool, bool)

    def __init__(self, snapshot, parent=None, bus="SESSION", monitor_sleep=True):
        super().__init__(parent)
        self.service = ROOT + ".youtube_music_native.instance" + uuid4().hex
        self._bus, self._monitor_sleep = bus, monitor_sleep
        self._snapshot, self._latest = snapshot, None
        self._lock, self._stop, self._events = Lock(), Event(), SimpleQueue()
        self._read, self._write = socket.socketpair()
        self._read.setblocking(False)
        self._write.setblocking(False)
        self._thread = Thread(target=self._run, name="desktop-media", daemon=True)

    def start(self):
        self._thread.start()

    def publish(self, snapshot):
        with self._lock:
            self._latest = snapshot
        self._wake()

    def seeked(self, position):
        self._events.put(int(position * 1000000))
        self._wake()

    def _wake(self):
        try:
            self._write.send(b"\0")
        except (OSError, BlockingIOError):
            pass

    def _flush(self, session):
        with self._lock:
            latest, self._latest = self._latest, None
        if latest is not None:
            changed = {name: (PLAYER_TYPES[name], value) for name, value in latest.items() if name != "Position" and value != self._snapshot.get(name)}
            self._snapshot = latest
            if changed:
                session.send(new_signal(DBusAddress(PATH, interface=PROPERTIES), "PropertiesChanged", "sa{sv}as", (PLAYER, changed, [])))
        while True:
            try:
                position = self._events.get_nowait()
            except Empty:
                break
            session.send(new_signal(DBusAddress(PATH, interface=PLAYER), "Seeked", "x", (position,)))

    def _run(self):
        session, system = None, None
        try:
            session = open_dbus_connection(self._bus)
            result = session.send_and_get_reply(message_bus.RequestName(self.service, 4), timeout=2)
            if result.body != (1,):
                raise RuntimeError("Media service unavailable")
            owner = None
            if self._monitor_sleep:
                try:
                    system = open_dbus_connection("SYSTEM")
                    owner = system.send_and_get_reply(message_bus.GetNameOwner("org.freedesktop.login1"), timeout=2).body[0]
                    if not isinstance(owner, str) or not owner.startswith(":"):
                        raise RuntimeError("Sleep service unavailable")
                    rule = MatchRule(type="signal", sender="org.freedesktop.login1", interface="org.freedesktop.login1.Manager", member="PrepareForSleep", path="/org/freedesktop/login1")
                    system.send_and_get_reply(message_bus.AddMatch(rule), timeout=2)
                except Exception:
                    if system:
                        system.close()
                    system = None
            if not self._stop.is_set():
                self.availabilityChanged.emit(True, system is not None)
            with selectors.DefaultSelector() as selector:
                selector.register(self._read, selectors.EVENT_READ, "wake")
                selector.register(session.sock, selectors.EVENT_READ, session)
                if system:
                    selector.register(system.sock, selectors.EVENT_READ, system)
                while not self._stop.is_set():
                    self._flush(session)
                    for key, _ in selector.select(timeout=1):
                        if key.data == "wake":
                            try:
                                while self._read.recv(4096):
                                    pass
                            except BlockingIOError:
                                pass
                            continue
                        connection = key.data
                        while not self._stop.is_set():
                            try:
                                message = connection.receive(timeout=0)
                            except TimeoutError:
                                break
                            if connection is session and message.header.message_type == MessageType.method_call:
                                self._flush(session)
                                response, command = reply(message, self._snapshot)
                                session.send(response)
                                if command:
                                    self.command.emit(*command)
                            elif connection is system and message.header.message_type == MessageType.signal and message.header.fields.get(H.sender) == owner and message.header.fields.get(H.member) == "PrepareForSleep" and message.header.fields.get(H.path) == "/org/freedesktop/login1" and message.header.fields.get(H.interface) == "org.freedesktop.login1.Manager" and message.header.fields.get(H.signature) == "b":
                                self.preparingForSleep.emit(message.body[0])
        except Exception:
            if not self._stop.is_set():
                self.availabilityChanged.emit(False, False)
        finally:
            if session:
                session.close()
            if system:
                system.close()
            self._read.close()

    def close(self):
        self._stop.set()
        self._wake()
        self._thread.join(timeout=1)
        self._write.close()
