"""Public release artifacts and OS-owned installation; never handle account data."""
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time
from urllib.request import Request, urlopen

BASE = 'https://github.com/Sayarinu/Tubify/releases/download/'
MAX_DOWNLOAD = 1024 * 1024 * 1024
MAX_SIGNATURE = 4096
# Installed by the Arch package: applies signed updates without a password prompt.
ARCH_HELPER = '/usr/lib/youtube-music-native/apply-update'


def integrity(item, limit):
    digest, size = item.get('digest', ''), item.get('size', 0)
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', digest) or type(size) is not int or not 0 < size <= limit:
        raise ValueError('Release is missing integrity metadata')
    return {'name': item['name'], 'sha256': digest[7:], 'size': size}


def asset_name(version, system=None):
    system = system or sys.platform
    if system == 'win32':
        return f'Tubify-{version}-windows-x64-setup.exe'
    if system == 'darwin':
        return f'Tubify-{version}-macos-arm64.dmg'
    return None


def select_asset(release, system=None):
    system = system or sys.platform
    tag = release.get('tag_name', '')
    if not re.fullmatch(r'native-v\d+\.\d+\.\d+', tag):
        raise ValueError('Invalid Tubify release')
    version = tag.removeprefix('native-v')
    candidates = []
    for item in release.get('assets', []):
        name = item.get('name', '')
        match = name == asset_name(version, system)
        if system == 'linux':
            # Releases from 0.2.1 name the pacman package after Tubify; earlier ones used the package name.
            match = name == f'Tubify-{version}-linux-x86_64.pkg.tar.zst' or bool(
                re.fullmatch(r'youtube-music-native-' + re.escape(version) + r'-\d+-x86_64\.pkg\.tar\.zst', name))
        if match:
            candidates.append({'tag': tag, **integrity(item, MAX_DOWNLOAD)})
    if len(candidates) != 1:
        raise ValueError('Release does not contain one matching installer')
    asset = candidates[0]
    if system == 'linux':
        # Releases before signed Linux packages have no signature; they install with a password.
        signatures = [item for item in release.get('assets', []) if item.get('name') == asset['name'] + '.sig']
        if len(signatures) == 1:
            asset['signature'] = integrity(signatures[0], MAX_SIGNATURE)
    return asset


def supported():
    machine = platform.machine().lower()
    if sys.platform == 'linux':
        # A source/venv launch must never replace the system package.
        root = Path(__file__).resolve()
        if not (root.is_relative_to('/usr/lib') and machine in {'x86_64', 'amd64'} and Path('/usr/bin/pacman').exists() and Path('/usr/bin/pkexec').exists()):
            return False
        try:
            owner = subprocess.run(['/usr/bin/pacman', '-Qqo', str(root)], capture_output=True, text=True, timeout=3)
            return owner.returncode == 0 and owner.stdout.strip() == 'youtube-music-native'
        except (OSError, subprocess.TimeoutExpired):
            return False
    if not getattr(sys, 'frozen', False):
        return False
    return (sys.platform == 'win32' and machine in {'amd64', 'x86_64'}) or (sys.platform == 'darwin' and machine == 'arm64')


def download(tag, directory, progress=None, opener=urlopen):
    """Re-fetch release metadata so an offline cache can never authorize execution."""
    if not re.fullmatch(r'native-v\d+\.\d+\.\d+', tag):
        raise ValueError('Invalid Tubify release')
    request = Request('https://api.github.com/repos/Sayarinu/Tubify/releases/tags/' + tag,
                      headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'Tubify-updater'})
    with opener(request, timeout=15) as response:
        raw = response.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError('Release response too large')
    release = json.loads(raw)
    if release.get('draft') or release.get('prerelease') or release.get('tag_name') != tag:
        raise ValueError('Release unavailable')
    asset = select_asset(release)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = fetch(tag, asset, directory, progress, opener)
    result = {**asset, 'path': str(target)}
    if 'signature' in asset:
        try:
            result['signature_path'] = str(fetch(tag, asset['signature'], directory, None, opener))
        except BaseException:
            target.unlink(missing_ok=True)
            raise
    return result


def fetch(tag, asset, directory, progress, opener):
    target = directory / asset['name']
    partial = target.with_suffix(target.suffix + '.part')
    digest, count = hashlib.sha256(), 0
    try:
        with opener(BASE + tag + '/' + asset['name'], timeout=30) as response, partial.open('wb') as out:
            while chunk := response.read(256 * 1024):
                count += len(chunk)
                if count > asset['size']:
                    raise ValueError('Download exceeded expected size')
                out.write(chunk)
                digest.update(chunk)
                if progress:
                    progress({'percent': int(100 * count / asset['size'])})
        if count != asset['size'] or digest.hexdigest() != asset['sha256']:
            raise ValueError('Download integrity check failed')
        partial.replace(target)
        return target
    finally:
        partial.unlink(missing_ok=True)


def launch_installer(asset, parent_pid):
    path = Path(asset['path']).resolve()
    with path.open('rb') as handle:
        if hashlib.file_digest(handle, 'sha256').hexdigest() != asset['sha256']:
            raise ValueError('Installer integrity check failed')
    if sys.platform == 'win32':
        subprocess.Popen([str(path), '/SILENT', '/SP-', '/NORESTART', '/NOCLOSEAPPLICATIONS',
                          '/TUBIFYUPDATE=1', f'/UPDATEPID={parent_pid}', f'/DIR={Path(sys.executable).parent}'])
    elif sys.platform == 'linux':
        # Copy before package replacement: the helper survives GUI/worker shutdown.
        helper = path.parent / 'install.py'
        shutil.copyfile(__file__, helper)
        signature = [asset['signature_path']] if asset.get('signature_path') else []
        subprocess.Popen([sys.executable, '-I', str(helper), str(parent_pid), str(path), asset['sha256'], *signature],
                         start_new_session=True, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        raise ValueError('Use the macOS updater')


def install_arch(parent, package, digest, signature=None):
    for _ in range(120):
        try:
            os.kill(parent, 0)
        except ProcessLookupError:
            break
        time.sleep(.5)
    else:
        return 1
    path = Path(package)
    result = 1
    try:
        with path.open('rb') as handle:
            if hashlib.file_digest(handle, 'sha256').hexdigest() != digest:
                raise ValueError('Installer changed')
        if signature and Path(ARCH_HELPER).is_file():
            # The helper checks the release signature as root, so polkit allows it without a password.
            command = [ARCH_HELPER, str(path), str(signature)]
        else:
            command = ['/usr/bin/pacman', '-U', '--noconfirm', str(path)]
        result = subprocess.run(['/usr/bin/pkexec', '--disable-internal-agent', *command]).returncode
    except (OSError, ValueError):
        pass
    finally:
        (path.parent / 'result.json').write_text(json.dumps({'success': result == 0}))
        subprocess.Popen(['/usr/bin/youtube-music-native'], start_new_session=True)
    return result


if __name__ == '__main__':
    raise SystemExit(install_arch(int(sys.argv[1]), sys.argv[2], sys.argv[3], *sys.argv[4:5]))
