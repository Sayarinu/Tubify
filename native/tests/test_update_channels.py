import base64
import hashlib
import importlib.util
import io
import json
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication

from youtube_music_native import maintenance, updates
from test_maintenance import Worker

DATA = b'synthetic package'


def rows(*releases):
    return [{'tag_name': tag, 'prerelease': pre, 'draft': draft, 'body': 'Notes for ' + tag} for tag, pre, draft in releases]


def opener(data):
    return lambda request, timeout: io.BytesIO(json.dumps(data).encode())


def test_versions_order_experimental_builds_before_their_stable_release():
    ordered = ['0.6.0', '0.7.0b1', '0.7.0b2', '0.7.0b10', '0.7.0', '0.7.1b1', '1.0.0']
    assert sorted(reversed(ordered), key=updates.version_key) == ordered
    assert updates.version_key('native-v0.7.0b2') == updates.version_key('0.7.0b2')
    for bad in ('0.7', '0.7.0-rc1', '0.7.0b', 'native-v0.7.0b1x', None, 7):
        assert updates.version_key(bad) is None
    assert updates.release_name('0.7.0b3') == 'Tubify Experimental 0.7.0b3'
    assert updates.release_name('native-v0.7.0') == 'Tubify 0.7.0' and updates.release_name('junk') == 'Tubify'
    assert updates.is_experimental('0.7.0b1') and not updates.is_experimental('0.7.0')


def test_stable_channel_never_sees_prereleases_and_experimental_takes_the_newest():
    listing = rows(('native-v0.7.0b2', True, False), ('native-v0.6.0', False, False), ('native-v0.7.0b3', True, True),
                   ('native-v0.8.0b1', False, False), ('native-v0.6.1', True, False), ('native-vbad', False, False))
    assert maintenance.lookup_release(opener(listing))['tag'] == 'native-v0.6.0'
    result = maintenance.lookup_release(opener(listing), 'experimental')
    assert result['tag'] == 'native-v0.7.0b2' and result['channel'] == 'experimental'
    # Once the stable release lands it outranks its experimental builds.
    listing += rows(('native-v0.7.0', False, False))
    assert maintenance.lookup_release(opener(listing), 'experimental')['tag'] == 'native-v0.7.0'
    with pytest.raises(ValueError):
        maintenance.lookup_release(opener(rows(('native-v0.7.0b1', True, False))))


def test_downloads_require_prerelease_flags_to_match_the_tag(tmp_path, monkeypatch):
    monkeypatch.setattr(updates.sys, 'platform', 'linux')
    def release(tag, prerelease):
        version = tag.removeprefix('native-v')
        name = f'Tubify-{version}-linux-x86_64.pkg.tar.zst'
        body = {'tag_name': tag, 'prerelease': prerelease, 'assets': [{'name': name, 'size': len(DATA), 'digest': 'sha256:' + hashlib.sha256(DATA).hexdigest()}]}
        def fetch(request, timeout):
            url = request if isinstance(request, str) else request.full_url
            return io.BytesIO(DATA if url.endswith('.zst') else json.dumps(body).encode())
        return fetch
    assert updates.download('native-v0.7.0b1', tmp_path, opener=release('native-v0.7.0b1', True))['name'] == 'Tubify-0.7.0b1-linux-x86_64.pkg.tar.zst'
    for tag, prerelease in (('native-v0.7.0b1', False), ('native-v0.7.0', True)):
        with pytest.raises(ValueError):
            updates.download(tag, tmp_path, opener=release(tag, prerelease))
    with pytest.raises(ValueError):
        updates.download('native-v0.7.0-evil', tmp_path, opener=release('native-v0.7.0', False))


def test_switching_back_to_stable_skips_the_newer_only_helper(tmp_path, monkeypatch):
    package = tmp_path / 'package.pkg.tar.zst'
    package.write_bytes(DATA)
    launched = []
    monkeypatch.setattr(updates.sys, 'platform', 'linux')
    monkeypatch.setattr(updates.subprocess, 'Popen', lambda argv, **kwargs: launched.append(argv))
    asset = {'path': str(package), 'sha256': hashlib.sha256(DATA).hexdigest(), 'signature_path': str(tmp_path / 'package.sig')}
    updates.launch_installer({**asset, 'downgrade': True}, 123)
    assert launched[0][-3:] == ['123', str(package), hashlib.sha256(DATA).hexdigest()]


def service(tmp_path, monkeypatch, installed, channel=None):
    QCoreApplication.instance() or QCoreApplication([])
    monkeypatch.setattr(updates, 'supported', lambda: True)
    monkeypatch.setattr(maintenance, 'installed_version', lambda: installed)
    from youtube_music_native.shell import ShellController
    shell = ShellController(tmp_path / 'config/settings.ini')
    if channel:
        shell.settings.setValue('updates/channel', channel)
    return maintenance.Maintenance(tmp_path / 'cache/release.json', shell, worker_factory=Worker)


def test_channel_defaults_follow_the_installed_build_and_persist(tmp_path, monkeypatch):
    stable = service(tmp_path / 'a', monkeypatch, '0.6.0')
    assert stable.channel == 'stable' and stable.versionName == 'Tubify 0.6.0'
    experimental = service(tmp_path / 'b', monkeypatch, '0.7.0b2')
    assert experimental.channel == 'experimental' and experimental.versionName == 'Tubify Experimental 0.7.0b2'
    stable.setChannel('experimental')
    assert stable.settings.value('updates/channel') == 'experimental'
    assert stable._worker.requests[-1][1]['channel'] == 'experimental'
    stable.setChannel('nightly')
    assert stable.channel == 'experimental'
    for item in (stable, experimental):
        item.close()


def test_experimental_channel_offers_newer_builds_and_stable_offers_the_way_back(tmp_path, monkeypatch):
    # Linux and Windows install through the downloaded package; macOS is covered separately.
    monkeypatch.setattr(maintenance.sys, 'platform', 'linux')
    item = service(tmp_path, monkeypatch, '0.6.0', 'experimental')
    item.checkRelease()
    item._worker.succeeded.emit(1, {'tag': 'native-v0.7.0b1', 'notes': 'Try it'})
    assert item.updateAvailable and not item.switchingChannel and item.latestName == 'Tubify Experimental 0.7.0b1' and item.status == 'Tubify Experimental 0.7.0b1 is available.'
    item.close()

    item = service(tmp_path / 'back', monkeypatch, '0.7.0b1', 'stable')
    item.checkRelease()
    item._worker.succeeded.emit(1, {'tag': 'native-v0.6.0', 'notes': 'Stable'})
    assert item.updateAvailable and item.switchingChannel and item.latestName == 'Tubify 0.6.0' and item.status == 'Tubify 0.6.0 is available to switch back to Stable.'
    # The download is installed as a downgrade so Linux never uses the newer-only helper.
    item.installUpdate()
    item._worker.succeeded.emit(2, {'name': 'Tubify-0.6.0-linux-x86_64.pkg.tar.zst', 'path': '/tmp/x', 'sha256': '0' * 64, 'size': 1})
    assert item._worker.requests[-1] == ('maintenance', {'action': 'install', 'asset': {'name': 'Tubify-0.6.0-linux-x86_64.pkg.tar.zst', 'path': '/tmp/x', 'sha256': '0' * 64, 'size': 1, 'downgrade': True}, 'parent_pid': item._worker.requests[-1][1]['parent_pid']})
    item.close()

    # A stable build on the stable channel is never offered an older release.
    item = service(tmp_path / 'stable', monkeypatch, '0.7.0', 'stable')
    item.checkRelease()
    item._worker.succeeded.emit(1, {'tag': 'native-v0.6.0'})
    assert not item.updateAvailable
    item.close()


def test_mac_switching_back_points_to_the_download(tmp_path, monkeypatch):
    item = service(tmp_path, monkeypatch, '0.7.0b1', 'stable')
    monkeypatch.setattr(maintenance.sys, 'platform', 'darwin')
    item.checkRelease()
    item._worker.succeeded.emit(1, {'tag': 'native-v0.6.0'})
    item.installUpdate()
    assert 'download it from Release Details' in item.status and item._worker.requests[-1][1]['action'] == 'release'
    item.close()


def test_stale_cache_is_only_used_for_the_same_channel(tmp_path):
    cache = tmp_path / 'release.json'
    cache.write_text(json.dumps({'tag': 'native-v0.7.0b1', 'channel': 'experimental', 'checkedAt': '2026-01-01T00:00:00+00:00'}))
    def offline(request, timeout):
        raise OSError('offline')
    assert maintenance.perform({'action': 'release', 'cache_path': str(cache), 'channel': 'experimental'}, offline)['stale']
    assert 'error' in maintenance.perform({'action': 'release', 'cache_path': str(cache), 'channel': 'stable'}, offline)


def test_appcast_accepts_experimental_versions(tmp_path):
    module = Path(__file__).resolve().parents[2] / 'scripts/native-appcast.py'
    if not module.exists():
        pytest.skip('release tooling is not part of this source tree')
    spec = importlib.util.spec_from_file_location('appcast', module)
    code = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(code)
    archive = tmp_path / 'Tubify-0.7.0b2-macos-arm64.dmg'
    archive.write_bytes(DATA)
    result = code.appcast('0.7.0b2', archive, base64.b64encode(b's' * 64).decode()).decode()
    assert 'native-v0.7.0b2/Tubify-0.7.0b2-macos-arm64.dmg' in result and '>0.7.0b2<' in result
