import base64
import hashlib
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QCoreApplication

from youtube_music_native import updates, maintenance
from test_maintenance import Worker


DATA = b'synthetic package'


def release(system='linux', version='0.2.0'):
    name = updates.asset_name(version, system) or f'youtube-music-native-{version}-1-x86_64.pkg.tar.zst'
    return {'tag_name': 'native-v'+version, 'assets': [{'name': name, 'size': len(DATA), 'digest': 'sha256:'+hashlib.sha256(DATA).hexdigest()}]}


@pytest.mark.parametrize('system', ['linux', 'win32', 'darwin'])
def test_exact_platform_artifact_and_digest(system):
    row = release(system)
    assert updates.select_asset(row, system)['name'] == row['assets'][0]['name']
    row['assets'][0]['digest'] = ''
    with pytest.raises(ValueError):
        updates.select_asset(row, system)


@pytest.mark.parametrize('change', ['wrong_version', 'duplicate', 'missing', 'wrapper'])
def test_reject_ambiguous_or_wrong_releases(change):
    row = release()
    if change == 'wrong_version':
        row['tag_name'] = 'native-v0.3.0'
    elif change == 'duplicate':
        row['assets'] *= 2
    elif change == 'missing':
        row['assets'] = []
    else:
        row['tag_name'] = 'v0.2.0'
    with pytest.raises(ValueError):
        updates.select_asset(row, 'linux')


@pytest.mark.parametrize('body', [DATA, b'corrupt', DATA+b'excess'])
def test_download_verifies_before_atomic_publish(tmp_path, monkeypatch, body):
    monkeypatch.setattr(updates.sys, 'platform', 'linux')
    calls, progress = [], []
    def opener(url, **kwargs):
        calls.append(url)
        return io.BytesIO(json.dumps(release()).encode() if len(calls) == 1 else body)
    if body == DATA:
        result = updates.download('native-v0.2.0', tmp_path, progress.append, opener)
        assert Path(result['path']).read_bytes() == DATA and progress[-1]['percent'] == 100
    else:
        with pytest.raises(ValueError):
            updates.download('native-v0.2.0', tmp_path, progress.append, opener)
        assert not list(tmp_path.iterdir())
    assert calls[1] == updates.BASE+'native-v0.2.0/'+release()['assets'][0]['name']


def test_interrupted_download_leaves_no_executable(tmp_path):
    class Broken(io.BytesIO):
        def read(self, size=-1):
            raise OSError('synthetic network failure')
    calls = []
    def opener(*args, **kwargs):
        calls.append(True)
        return io.BytesIO(json.dumps(release(updates.sys.platform)).encode()) if len(calls) == 1 else Broken()
    with pytest.raises(OSError):
        updates.download('native-v0.2.0', tmp_path, opener=opener)
    assert not list(tmp_path.iterdir())


def test_daily_checks_and_stale_cache_never_install(tmp_path, monkeypatch):
    app = QCoreApplication.instance() or QCoreApplication([])
    monkeypatch.setattr(updates, 'supported', lambda: True)
    service = maintenance.Maintenance(tmp_path/'cache/release.json', object(), worker_factory=Worker)
    monkeypatch.setattr(maintenance.time, 'time', lambda: 100000.)
    service._check_due()
    worker = service._worker
    assert len(worker.requests) == 1
    worker.succeeded.emit(1, {'tag':'native-v9.0.0', 'stale':True})
    assert not service.updateAvailable
    service._check_due()
    assert len(worker.requests) == 1
    service.setAutomaticChecks(False)
    monkeypatch.setattr(maintenance.time, 'time', lambda: 300000.)
    service._check_due()
    assert len(worker.requests) == 1
    service.checkRelease()
    worker.succeeded.emit(2, {'tag':'native-v9.0.0'})
    assert service.updateAvailable
    service.close()


def test_arch_auth_cancel_relaunches_without_elevating_gui(tmp_path, monkeypatch):
    package = tmp_path/'package.pkg.tar.zst'
    package.write_bytes(DATA)
    def exited(pid, signal):
        raise ProcessLookupError()
    monkeypatch.setattr(updates.os, 'kill', exited)
    calls = []
    monkeypatch.setattr(updates.subprocess, 'run', lambda argv: calls.append(argv) or SimpleNamespace(returncode=126))
    monkeypatch.setattr(updates.subprocess, 'Popen', lambda argv, **kwargs: calls.append(argv))
    assert updates.install_arch(123, package, hashlib.sha256(DATA).hexdigest()) == 126
    assert calls[0][:3] == ['/usr/bin/pkexec', '--disable-internal-agent', '/usr/bin/pacman']
    assert calls[1] == ['/usr/bin/youtube-music-native']
    assert json.loads((tmp_path/'result.json').read_text()) == {'success':False}


def test_tampered_installer_never_launches(tmp_path, monkeypatch):
    path = tmp_path/'setup.exe'
    path.write_bytes(b'changed')
    monkeypatch.setattr(updates.subprocess, 'Popen', lambda *a, **k: pytest.fail('Installer must not execute'))
    with pytest.raises(ValueError):
        updates.launch_installer({'path':str(path), 'sha256':hashlib.sha256(DATA).hexdigest()}, 123)


def test_appcast_contains_signed_versioned_download(tmp_path):
    module = Path(__file__).resolve().parents[2]/'scripts/native-appcast.py'
    spec = importlib.util.spec_from_file_location('appcast', module)
    code = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(code)
    archive = tmp_path/'Tubify-0.2.0-macos-arm64.dmg'
    archive.write_bytes(DATA)
    signature = base64.b64encode(b's'*64).decode()
    result = code.appcast('0.2.0', archive, signature).decode()
    assert 'native-v0.2.0/Tubify-0.2.0-macos-arm64.dmg' in result and signature in result
    with pytest.raises(ValueError):
        code.appcast('../escape', archive, signature)


def test_cancel_download_discards_partial_and_late_results(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    service = maintenance.Maintenance(tmp_path/'cache/release.json', object(), worker_factory=Worker)
    service._request('download', {})
    folder = tmp_path/'cache/updates'
    folder.mkdir(parents=True)
    (folder/'installer.part').write_bytes(b'partial')
    service._worker.reset = lambda: None
    service.cancelUpdate()
    assert not service.busy and not list(folder.iterdir())
    service._result(1, {'started':True})
    assert service.status == 'Update download cancelled.'
    service.close()


def test_windows_handoff_waits_for_gui_and_preserves_install_directory(tmp_path, monkeypatch):
    path = tmp_path/'setup.exe'
    path.write_bytes(DATA)
    calls = []
    monkeypatch.setattr(updates.sys, 'platform', 'win32')
    monkeypatch.setattr(updates.sys, 'executable', str(tmp_path/'Installed App/Tubify.exe'))
    monkeypatch.setattr(updates.subprocess, 'Popen', lambda argv, **kwargs: calls.append(argv))
    updates.launch_installer({'path':str(path), 'sha256':hashlib.sha256(DATA).hexdigest()}, 321)
    assert '/UPDATEPID=321' in calls[0]
    assert '/NOCLOSEAPPLICATIONS' in calls[0]
    assert calls[0][-1] == '/DIR='+str(tmp_path/'Installed App')


def test_update_preferences_use_shell_config_not_replaceable_cache(tmp_path):
    from youtube_music_native.shell import ShellController
    app = QCoreApplication.instance() or QCoreApplication([])
    shell = ShellController(tmp_path/'config/settings.ini')
    service = maintenance.Maintenance(tmp_path/'separate/cache/release.json', shell, worker_factory=Worker)
    service.setAutomaticChecks(False)
    assert service.settings is shell.settings
    assert shell.settings.value('updates/automatic', True, type=bool) is False
    service.close()
