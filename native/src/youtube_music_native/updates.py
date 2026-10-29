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

BASE = 'https://github.com/Sayarinu/YouTube-Music-App/releases/download/'
MAX_DOWNLOAD = 1024 * 1024 * 1024


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
        raise ValueError('Invalid native release')
    version = tag.removeprefix('native-v')
    candidates = []
    for item in release.get('assets', []):
        name = item.get('name', '')
        match = name == asset_name(version, system)
        if system == 'linux':
            match = bool(re.fullmatch(r'youtube-music-native-' + re.escape(version) + r'-\d+-x86_64\.pkg\.tar\.zst', name))
        if match:
            digest, size = item.get('digest', ''), item.get('size', 0)
            if not re.fullmatch(r'sha256:[0-9a-f]{64}', digest) or type(size) is not int or not 0 < size <= MAX_DOWNLOAD:
                raise ValueError('Release is missing integrity metadata')
            candidates.append({'tag': tag, 'name': name, 'sha256': digest[7:], 'size': size})
    if len(candidates) != 1:
        raise ValueError('Release does not contain one matching installer')
    return candidates[0]


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
        raise ValueError('Invalid native release')
    request = Request('https://api.github.com/repos/Sayarinu/YouTube-Music-App/releases/tags/' + tag,
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
        return {**asset, 'path': str(target)}
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
        subprocess.Popen([sys.executable, '-I', str(helper), str(parent_pid), str(path), asset['sha256']],
                         start_new_session=True, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        raise ValueError('Use the macOS updater')


def install_arch(parent, package, digest):
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
        result = subprocess.run(['/usr/bin/pkexec', '--disable-internal-agent', '/usr/bin/pacman', '-U', '--noconfirm', str(path)]).returncode
    except (OSError, ValueError):
        pass
    finally:
        (path.parent / 'result.json').write_text(json.dumps({'success': result == 0}))
        subprocess.Popen(['/usr/bin/youtube-music-native'], start_new_session=True)
    return result


if __name__ == '__main__':
    raise SystemExit(install_arch(int(sys.argv[1]), sys.argv[2], sys.argv[3]))
