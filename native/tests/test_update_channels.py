import base64
import hashlib
import importlib.util
import io
import json
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication

from youtube_music_native.updates import maintenance

from youtube_music_native.updates import updates
from test_maintenance import Worker
from test_updates import trust_new_key

DATA = b'synthetic package'


def rows(*releases):
    return [{'tag_name': tag, 'prerelease': pre, 'draft': draft, 'body': 'Notes for ' + tag} for tag, pre, draft in releases]


def opener(data):
    return lambda request, timeout: io.BytesIO(json.dumps(data).encode())


def test_versions_order_experimental_builds_before_their_stable_release():
    ordered = ['0.6.0', '0.7.0b1', '0.7.0b2', '0.7.0b10', '0.7.0', '0.7.1b1', '1.0.0']
    assert sorted(reversed(ordered), key=updates.version_key) == ordered
    assert updates.version_key('Tubify-Experimental-0.7.0b2') == updates.version_key('0.7.0b2')
    for bad in ('0.7', '0.7.0-rc1', '0.7.0b', 'Tubify-Experimental-0.7.0b1x', None, 7):
        assert updates.version_key(bad) is None
    assert updates.release_name('0.7.0b3') == 'Tubify Experimental 0.7.0b3'
    assert updates.release_name('Tubify-0.7.0') == 'Tubify 0.7.0' and updates.release_name('junk') == 'Tubify'
    assert updates.is_experimental('0.7.0b1') and not updates.is_experimental('0.7.0')


def test_stable_channel_never_sees_prereleases_and_experimental_takes_the_newest():
    listing = rows(('Tubify-Experimental-0.7.0b2', True, False), ('Tubify-0.6.0', False, False), ('Tubify-Experimental-0.7.0b3', True, True),
                   ('Tubify-Experimental-0.8.0b1', False, False), ('Tubify-0.6.1', True, False), ('Tubify-bad', False, False))
    assert maintenance.lookup_release(opener(listing))['tag'] == 'Tubify-0.6.0'
    result = maintenance.lookup_release(opener(listing), 'experimental')
    assert result['tag'] == 'Tubify-Experimental-0.7.0b2' and result['channel'] == 'experimental'
    # Once the stable release lands it outranks its experimental builds.
    listing += rows(('Tubify-0.7.0', False, False))
    assert maintenance.lookup_release(opener(listing), 'experimental')['tag'] == 'Tubify-0.7.0'
    with pytest.raises(ValueError):
        maintenance.lookup_release(opener(rows(('Tubify-Experimental-0.7.0b1', True, False))))


def test_downloads_require_prerelease_flags_to_match_the_tag(tmp_path, monkeypatch):
    monkeypatch.setattr(updates.sys, 'platform', 'linux')
    def release(tag, prerelease):
        version = updates.tag_version(tag)
        name = f'Tubify-{version}-linux-x86_64.pkg.tar.zst'
        row = {'size': len(DATA), 'digest': 'sha256:' + hashlib.sha256(DATA).hexdigest()}
        body = {'tag_name': tag, 'prerelease': prerelease, 'assets': [{'name': name, **row}, {'name': name + '.sig', **row}]}
        def fetch(request, timeout):
            url = request if isinstance(request, str) else request.full_url
            return io.BytesIO(DATA if url.endswith(('.zst', '.sig')) else json.dumps(body).encode())
        return fetch
    assert updates.download('Tubify-Experimental-0.7.0b1', tmp_path, opener=release('Tubify-Experimental-0.7.0b1', True))['name'] == 'Tubify-0.7.0b1-linux-x86_64.pkg.tar.zst'
    for tag, prerelease in (('Tubify-Experimental-0.7.0b1', False), ('Tubify-0.7.0', True)):
        with pytest.raises(ValueError):
            updates.download(tag, tmp_path, opener=release(tag, prerelease))
    with pytest.raises(ValueError):
        updates.download('Tubify-0.7.0-evil', tmp_path, opener=release('Tubify-0.7.0', False))


def test_switching_back_to_stable_offers_the_helper_and_marks_the_downgrade(tmp_path, monkeypatch):
    package = tmp_path / 'package.pkg.tar.zst'
    package.write_bytes(DATA)
    launched = []
    monkeypatch.setattr(updates.sys, 'platform', 'linux')
    monkeypatch.setattr(updates.subprocess, 'Popen', lambda argv, **kwargs: launched.append(argv))
    asset = {'path': str(package), 'sha256': hashlib.sha256(DATA).hexdigest(), 'signature_path': str(trust_new_key(tmp_path, monkeypatch))}
    updates.launch_installer({**asset, 'downgrade': True}, 123)
    assert launched[0][-5:] == ['123', str(package), hashlib.sha256(DATA).hexdigest(), asset['signature_path'], 'downgrade']
    updates.launch_installer(asset, 123)
    assert launched[1][-4:] == ['123', str(package), hashlib.sha256(DATA).hexdigest(), asset['signature_path']]


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
    item._worker.succeeded.emit(1, {'tag': 'Tubify-Experimental-0.7.0b1', 'notes': 'Try it'})
    assert item.updateAvailable and item.switchingChannel and not item.downgrading and item.latestName == 'Tubify Experimental 0.7.0b1' and item.status == 'Tubify Experimental 0.7.0b1 is available to switch to Experimental.'
    # A newer build goes through the password-free helper.
    item.installUpdate()
    item._worker.succeeded.emit(2, {'tag': 'Tubify-Experimental-0.7.0b1', 'notes': 'Try it'})
    item._worker.succeeded.emit(3, {'name': 'x.pkg.tar.zst', 'path': '/tmp/x', 'sha256': '0' * 64, 'size': 1})
    assert item._worker.requests[-1][1]['asset']['downgrade'] is False
    item.close()

    # On the experimental channel, updating between experimental builds isn't a switch, and neither is a newer stable release for a stable build.
    for installed, tag in (('0.7.0b1', 'Tubify-Experimental-0.7.0b2'), ('0.6.0', 'Tubify-0.7.0')):
        item = service(tmp_path / installed, monkeypatch, installed, 'experimental')
        item.checkRelease()
        item._worker.succeeded.emit(1, {'tag': tag})
        assert item.updateAvailable and not item.switchingChannel and not item.downgrading
        item.close()

    item = service(tmp_path / 'back', monkeypatch, '0.7.0b1', 'stable')
    item.checkRelease()
    item._worker.succeeded.emit(1, {'tag': 'Tubify-0.6.0', 'notes': 'Stable'})
    assert item.updateAvailable and item.switchingChannel and item.downgrading and item.latestName == 'Tubify 0.6.0' and item.status == 'Tubify 0.6.0 is available to switch to Stable.'
    # The download is marked as a downgrade, so Linux can fall back to a password if the helper refuses it.
    item.installUpdate()
    item._worker.succeeded.emit(2, {'tag': 'Tubify-0.6.0', 'notes': 'Stable'})
    item._worker.succeeded.emit(3, {'name': 'Tubify-0.6.0-linux-x86_64.pkg.tar.zst', 'path': '/tmp/x', 'sha256': '0' * 64, 'size': 1})
    assert item._worker.requests[-1] == ('maintenance', {'action': 'install', 'asset': {'name': 'Tubify-0.6.0-linux-x86_64.pkg.tar.zst', 'path': '/tmp/x', 'sha256': '0' * 64, 'size': 1, 'downgrade': True}, 'parent_pid': item._worker.requests[-1][1]['parent_pid']})
    item.close()

    # A stable build on the stable channel is never offered an older release.
    item = service(tmp_path / 'stable', monkeypatch, '0.7.0', 'stable')
    item.checkRelease()
    item._worker.succeeded.emit(1, {'tag': 'Tubify-0.6.0'})
    assert not item.updateAvailable
    item.close()


@pytest.mark.parametrize('installed,channel,due', [
    ('0.7.0', 'experimental', True),
    ('0.7.0b1', 'stable', True),
    ('0.7.0', 'stable', False),
    ('0.7.0b1', 'experimental', False),
])
def test_a_chosen_switch_is_offered_again_after_a_restart(tmp_path, monkeypatch, installed, channel, due):
    item = service(tmp_path, monkeypatch, installed, channel)
    # With automatic checks off, and a check moments ago, only the switch still looks for a release.
    item.setAutomaticChecks(False)
    item.settings.setValue('updates/lastAttempt', maintenance.time.time())
    scheduled = []
    monkeypatch.setattr(maintenance.QTimer, 'singleShot', lambda delay, action: scheduled.append(action))
    item.start()
    scheduled[0]()
    assert bool(item._worker and item._worker.requests) == due
    item.close()


def test_mac_switching_back_points_to_the_download(tmp_path, monkeypatch):
    item = service(tmp_path, monkeypatch, '0.7.0b1', 'stable')
    monkeypatch.setattr(maintenance.sys, 'platform', 'darwin')
    item.checkRelease()
    item._worker.succeeded.emit(1, {'tag': 'Tubify-0.6.0'})
    item.installUpdate()
    item._worker.succeeded.emit(2, {'tag': 'Tubify-0.6.0'})
    assert 'download it from Release Details' in item.status and item._worker.requests[-1][1]['action'] == 'release'
    item.close()


def offered(tmp_path, monkeypatch, installed, channel, tag):
    """A service showing an offer for ``tag``, with the update button just clicked."""
    monkeypatch.setattr(maintenance.sys, 'platform', 'linux')
    item = service(tmp_path, monkeypatch, installed, channel)
    item.checkRelease()
    item._worker.succeeded.emit(1, {'tag': tag})
    assert item.updateAvailable
    item.installUpdate()
    assert item._worker.requests[-1][1] == {'action': 'release', 'cache_path': item._cache, 'channel': channel} and item.updateAvailable and item.busy
    return item


@pytest.mark.parametrize('installed,channel,waiting,newest', [
    # An older stable offer made before a newer stable release shipped must not move the app backwards.
    ('0.8.3b5', 'stable', 'Tubify-0.8.2', 'Tubify-0.8.3'),
    ('0.7.0b1', 'experimental', 'Tubify-Experimental-0.7.0b2', 'Tubify-Experimental-0.7.0b3'),
])
def test_clicking_update_installs_the_newest_release_not_the_waiting_offer(tmp_path, monkeypatch, installed, channel, waiting, newest):
    item = offered(tmp_path, monkeypatch, installed, channel, waiting)
    item._worker.succeeded.emit(2, {'tag': newest, 'notes': 'Newest'})
    action = item._worker.requests[-1][1]
    assert action['action'] == 'download' and action['tag'] == newest
    assert not item.downgrading and item.latestName == updates.release_name(newest) and item.releaseNotes == 'Newest'
    item.close()


@pytest.mark.parametrize('failure', [
    {'error': 'Release information is unavailable.'},
    {'tag': 'Tubify-0.8.2', 'checkedAt': '2026-01-01T00:00:00+00:00', 'stale': True},
    {'tag': 'not-a-release'},
])
def test_a_failed_lookup_installs_nothing_and_keeps_the_offer_to_retry(tmp_path, monkeypatch, failure):
    item = offered(tmp_path, monkeypatch, '0.8.3b5', 'stable', 'Tubify-0.8.2')
    item._worker.succeeded.emit(2, failure)
    assert len(item._worker.requests) == 2 and item.updateAvailable and not item.busy
    # Clicking again looks up again.
    item.installUpdate()
    item._worker.succeeded.emit(3, {'tag': 'Tubify-0.8.3'})
    assert item._worker.requests[-1][1]['action'] == 'download' and item._worker.requests[-1][1]['tag'] == 'Tubify-0.8.3'
    item.close()


def test_an_ordinary_check_after_a_failed_click_does_not_install(tmp_path, monkeypatch):
    item = offered(tmp_path, monkeypatch, '0.8.3b5', 'stable', 'Tubify-0.8.2')
    item._worker.succeeded.emit(2, {'error': 'Release information is unavailable.'})
    item.checkRelease()
    item._worker.succeeded.emit(3, {'tag': 'Tubify-0.8.3'})
    assert item.updateAvailable and item._worker.requests[-1][1]['action'] == 'release'
    item.close()


def test_a_click_with_nothing_newer_left_withdraws_the_offer(tmp_path, monkeypatch):
    item = offered(tmp_path, monkeypatch, '0.7.0b1', 'experimental', 'Tubify-Experimental-0.7.0b2')
    item._worker.succeeded.emit(2, {'tag': 'Tubify-Experimental-0.7.0b1'})
    assert len(item._worker.requests) == 2 and not item.updateAvailable and item.status.startswith('You have the latest')
    item.close()


def test_sparkle_gets_the_newest_release_after_a_click(tmp_path, monkeypatch):
    item = offered(tmp_path, monkeypatch, '0.7.0', 'stable', 'Tubify-0.7.1')
    monkeypatch.setattr(maintenance.sys, 'platform', 'darwin')
    installed = []
    item._mac = type('Mac', (), {'install': lambda self, tag: installed.append(tag)})()
    item._worker.succeeded.emit(2, {'tag': 'Tubify-0.7.2'})
    assert installed == ['Tubify-0.7.2'] and len(item._worker.requests) == 2
    item.close()


def test_stale_cache_never_shows_experimental_builds_on_stable(tmp_path):
    cache = tmp_path / 'release.json'
    cache.write_text(json.dumps({'tag': 'Tubify-Experimental-0.7.0b1', 'channel': 'experimental', 'checkedAt': '2026-01-01T00:00:00+00:00'}))
    def offline(request, timeout):
        raise OSError('offline')
    assert maintenance.perform({'action': 'release', 'cache_path': str(cache), 'channel': 'experimental'}, offline)['stale']
    assert 'error' in maintenance.perform({'action': 'release', 'cache_path': str(cache), 'channel': 'stable'}, offline)
    # Stable lookups, including caches from before channels existed, also answer for experimental.
    for cached in ({'tag': 'Tubify-0.6.0', 'channel': 'stable'}, {'tag': 'Tubify-0.6.0'}):
        cache.write_text(json.dumps({**cached, 'checkedAt': '2026-01-01T00:00:00+00:00'}))
        for channel in ('stable', 'experimental'):
            assert maintenance.perform({'action': 'release', 'cache_path': str(cache), 'channel': channel}, offline)['stale']


def test_a_known_update_survives_upgrading_to_an_experimental_build(tmp_path, monkeypatch):
    item = service(tmp_path, monkeypatch, '0.7.0b1')
    cache = tmp_path / 'cache/release.json'
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({'tag': 'Tubify-99.0.0', 'checkedAt': '2026-01-01T00:00:00+00:00'}))
    assert item.channel == 'experimental' and item._known_newer()
    cache.write_text(json.dumps({'tag': 'Tubify-Experimental-99.0.0b1', 'channel': 'experimental', 'checkedAt': '2026-01-01T00:00:00+00:00'}))
    item.setChannel('stable')
    assert not item._known_newer()
    item.close()


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
    assert 'Tubify-Experimental-0.7.0b2/Tubify-0.7.0b2-macos-arm64.dmg' in result and '>0.7.0b2<' in result


def test_every_release_uses_a_tubify_tag():
    assert updates.release_tag('0.7.1b1') == 'Tubify-Experimental-0.7.1b1'
    assert updates.release_tag('0.7.1') == 'Tubify-0.7.1'
    assert updates.release_tag('1.0.0') == 'Tubify-1.0.0'
    for bad in ('Tubify-0.7.1', '0.7', 'latest'):
        with pytest.raises(ValueError):
            updates.release_tag(bad)


def test_tags_parse_and_must_match_their_channel():
    assert updates.tag_version('Tubify-0.7.1') == '0.7.1' and updates.tag_version('Tubify-Experimental-0.7.0b2') == '0.7.0b2'
    for bad in ('native-v0.7.1', 'Tubify-0.7.1b1', 'Tubify-Experimental-0.7.1', 'tubify-0.7.1', 'Tubify-0.7.1/../x', 'Tubify-v0.7.1'):
        assert updates.tag_version(bad) is None and updates.version_key(bad) is None
    assert updates.version_key('Tubify-Experimental-0.7.1b1') < updates.version_key('Tubify-0.7.1') < updates.version_key('Tubify-Experimental-0.7.2b1')
    assert updates.version_key('Tubify-0.7.0') < updates.version_key('Tubify-Experimental-0.7.1b1')
    assert updates.release_name('Tubify-Experimental-0.7.1b1') == 'Tubify Experimental 0.7.1b1'
    assert updates.release_name('Tubify-0.7.1') == 'Tubify 0.7.1'


def test_channels_and_downloads_use_the_release_tags(tmp_path, monkeypatch):
    listing = rows(('Tubify-0.7.1', False, False), ('Tubify-0.7.0', False, False), ('Tubify-Experimental-0.7.2b1', True, False),
                   ('Tubify-Experimental-0.7.0b4', True, False), ('Tubify-0.7.2b1', True, False))
    assert maintenance.lookup_release(opener(listing))['tag'] == 'Tubify-0.7.1'
    assert maintenance.lookup_release(opener(listing), 'experimental')['tag'] == 'Tubify-Experimental-0.7.2b1'
    monkeypatch.setattr(updates.sys, 'platform', 'linux')
    name = 'Tubify-0.7.1-linux-x86_64.pkg.tar.zst'
    row = {'size': len(DATA), 'digest': 'sha256:' + hashlib.sha256(DATA).hexdigest()}
    body = {'tag_name': 'Tubify-0.7.1', 'prerelease': False, 'assets': [{'name': name, **row}, {'name': name + '.sig', **row}]}
    urls = []
    def fetch(request, timeout):
        url = request if isinstance(request, str) else request.full_url
        urls.append(url)
        return io.BytesIO(DATA if url.endswith(('.zst', '.sig')) else json.dumps(body).encode())
    assert updates.download('Tubify-0.7.1', tmp_path, opener=fetch)['name'] == name
    assert urls == ['https://api.github.com/repos/Sayarinu/Tubify/releases/tags/Tubify-0.7.1', updates.BASE + 'Tubify-0.7.1/' + name, updates.BASE + 'Tubify-0.7.1/' + name + '.sig']


def test_appcast_points_at_the_release_tag(tmp_path):
    module = Path(__file__).resolve().parents[2] / 'scripts/native-appcast.py'
    if not module.exists():
        pytest.skip('release tooling is not part of this source tree')
    spec = importlib.util.spec_from_file_location('appcast_tags', module)
    code = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(code)
    signature = base64.b64encode(b's' * 64).decode()
    for version, tag in (('0.7.0', 'Tubify-0.7.0'), ('0.7.1', 'Tubify-0.7.1'), ('0.7.1b2', 'Tubify-Experimental-0.7.1b2')):
        archive = tmp_path / f'Tubify-{version}-macos-arm64.dmg'
        archive.write_bytes(DATA)
        assert f'releases/download/{tag}/Tubify-{version}-macos-arm64.dmg' in code.appcast(version, archive, signature).decode()
