"""Global shortcuts stay opt-in and delegate to the existing command owners."""
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QCoreApplication, QObject, QSettings, Signal

from youtube_music_native import shortcuts
from youtube_music_native.shortcuts import DEFAULTS, GlobalShortcuts, normalize
from youtube_music_native.shell import ShellController
from test_playback_options import player_at


class FakeAdapter(QObject):
    activated = Signal(str)
    result = Signal(dict, dict, str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.closed = False
        self.configured = False

    def register(self, rows):
        self.rows = rows
        self.result.emit({key: binding for key, _, binding in rows}, {}, 'Registered', True)

    def configure(self):
        self.configured = True

    def close(self):
        self.closed = True


def drain():
    QCoreApplication.processEvents()


def service(tmp_path, monkeypatch, factory=FakeAdapter):
    player = player_at(tmp_path)
    shell = ShellController(tmp_path / 'settings.ini')
    ratings = []
    library = SimpleNamespace(rate=lambda track, rating: ratings.append((track, rating)))
    account = SimpleNamespace(connected=True)
    actions = SimpleNamespace(busy=False)
    state = GlobalShortcuts(shell, player, library, account, actions, tmp_path / 'settings.ini', adapter_factory=factory)
    monkeypatch.setattr(shortcuts.QGuiApplication, 'focusWindow', lambda: None)
    return state, player, shell, ratings


@pytest.mark.parametrize(('given', 'expected'), [(' alt + control + p ', 'Ctrl+Alt+P'), ('super+shift+f5', 'Shift+Meta+F5'), ('option+2', 'Alt+2'), ('F6', 'F6'), ('MediaNext', 'MediaNext'), ('', '')])
def test_portable_chords(given, expected):
    assert normalize(given, 'linux') == expected


@pytest.mark.parametrize('given', ['p', 'Shift+A', 'Ctrl++', 'Ctrl+Ctrl+A', 'Ctrl+A,B', 'Ctrl+é', 'Ctrl+Alt+Delete', 'Alt+Tab', 'Alt+F4', ['Ctrl+A'], 'A' * 81])
def test_invalid_and_reserved_chords(given):
    with pytest.raises(ValueError):
        normalize(given, 'linux')


def test_platform_reserved_chords():
    for chord in ('Meta+R', 'Ctrl+F12'):
        with pytest.raises(ValueError):
            normalize(chord, 'win32')
    for chord in ('Cmd+Space', 'Command+Q', 'Alt+Meta+Escape', 'Meta+Shift+Tab'):
        with pytest.raises(ValueError):
            normalize(chord, 'darwin')


def test_disabled_creates_no_adapter_persists_and_replaces_registration(tmp_path, monkeypatch):
    created = []
    def factory(parent):
        adapter = FakeAdapter(parent)
        created.append(adapter)
        return adapter
    state, player, _, _ = service(tmp_path, monkeypatch, factory)
    state.start(None)
    assert not state.enabled and not created
    assert state.setBinding('toggle', 'Ctrl+Alt+P')
    assert not created
    state.setEnabled(True)
    drain()
    assert state.bindings[0]['registered'] == 'Ctrl+Alt+P'
    assert state.canConfigure
    state.configure()
    assert created[-1].configured
    assert not state.setBinding('next', 'Ctrl+Alt+P')
    assert next(row for row in state.bindings if row['id'] == 'next')['error']
    assert state.setBinding('toggle', '')
    drain()
    assert created[0].closed and 'toggle' not in dict((row[0], row[2]) for row in created[-1].rows)
    state.reset()
    drain()
    assert state.bindings[0]['binding'] == DEFAULTS['toggle']
    state.setEnabled(False)
    drain()
    assert created[-1].closed and not state.adapter
    restored = GlobalShortcuts(state.shell, player, state.library, state.account, state.actions, tmp_path / 'settings.ini', adapter_factory=factory)
    assert not restored.enabled and restored.bindings[0]['binding'] == DEFAULTS['toggle']
    state.close()
    restored.close()
    player.close()


def test_stale_callbacks_unknown_actions_and_focus_guards(tmp_path, monkeypatch):
    state, player, shell, _ = service(tmp_path, monkeypatch)
    state.setEnabled(True)
    drain()
    old = state.adapter
    state.retry()
    drain()
    old.activated.emit('toggle')
    old.result.emit({'unknown': 'Ctrl+P'}, {}, 'stale', True)
    drain()
    assert player.playing and state.status == 'Registered'
    state.adapter.activated.emit('unknown')
    drain()
    assert player.playing
    focus = QObject()
    focus.setProperty('playbackShortcuts', False)
    monkeypatch.setattr(shortcuts.QGuiApplication, 'focusWindow', lambda: focus)
    state.adapter.activated.emit('toggle')
    drain()
    assert player.playing
    focus.setProperty('playbackShortcuts', True)
    state.adapter.activated.emit('toggle')
    drain()
    assert not player.playing
    state.setEnabled(False)
    old.activated.emit('toggle')
    drain()
    assert not player.playing
    state.close()
    player.close()


def test_commands_use_shared_player_volume_and_ratings(tmp_path, monkeypatch):
    state, player, shell, ratings = service(tmp_path, monkeypatch)
    calls = []
    for name in ('togglePlayback', 'resume', 'pause', 'stop', 'previous', 'next', 'seek', 'handleAction'):
        monkeypatch.setattr(player, name, lambda *args, name=name: calls.append((name, args)))
    state.setBinding('play', 'Ctrl+Alt+F1')
    state.setBinding('pause', 'Ctrl+Alt+F2')
    state.setEnabled(True)
    drain()
    for key in ('toggle', 'play', 'pause', 'stop', 'previous', 'next', 'seekBack', 'seekForward', 'shuffle', 'repeat', 'volumeDown', 'like', 'dislike'):
        state.adapter.activated.emit(key)
        drain()
    assert [name for name, _ in calls] == ['togglePlayback', 'resume', 'pause', 'stop', 'previous', 'next', 'seek', 'seek', 'handleAction', 'handleAction']
    assert calls[6][1] == (player.position - 5,)
    assert calls[7][1] == (player.position + 5,)
    assert shell.volume == 65
    assert [rating for _, rating in ratings] == ['LIKE', 'DISLIKE']
    state.actions.busy = True
    state.adapter.activated.emit('like')
    drain()
    state.actions.busy, state.account.connected = False, False
    state.adapter.activated.emit('dislike')
    drain()
    assert len(ratings) == 2
    state.adapter.activated.emit('mute')
    drain()
    assert shell.volume == 0
    state.adapter.activated.emit('mute')
    drain()
    assert shell.volume == 65
    state.close()
    player.close()


def test_registration_failure_is_visible_and_retryable(tmp_path, monkeypatch):
    def unavailable(parent):
        raise RuntimeError('private OS failure detail')
    state, player, _, _ = service(tmp_path, monkeypatch, unavailable)
    state.setEnabled(True)
    assert state.enabled and 'unavailable' in state.status and 'private' not in state.status
    state.factory = FakeAdapter
    state.retry()
    drain()
    assert state.status == 'Registered'
    state.close()
    player.close()


@pytest.mark.parametrize("saved", ['{"toggle":"plain text"}', "[]", "null"])
def test_corrupt_saved_binding_does_not_register(tmp_path, monkeypatch, saved):
    settings = QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat)
    settings.setValue('globalShortcutsEnabled', True)
    settings.setValue("globalShortcuts", saved)
    settings.sync()
    state, player, _, _ = service(tmp_path, monkeypatch)
    assert not state.enabled and 'could not be read' in state.status
    state.close()
    player.close()


def test_worker_notifications_dispatch_on_the_gui_thread(tmp_path, monkeypatch):
    from threading import Thread, get_ident
    gui_thread, observed = get_ident(), []
    class WorkerAdapter(FakeAdapter):
        def register(self, rows):
            self.thread = Thread(target=lambda: (self.result.emit({'toggle': 'Ctrl+Alt+Space'}, {}, 'Ready', False), self.activated.emit('toggle')))
            self.thread.start()
    state, player, _, _ = service(tmp_path, monkeypatch, WorkerAdapter)
    monkeypatch.setattr(player, 'togglePlayback', lambda: observed.append(get_ident()))
    state.setEnabled(True)
    state.adapter.thread.join(timeout=1)
    drain()
    assert state.status == 'Ready' and observed == [gui_thread]
    state.close()
    player.close()


def test_repeated_enable_disable_releases_adapter_objects(tmp_path, monkeypatch):
    import gc
    import weakref
    from PySide6.QtCore import QEvent
    class DeletingAdapter(FakeAdapter):
        def close(self):
            super().close()
            self.deleteLater()
    state, player, _, _ = service(tmp_path, monkeypatch, DeletingAdapter)
    references = []
    for _ in range(20):
        state.setEnabled(True)
        drain()
        references.append(weakref.ref(state.adapter))
        state.setEnabled(False)
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        drain()
    gc.collect()
    assert all(reference() is None for reference in references)
    assert not state.children()
    state.close()
    player.close()
