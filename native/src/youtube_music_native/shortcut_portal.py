"""Wayland/X11 portal adapter. D-Bus waits and permission dialogs stay off the GUI thread."""

from collections import deque
from threading import Event, Thread
from time import monotonic
from uuid import uuid4

from PySide6.QtCore import QObject, Signal, Slot
from jeepney import DBusAddress, new_method_call
from jeepney.bus_messages import MatchRule, message_bus
from jeepney.io.blocking import open_dbus_connection
from jeepney.low_level import HeaderFields as H, MessageType


SERVICE = "org.freedesktop.portal.Desktop"
PATH = "/org/freedesktop/portal/desktop"
INTERFACE = "org.freedesktop.portal.GlobalShortcuts"
REQUEST = "org.freedesktop.portal.Request"
SESSION = "org.freedesktop.portal.Session"
FALLBACK = "The desktop global-shortcuts portal is unavailable. Existing MPRIS media controls remain available."


def trigger(binding):
    parts = binding.split("+")
    modifiers = {"Ctrl": "CTRL", "Alt": "ALT", "Shift": "SHIFT", "Meta": "LOGO"}
    keys = {"Space": "space", "Enter": "Return", "PageUp": "Page_Up", "PageDown": "Page_Down", "Backspace": "BackSpace", "MediaPlay": "XF86AudioPlay", "MediaPause": "XF86AudioPause", "MediaToggle": "XF86AudioPlay", "MediaStop": "XF86AudioStop", "MediaNext": "XF86AudioNext", "MediaPrevious": "XF86AudioPrev"}
    key = keys.get(parts[-1], parts[-1].lower() if len(parts[-1]) == 1 else parts[-1])
    return "+".join([modifiers[part] for part in parts[:-1]] + [key])


def registration(rows, shortcuts):
    requested = {key: binding for key, _, binding in rows}
    accepted = {key: details.get("trigger_description", ("s", ""))[1] for key, details in shortcuts if key in requested}
    accepted = {key: description for key, description in accepted.items() if description}
    errors = {key: "The desktop did not assign this shortcut. Use Desktop shortcuts or choose another combination." for key in requested if key not in accepted}
    return accepted, errors


class PortalShortcuts(QObject):
    activated = Signal(str)
    result = Signal(dict, dict, str, bool)
    finished = Signal()

    def __init__(self, parent=None, connection_factory=open_dbus_connection):
        super().__init__(parent)
        self.factory = connection_factory
        self._stop, self._configure = Event(), Event()
        self._thread = None
        self._request_path, self._session = "", ""
        self.finished.connect(self._dispose_if_closed)

    def register(self, rows):
        self._thread = Thread(target=self._run, args=(rows,), name="global-shortcuts-portal", daemon=True)
        self._thread.start()

    def configure(self):
        self._configure.set()

    def _call(self, connection, method, signature, body, path=PATH, interface=INTERFACE):
        response = connection.send_and_get_reply(new_method_call(DBusAddress(path, bus_name=SERVICE, interface=interface), method, signature, body), timeout=2)
        if response.header.message_type == MessageType.error:
            raise RuntimeError("Portal request failed")
        return response.body

    def _request(self, connection, pending, method, signature, body):
        self._request_path = self._call(connection, method, signature, body)[0]
        deadline = monotonic() + 120
        while not self._stop.is_set() and monotonic() < deadline:
            while pending:
                message = pending.popleft()
                if message.header.fields.get(H.path) == self._request_path and message.header.fields.get(H.interface) == REQUEST and message.header.fields.get(H.member) == "Response":
                    self._request_path = ""
                    code, values = message.body
                    if code:
                        raise PermissionError("Shortcut permission was cancelled or denied. Retry when ready; existing MPRIS media controls remain available.")
                    return values
            try:
                pending.appendleft(connection.recv_until_filtered(pending, timeout=0.2))
            except TimeoutError:
                pass
        raise TimeoutError("Shortcut permission did not complete. Retry when ready; existing MPRIS media controls remain available.")

    def _run(self, rows):
        connection = None
        try:
            connection = self.factory("SESSION")
            owner_reply = connection.send_and_get_reply(message_bus.GetNameOwner(SERVICE), timeout=2)
            if owner_reply.header.message_type == MessageType.error:
                raise RuntimeError("Portal unavailable")
            owner = owner_reply.body[0]
            if not isinstance(owner, str) or not owner.startswith(":"):
                raise RuntimeError("Invalid portal owner")
            rule = MatchRule(type="signal", sender=owner)
            connection.send_and_get_reply(message_bus.AddMatch(rule), timeout=2)
            pending = deque(maxlen=64)
            with connection.filter(rule, queue=pending):
                version = self._call(connection, "Get", "ss", (INTERFACE, "version"), interface="org.freedesktop.DBus.Properties")[0][1]
                options = {"handle_token": ("s", "request" + uuid4().hex), "session_handle_token": ("s", "session" + uuid4().hex)}
                self._session = self._request(connection, pending, "CreateSession", "a{sv}", (options,))["session_handle"][1]
                definitions = [(key, {"description": ("s", title), "preferred_trigger": ("s", trigger(binding))}) for key, title, binding in rows]
                response = self._request(connection, pending, "BindShortcuts", "oa(sa{sv})sa{sv}", (self._session, definitions, "", {"handle_token": ("s", "bind" + uuid4().hex)}))
                bound = dict(response.get("shortcuts", ("a(sa{sv})", []))[1])
                accepted, errors = registration(rows, bound.items())
                if not self._stop.is_set():
                    self.result.emit(accepted, errors, f"{len(accepted)} global shortcuts active through the desktop portal." + (" Some bindings need attention." if errors else ""), version >= 2)
                while not self._stop.is_set():
                    if self._configure.is_set():
                        self._configure.clear()
                        self._call(connection, "ConfigureShortcuts", "osa{sv}", (self._session, "", {}))
                    while pending:
                        message = pending.popleft()
                        fields, body = message.header.fields, message.body
                        if fields.get(H.interface) == SESSION and fields.get(H.path) == self._session and fields.get(H.member) == "Closed":
                            raise RuntimeError("Portal session closed")
                        if fields.get(H.interface) != INTERFACE or fields.get(H.path) != PATH or not body or body[0] != self._session:
                            continue
                        if fields.get(H.member) == "Activated" and body[1] in accepted:
                            self.activated.emit(body[1])
                        elif fields.get(H.member) == "ShortcutsChanged":
                            bound.update(body[1])
                            accepted, errors = registration(rows, bound.items())
                            self.result.emit(accepted, errors, f"{len(accepted)} global shortcuts active through the desktop portal.", version >= 2)
                    try:
                        pending.appendleft(connection.recv_until_filtered(pending, timeout=0.2))
                    except TimeoutError:
                        pass
        except Exception as error:
            if not self._stop.is_set():
                self.result.emit({}, {}, str(error) if isinstance(error, (PermissionError, TimeoutError)) else FALLBACK, False)
        finally:
            if connection:
                for path, interface in ((self._request_path, REQUEST), (self._session, SESSION)):
                    if path:
                        try:
                            connection.send(new_method_call(DBusAddress(path, bus_name=SERVICE, interface=interface), "Close"))
                        except Exception:
                            pass
                connection.close()
            try:
                self.finished.emit()
            except RuntimeError:  # The application may have destroyed Qt objects during shutdown.
                pass

    @Slot()
    def _dispose_if_closed(self):
        if self._stop.is_set():
            self.deleteLater()

    def close(self):
        self._stop.set()
        if not self._thread or not self._thread.is_alive():
            self.deleteLater()
