import base64
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace

from Cryptodome.Signature import eddsa
import pytest
from PySide6.QtCore import QCoreApplication

from youtube_music_native.updates import updates

from youtube_music_native.updates import maintenance
from test_maintenance import Worker


DATA = b'synthetic package'


def asset_row(name, data=DATA):
    return {'name': name, 'size': len(data), 'digest': 'sha256:'+hashlib.sha256(data).hexdigest()}


def release(system='linux', version='0.2.0'):
    name = updates.asset_name(version, system)
    assets = [asset_row(name)]
    if system != 'darwin':
        assets.append(asset_row(name + '.sig'))
    return {'tag_name': updates.release_tag(version), 'assets': assets}


def trust_new_key(tmp_path, monkeypatch, data=DATA):
    """Install a throwaway update key and return a file holding a valid signature for data."""
    seed = eddsa.import_private_key(bytes(range(32)))
    public = tmp_path/'update-public-key'
    public.write_text(base64.b64encode(seed.public_key().export_key(format='raw')).decode())
    monkeypatch.setattr(updates, 'update_public_key', lambda: public)
    signature = tmp_path/'installer.sig'
    signature.write_text(base64.b64encode(eddsa.new(seed, 'rfc8032').sign(data)).decode())
    return signature


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
        row['tag_name'] = 'Tubify-0.3.0'
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
        result = updates.download('Tubify-0.2.0', tmp_path, progress.append, opener)
        assert Path(result['path']).read_bytes() == DATA and progress[-1]['percent'] == 100
    else:
        with pytest.raises(ValueError):
            updates.download('Tubify-0.2.0', tmp_path, progress.append, opener)
        assert not list(tmp_path.iterdir())
    assert calls[1] == updates.BASE+'Tubify-0.2.0/'+release()['assets'][0]['name']


def test_interrupted_download_leaves_no_executable(tmp_path):
    class Broken(io.BytesIO):
        def read(self, size=-1):
            raise OSError('synthetic network failure')
    calls = []
    def opener(*args, **kwargs):
        calls.append(True)
        return io.BytesIO(json.dumps(release(updates.sys.platform)).encode()) if len(calls) == 1 else Broken()
    with pytest.raises(OSError):
        updates.download('Tubify-0.2.0', tmp_path, opener=opener)
    assert not list(tmp_path.iterdir())


def test_daily_checks_and_stale_cache_never_install(tmp_path, monkeypatch):
    app = QCoreApplication.instance() or QCoreApplication([])
    monkeypatch.setattr(updates, 'supported', lambda: True)
    service = maintenance.Maintenance(tmp_path/'cache/release.json', object(), worker_factory=Worker)
    monkeypatch.setattr(maintenance.time, 'time', lambda: 100000.)
    service._check_due()
    worker = service._worker
    assert len(worker.requests) == 1
    worker.succeeded.emit(1, {'tag':'Tubify-9.0.0', 'stale':True})
    assert not service.updateAvailable
    service._check_due()
    assert len(worker.requests) == 1
    service.setAutomaticChecks(False)
    monkeypatch.setattr(maintenance.time, 'time', lambda: 300000.)
    service._check_due()
    assert len(worker.requests) == 1
    service.checkRelease()
    worker.succeeded.emit(2, {'tag':'Tubify-9.0.0'})
    assert service.updateAvailable
    service.close()


def test_linux_auth_cancel_relaunches_without_elevating_gui(tmp_path, monkeypatch):
    package = tmp_path/'package.pkg.tar.zst'
    package.write_bytes(DATA)
    def exited(pid, signal):
        raise ProcessLookupError()
    monkeypatch.setattr(updates.os, 'kill', exited)
    calls = []
    monkeypatch.setattr(updates.subprocess, 'run', lambda argv: calls.append(argv) or SimpleNamespace(returncode=126))
    monkeypatch.setattr(updates.subprocess, 'Popen', lambda argv, **kwargs: calls.append(argv))
    assert updates.install_linux(123, package, hashlib.sha256(DATA).hexdigest()) == 126
    assert calls[0][:3] == ['/usr/bin/pkexec', '--disable-internal-agent', '/usr/bin/pacman']
    assert calls[1] == ['/usr/bin/youtube-music-native']
    assert json.loads((tmp_path/'result.json').read_text()) == {'success':False}


def test_linux_password_fallback_installs_a_private_verified_copy(tmp_path, monkeypatch):
    package = tmp_path/'package.pkg.tar.zst'
    package.write_bytes(DATA)
    monkeypatch.setattr(updates.os, 'kill', lambda pid, signal: (_ for _ in ()).throw(ProcessLookupError()))
    monkeypatch.setattr(updates.subprocess, 'Popen', lambda argv, **kwargs: None)
    installed = []
    def run(argv):
        # Changing the downloaded file after the check must not change what pacman installs.
        package.write_bytes(b'changed')
        copy = Path(argv[-1])
        installed.append((copy, copy.parent.stat().st_mode & 0o777, copy.read_bytes()))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(updates.subprocess, 'run', run)
    assert updates.install_linux(123, package, hashlib.sha256(DATA).hexdigest()) == 0
    copy, mode, data = installed[0]
    assert copy.parent != tmp_path and copy.name == package.name and data == DATA
    if sys.platform != 'win32':
        assert mode == 0o700
    assert not copy.parent.exists()
    monkeypatch.setattr(updates.subprocess, 'run', lambda argv: pytest.fail('A changed package must not install'))
    assert updates.install_linux(123, package, hashlib.sha256(DATA).hexdigest()) == 1


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
    assert 'Tubify-0.2.0/Tubify-0.2.0-macos-arm64.dmg' in result and signature in result
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
    signature = trust_new_key(tmp_path, monkeypatch)
    updates.launch_installer({'path':str(path), 'sha256':hashlib.sha256(DATA).hexdigest(), 'signature_path':str(signature)}, 321)
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


def test_release_lookup_carries_bounded_plain_notes_and_restart_rechecks(tmp_path, monkeypatch):
    rows = [{'tag_name': 'Tubify-0.3.0', 'body': 'Line one\r\n' + 'x' * 3000}, {'tag_name': 'Tubify-0.2.0', 'body': 'old'}]
    result = maintenance.lookup_release(lambda request, timeout: io.BytesIO(json.dumps(rows).encode()))
    assert result['tag'] == 'Tubify-0.3.0' and result['notes'].startswith('Line one\n')
    assert len(result['notes']) <= maintenance.NOTES_LIMIT + 1 and result['notes'].endswith('…')
    app = QCoreApplication.instance() or QCoreApplication([])
    monkeypatch.setattr(updates, 'supported', lambda: True)
    cache = tmp_path/'cache/release.json'
    cache.parent.mkdir()
    cache.write_text(json.dumps({'tag': 'Tubify-99.0.0', 'checkedAt': '2026-01-01T00:00:00+00:00'}))
    service = maintenance.Maintenance(cache, object(), worker_factory=Worker)
    # A cached newer release is re-confirmed at startup instead of trusted.
    assert service._known_newer() and not service.updateAvailable
    service.checkRelease()
    service._worker.succeeded.emit(1, {'tag': 'Tubify-99.0.0', 'notes': 'Header indicator'})
    assert service.updateAvailable and service.latestName == 'Tubify 99.0.0' and service.releaseNotes == 'Header indicator'
    service.close()


def test_third_party_notices_ship_with_the_package():
    notices = Path(maintenance.__file__).resolve().parents[1] / 'assets' / 'THIRD_PARTY_NOTICES.md'
    text = notices.read_text(encoding='utf-8')
    for component in ('PySide6', 'mpv', 'FFmpeg', 'yt-dlp', 'ytmusicapi', 'Sparkle', 'Roboto', 'Lucide', 'mutagen'):
        assert component in text
    assert 'not affiliated' in text


def test_linux_updates_find_only_the_tubify_named_package():
    name = 'Tubify-0.2.1-linux-x86_64.pkg.tar.zst'
    source = {'name': 'Tubify-0.2.1-linux-source.tar.gz', 'digest': 'sha256:' + '0' * 64, 'size': 10}
    row = {'tag_name': 'Tubify-0.2.1', 'assets': [asset_row(name), asset_row(name + '.sig'), source]}
    assert updates.select_asset(row, 'linux')['name'] == name
    old = 'youtube-music-native-0.2.1-1-x86_64.pkg.tar.zst'
    with pytest.raises(ValueError):
        updates.select_asset({'tag_name': 'Tubify-0.2.1', 'assets': [asset_row(old), asset_row(old + '.sig')]}, 'linux')


@pytest.mark.parametrize('system', ['linux', 'win32'])
def test_a_release_without_a_signature_is_refused(system):
    row = release(system)
    del row['assets'][1]
    with pytest.raises(updates.UnsignedUpdate):
        updates.select_asset(row, system)


def test_linux_prefers_the_signature_name_pacman_ignores():
    row = release('linux')
    package = row['assets'][0]['name']
    row['assets'].append(asset_row(package + '.ed25519', SIGNATURE))
    assert updates.select_asset(row, 'linux')['signature']['name'] == package + '.ed25519'
    del row['assets'][1]
    assert updates.select_asset(row, 'linux')['signature']['name'] == package + '.ed25519'


def test_releases_with_only_the_older_signature_name_still_install():
    row = release('linux')
    assert updates.select_asset(row, 'linux')['signature']['name'] == row['assets'][0]['name'] + '.sig'
    assert updates.select_asset(release('win32'), 'win32')['signature']['name'].endswith('.exe.sig')


def test_macos_relies_on_sparkle_rather_than_a_separate_signature():
    assert 'signature' not in updates.select_asset(release('darwin'), 'darwin')


def windows_installer(tmp_path, monkeypatch, data=DATA):
    path = tmp_path/'setup.exe'
    path.write_bytes(data)
    calls = []
    monkeypatch.setattr(updates.sys, 'platform', 'win32')
    monkeypatch.setattr(updates.sys, 'executable', str(tmp_path/'Tubify.exe'))
    monkeypatch.setattr(updates.subprocess, 'Popen', lambda argv, **kwargs: calls.append(argv))
    return {'path': str(path), 'sha256': hashlib.sha256(data).hexdigest()}, calls


def test_windows_runs_an_installer_only_with_a_valid_signature(tmp_path, monkeypatch):
    signature = trust_new_key(tmp_path, monkeypatch)
    asset, calls = windows_installer(tmp_path, monkeypatch)
    updates.launch_installer({**asset, 'signature_path': str(signature)}, 1)
    assert len(calls) == 1


def test_windows_refuses_a_missing_signature(tmp_path, monkeypatch):
    trust_new_key(tmp_path, monkeypatch)
    asset, calls = windows_installer(tmp_path, monkeypatch)
    with pytest.raises(updates.UnsignedUpdate):
        updates.launch_installer(asset, 1)
    assert not calls


def test_windows_refuses_a_bad_signature(tmp_path, monkeypatch):
    signature = trust_new_key(tmp_path, monkeypatch)
    signature.write_text(base64.b64encode(bytes(64)).decode())
    asset, calls = windows_installer(tmp_path, monkeypatch)
    with pytest.raises(updates.UnsignedUpdate):
        updates.launch_installer({**asset, 'signature_path': str(signature)}, 1)
    assert not calls


def test_windows_refuses_a_tampered_installer_even_with_a_matching_hash(tmp_path, monkeypatch):
    signature = trust_new_key(tmp_path, monkeypatch)
    # An attacker who controls the release also controls the hash, so only the signature can catch this.
    asset, calls = windows_installer(tmp_path, monkeypatch, DATA + b'tampered')
    with pytest.raises(updates.UnsignedUpdate):
        updates.launch_installer({**asset, 'signature_path': str(signature)}, 1)
    assert not calls


def test_windows_refuses_a_signature_from_another_key(tmp_path, monkeypatch):
    signature = trust_new_key(tmp_path, monkeypatch)
    other = eddsa.import_private_key(bytes(32))
    (tmp_path/'update-public-key').write_text(base64.b64encode(other.public_key().export_key(format='raw')).decode())
    asset, calls = windows_installer(tmp_path, monkeypatch)
    with pytest.raises(updates.UnsignedUpdate):
        updates.launch_installer({**asset, 'signature_path': str(signature)}, 1)
    assert not calls


def test_unverified_updates_explain_why_they_were_stopped(tmp_path, monkeypatch):
    trust_new_key(tmp_path, monkeypatch)
    asset, calls = windows_installer(tmp_path, monkeypatch)
    result = maintenance.perform({'action': 'install', 'asset': asset, 'parent_pid': 1})
    assert result == {'error': maintenance.UNSIGNED_UPDATE} and not calls
    row = release('win32')
    del row['assets'][1]
    opener = lambda request, timeout: io.BytesIO(json.dumps(row).encode())
    result = maintenance.perform({'action': 'download', 'tag': 'Tubify-0.2.0', 'directory': str(tmp_path/'updates')}, opener)
    assert result == {'error': maintenance.UNSIGNED_UPDATE}


SIGNATURE = b'c2lnbmF0dXJl\n'


def signed_release():
    row = release('linux')
    row['assets'][1] = asset_row(row['assets'][0]['name'] + '.sig', SIGNATURE)
    return row


def test_linux_release_downloads_its_signature_beside_the_package(tmp_path, monkeypatch):
    monkeypatch.setattr(updates.sys, 'platform', 'linux')
    calls = []
    def opener(url, **kwargs):
        calls.append(url)
        return io.BytesIO(json.dumps(signed_release()).encode() if len(calls) == 1 else SIGNATURE if url.endswith('.sig') else DATA)
    result = updates.download('Tubify-0.2.0', tmp_path, opener=opener)
    assert Path(result['signature_path']).read_bytes() == SIGNATURE and Path(result['path']).read_bytes() == DATA
    # A changed signature download leaves nothing that could be installed.
    for item in tmp_path.iterdir():
        item.unlink()
    calls.clear()
    def tampered(url, **kwargs):
        calls.append(url)
        return io.BytesIO(json.dumps(signed_release()).encode() if len(calls) == 1 else b'c2lnbmF0dXJF\n' if url.endswith('.sig') else DATA)
    with pytest.raises(ValueError):
        updates.download('Tubify-0.2.0', tmp_path, opener=tampered)
    assert not list(tmp_path.iterdir())


def test_linux_signed_update_uses_the_passwordless_helper_when_installed(tmp_path, monkeypatch):
    package = tmp_path/'package.pkg.tar.zst'
    package.write_bytes(DATA)
    signature = tmp_path/'package.pkg.tar.zst.sig'
    signature.write_bytes(SIGNATURE)
    helper = tmp_path/'apply-update'
    monkeypatch.setattr(updates.os, 'kill', lambda pid, signal: (_ for _ in ()).throw(ProcessLookupError()))
    calls = []
    monkeypatch.setattr(updates.subprocess, 'run', lambda argv: calls.append(argv) or SimpleNamespace(returncode=0))
    monkeypatch.setattr(updates.subprocess, 'Popen', lambda argv, **kwargs: None)
    monkeypatch.setattr(updates, 'LINUX_HELPER', str(helper))
    # Without the helper, the update still installs with a password prompt.
    assert updates.install_linux(123, package, hashlib.sha256(DATA).hexdigest(), signature) == 0
    assert calls[-1][2] == '/usr/bin/pacman'
    helper.write_text('')
    assert updates.install_linux(123, package, hashlib.sha256(DATA).hexdigest(), signature) == 0
    assert calls[-1] == ['/usr/bin/pkexec', '--disable-internal-agent', str(helper), str(package), str(signature)]
    assert updates.install_linux(123, package, hashlib.sha256(DATA).hexdigest()) == 0
    assert calls[-1][2] == '/usr/bin/pacman'


def test_refused_switch_back_falls_back_to_a_password_but_a_refused_update_does_not(tmp_path, monkeypatch):
    package = tmp_path/'package.pkg.tar.zst'
    package.write_bytes(DATA)
    signature = tmp_path/'package.pkg.tar.zst.sig'
    signature.write_bytes(SIGNATURE)
    helper = tmp_path/'apply-update'
    helper.write_text('')
    monkeypatch.setattr(updates.os, 'kill', lambda pid, signal: (_ for _ in ()).throw(ProcessLookupError()))
    monkeypatch.setattr(updates.subprocess, 'Popen', lambda argv, **kwargs: None)
    monkeypatch.setattr(updates, 'LINUX_HELPER', str(helper))
    digest = hashlib.sha256(DATA).hexdigest()

    def installs(answer, downgrade):
        calls = []
        def run(argv):
            calls.append(argv[2])
            return SimpleNamespace(returncode=answer if argv[2] == str(helper) else 0)
        monkeypatch.setattr(updates.subprocess, 'run', run)
        return updates.install_linux(123, package, digest, signature, downgrade=downgrade), calls

    assert installs(0, True) == (0, [str(helper)])
    assert installs(updates.HELPER_REFUSED, True) == (0, [str(helper), '/usr/bin/pacman'])
    assert installs(updates.HELPER_REFUSED, False) == (updates.HELPER_REFUSED, [str(helper)])
    # Anything else, such as a bad signature or a dismissed prompt, never reaches pacman.
    assert installs(3, True) == (3, [str(helper)])


def test_linux_installer_helper_receives_the_signature(tmp_path, monkeypatch):
    package = tmp_path/'package.pkg.tar.zst'
    package.write_bytes(DATA)
    launched = []
    monkeypatch.setattr(updates.sys, 'platform', 'linux')
    monkeypatch.setattr(updates.subprocess, 'Popen', lambda argv, **kwargs: launched.append(argv))
    signature = trust_new_key(tmp_path, monkeypatch)
    updates.launch_installer({'path': str(package), 'sha256': hashlib.sha256(DATA).hexdigest(), 'signature_path': str(signature)}, 123)
    assert launched[0][-4:] == ['123', str(package), hashlib.sha256(DATA).hexdigest(), str(signature)]
