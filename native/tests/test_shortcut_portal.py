"""Linux portal protocol, asynchronous permission lifecycle, and signal routing."""
from collections import deque
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QCoreApplication

pytest.importorskip('jeepney')
from jeepney.low_level import HeaderFields as H, MessageType
from youtube_music_native.shortcut_portal import INTERFACE, PATH, REQUEST, SESSION, PortalShortcuts, registration, trigger


def signal(path, interface, name, body):
    return SimpleNamespace(header=SimpleNamespace(fields={H.path: path, H.interface: interface, H.member: name}), body=body)


def reply(*body):
    return SimpleNamespace(header=SimpleNamespace(message_type=MessageType.method_return), body=body)


class FakeConnection:
    def __init__(self, denial=False, unavailable=False, late=False):
        self.denial, self.unavailable, self.late = denial, unavailable, late
        self.responses = deque()
        self.calls, self.closed, self.phase = [], False, 0
        self.session = '/org/freedesktop/portal/session/fixture'

    @contextmanager
    def filter(self, rule, queue):
        self.queue = queue
        yield

    def send_and_get_reply(self, message, timeout):
        name = message.header.fields[H.member]
        self.calls.append((name, message.body))
        if self.unavailable:
            raise RuntimeError('unavailable')
        if name == 'GetNameOwner':
            return reply(':1.72')
        if name == 'AddMatch':
            assert 'sender=\':1.72\'' in message.body[0]
            return reply()
        if name == 'Get':
            return reply(('u', 2))
        path = '/org/freedesktop/portal/request/' + name
        if name == 'CreateSession':
            values = {'session_handle': ('s', self.session)}
        elif name == 'BindShortcuts':
            assert message.body[0] == self.session
            assert message.body[1][0][1]['preferred_trigger'] == ('s', 'CTRL+ALT+space')
            values = {'shortcuts': ('a(sa{sv})', [('toggle', {'trigger_description': ('s', 'Ctrl+Alt+Space')}), ('next', {'trigger_description': ('s', 'Ctrl+Alt+Right')})])}
        else:
            return reply()
        response = signal(path, REQUEST, "Response", (1 if self.denial else 0, values))
        (self.responses if self.late else self.queue).append(response)
        return reply(path)

    def recv_until_filtered(self, queue, timeout):
        if self.responses:
            return self.responses.popleft()
        if self.phase == 0:
            queue.append(signal(PATH, INTERFACE, 'Activated', ('/other/session', 'toggle', 1, {})))
            queue.append(signal(PATH, INTERFACE, 'Activated', (self.session, 'unknown', 1, {})))
            queue.append(signal(PATH, INTERFACE, 'Activated', (self.session, 'toggle', 1, {})))
            queue.append(signal(PATH, INTERFACE, 'ShortcutsChanged', (self.session, [('toggle', {'trigger_description': ('s', 'Super+P')})])))
            self.adapter.configure()
        else:
            self.adapter.close()
        self.phase += 1
        if queue:
            return queue.popleft()
        raise TimeoutError

    def send(self, message):
        self.calls.append((message.header.fields[H.member], message.header.fields[H.path]))

    def close(self):
        self.closed = True


ROWS = [('toggle', 'Play / pause', 'Ctrl+Alt+Space'), ('next', 'Next', 'Ctrl+Alt+Right')]


@pytest.mark.parametrize("late", [False, True])
def test_portal_protocol_scopes_events_updates_and_closes_session(late):
    app = QCoreApplication.instance() or QCoreApplication([])
    connection = FakeConnection(late=late)
    adapter = PortalShortcuts(connection_factory=lambda bus: connection)
    connection.adapter = adapter
    results, triggered = [], []
    adapter.result.connect(lambda *args: results.append(args))
    adapter.activated.connect(triggered.append)
    adapter._run(ROWS)
    assert triggered == ['toggle']
    assert results[0][0] == {'toggle': 'Ctrl+Alt+Space', 'next': 'Ctrl+Alt+Right'}
    assert results[1][0] == {'toggle': 'Super+P', 'next': 'Ctrl+Alt+Right'}
    assert results[0][3] and connection.closed
    assert any(name == 'ConfigureShortcuts' for name, _ in connection.calls)
    assert ('Close', connection.session) in connection.calls


@pytest.mark.parametrize('denial', [True, False])
def test_denied_or_missing_portal_reports_safe_fallback(denial):
    app = QCoreApplication.instance() or QCoreApplication([])
    connection = FakeConnection(denial=denial, unavailable=not denial)
    adapter = PortalShortcuts(connection_factory=lambda bus: connection)
    results = []
    adapter.result.connect(lambda *args: results.append(args))
    adapter._run(ROWS)
    assert not results[-1][0] and 'MPRIS' in results[-1][2] and not results[-1][3]
    assert ('cancelled' if denial else 'unavailable') in results[-1][2]
    assert connection.closed
    adapter.close()


def test_missing_assignments_and_trigger_conversion():
    accepted, errors = registration(ROWS, [('toggle', {'trigger_description': ('s', 'Control+P')})])
    assert accepted == {'toggle': 'Control+P'} and set(errors) == {'next'}
    assert trigger('Ctrl+Shift+PageUp') == 'CTRL+SHIFT+Page_Up'
    assert trigger('Meta+MediaNext') == 'LOGO+XF86AudioNext'


def test_close_cancels_pending_permission_without_gui_wait():
    from time import monotonic
    app = QCoreApplication.instance() or QCoreApplication([])
    class PendingConnection(FakeConnection):
        def send_and_get_reply(self, message, timeout):
            if message.header.fields[H.member] == 'BindShortcuts':
                return reply('/org/freedesktop/portal/request/pending')
            return super().send_and_get_reply(message, timeout)

        def recv_until_filtered(self, queue, timeout):
            started = monotonic()
            self.adapter.close()
            assert monotonic() - started < 0.05
            raise TimeoutError
    connection = PendingConnection()
    adapter = PortalShortcuts(connection_factory=lambda bus: connection)
    connection.adapter = adapter
    results = []
    adapter.result.connect(lambda *args: results.append(args))
    adapter._run(ROWS)
    assert not results and connection.closed
    assert ('Close', '/org/freedesktop/portal/request/pending') in connection.calls
    assert ('Close', connection.session) in connection.calls
