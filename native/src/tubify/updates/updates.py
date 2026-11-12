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
# pacman reads <package>.sig as a GPG signature, so Linux packages use .ed25519.
# Linux .sig stays until no 0.8.1 installs, which only look for that name, remain.
SIGNATURE_SUFFIXES = ('.ed25519', '.sig')
# Installed by the Linux package: applies signed updates without a password prompt.
LINUX_HELPER = '/usr/lib/tubify/apply-update'
LINUX_PUBLIC_KEY = '/usr/lib/tubify/update-public-key'
# The helper's answer when a build is older than it may install without a password.
HELPER_REFUSED = 5
# Release tags: Tubify-X.Y.Z (stable) and Tubify-Experimental-X.Y.ZbN (experimental).
VERSION = re.compile(r'(\d+)\.(\d+)\.(\d+)(?:b(\d+))?')
STABLE_TAG = re.compile(r'Tubify-(\d+\.\d+\.\d+)')
EXPERIMENTAL_TAG = re.compile(r'Tubify-Experimental-(\d+\.\d+\.\d+b\d+)')


def tag_version(tag):
    """The version a release tag names, or None. Tubify- tags must agree with the version's channel."""
    if not isinstance(tag, str):
        return None
    for pattern in (STABLE_TAG, EXPERIMENTAL_TAG):
        match = pattern.fullmatch(tag)
        if match:
            return match.group(1)
    return None


def version_key(value):
    """Sortable (X, Y, Z, stable?, N): 0.7.0 < 0.7.1b1 < 0.7.1b2 < 0.7.1; None if invalid. Accepts versions and tags."""
    if not isinstance(value, str):
        return None
    match = VERSION.fullmatch(tag_version(value) or value)
    if not match:
        return None
    major, minor, patch, build = match.groups()
    return (int(major), int(minor), int(patch), 0 if build else 1, int(build or 0))


def is_experimental(value):
    key = version_key(value)
    return bool(key and key[3] == 0)


def release_tag(version):
    """The tag a version is released under; the one rule shared by CI, the appcast and the app."""
    key = version_key(version)
    if not key or tag_version(version):
        raise ValueError('Invalid Tubify version: ' + str(version))
    return ('Tubify-Experimental-' if key[3] == 0 else 'Tubify-') + version


def release_name(value):
    """What people see: "Tubify 0.7.0" for stable builds, "Tubify Experimental 0.7.1b3" for experimental ones."""
    key = version_key(value)
    if not key:
        return 'Tubify'
    version = tag_version(value) or value
    return ('Tubify Experimental ' if key[3] == 0 else 'Tubify ') + version


class UnsignedUpdate(ValueError):
    """The release has no signature, or the download doesn't match it. Nothing gets installed."""


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
    return f'Tubify-{version}-linux-x86_64.pkg.tar.zst'


def select_asset(release, system=None):
    system = system or sys.platform
    tag = release.get('tag_name', '')
    version = tag_version(tag)
    if not version:
        raise ValueError('Invalid Tubify release')
    candidates = []
    for item in release.get('assets', []):
        if item.get('name', '') == asset_name(version, system):
            candidates.append({'tag': tag, **integrity(item, MAX_DOWNLOAD)})
    if len(candidates) != 1:
        raise ValueError('Release does not contain one matching installer')
    asset = candidates[0]
    # Sparkle checks macOS updates itself; everywhere else launch_installer checks this signature.
    if system != 'darwin':
        for suffix in SIGNATURE_SUFFIXES:
            signatures = [item for item in release.get('assets', []) if item.get('name') == asset['name'] + suffix]
            if len(signatures) == 1:
                asset['signature'] = integrity(signatures[0], MAX_SIGNATURE)
                return asset
        raise UnsignedUpdate('Release has no signature')
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
            return owner.returncode == 0 and owner.stdout.strip() == 'tubify'
        except (OSError, subprocess.TimeoutExpired):
            return False
    if not getattr(sys, 'frozen', False):
        return False
    return (sys.platform == 'win32' and machine in {'amd64', 'x86_64'}) or (sys.platform == 'darwin' and machine == 'arm64')


def download(tag, directory, progress=None, opener=urlopen):
    """Re-fetch release metadata so an offline cache can never authorize execution."""
    if not tag_version(tag):
        raise ValueError('Invalid Tubify release')
    request = Request('https://api.github.com/repos/Sayarinu/Tubify/releases/tags/' + tag,
                      headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'Tubify-updater'})
    with opener(request, timeout=15) as response:
        raw = response.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError('Release response too large')
    release = json.loads(raw)
    # Experimental tags must be published as prereleases and stable tags must not be.
    if release.get('draft') or bool(release.get('prerelease')) != is_experimental(tag) or release.get('tag_name') != tag:
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


def update_public_key():
    """The key this install trusts, placed by the package build."""
    if sys.platform == 'win32':
        from tubify.util import bundle_root

        return bundle_root() / 'update-public-key'
    return Path(LINUX_PUBLIC_KEY)


def check_signature(data, asset):
    from tubify.updates.package_signature import verify

    if not asset.get('signature_path'):
        raise UnsignedUpdate('Installer has no signature')
    if not verify(data, Path(asset['signature_path']).read_text(), update_public_key().read_text()):
        raise UnsignedUpdate('Installer signature check failed')


def launch_installer(asset, parent_pid):
    path = Path(asset['path']).resolve()
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != asset['sha256']:
        raise ValueError('Installer integrity check failed')
    if sys.platform not in {'win32', 'linux'}:
        raise ValueError('Use the macOS updater')
    check_signature(data, asset)
    if sys.platform == 'win32':
        subprocess.Popen([str(path), '/SILENT', '/SP-', '/NORESTART', '/NOCLOSEAPPLICATIONS',
                          '/TUBIFYUPDATE=1', f'/UPDATEPID={parent_pid}', f'/DIR={Path(sys.executable).parent}'])
    elif sys.platform == 'linux':
        # Copy before package replacement: the helper survives GUI/worker shutdown.
        helper = path.parent / 'install.py'
        shutil.copyfile(__file__, helper)
        signature = [asset['signature_path']] if asset.get('signature_path') else []
        downgrade = ['downgrade'] if signature and asset.get('downgrade') else []
        subprocess.Popen([sys.executable, '-I', str(helper), str(parent_pid), str(path), asset['sha256'], *signature, *downgrade],
                         start_new_session=True, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# Runs as root after the password prompt: copies the package somewhere only root can write,
# checks that copy against the expected digest, and installs that copy. Checking the file in
# the user-writable updates folder instead would let a local program swap it before pacman reads it.
ROOT_INSTALL = (
    'set -eu; umask 077; dir=$(mktemp -d); trap \'rm -rf "$dir"\' EXIT; '
    'copy="$dir/update.pkg.tar.zst"; cat -- "$1" > "$copy"; '
    'printf \'%s  %s\\n\' "$2" "$copy" | sha256sum --check --status; '
    '/usr/bin/pacman -U --noconfirm "$copy"'
)


def root_install_command(path, digest):
    return ['/usr/bin/pkexec', '--disable-internal-agent', '/bin/sh', '-c', ROOT_INSTALL, 'tubify-update', str(path), digest]


def install_linux(parent, package, digest, signature=None, downgrade=False):
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
        # Checked here too, so a changed file never asks for a password.
        with path.open('rb') as handle:
            if hashlib.file_digest(handle, 'sha256').hexdigest() != digest:
                raise ValueError('Installer changed')
        use_password = True
        if signature and Path(LINUX_HELPER).is_file():
            # The helper checks the release signature as root, so polkit allows it without a password.
            result = subprocess.run(['/usr/bin/pkexec', '--disable-internal-agent', LINUX_HELPER, str(path), str(signature)]).returncode
            # A switch back the helper won't allow can still go ahead with a password.
            use_password = downgrade and result == HELPER_REFUSED
        if use_password:
            result = subprocess.run(root_install_command(path, digest)).returncode
    except (OSError, ValueError):
        pass
    finally:
        (path.parent / 'result.json').write_text(json.dumps({'success': result == 0}))
        subprocess.Popen(['/usr/bin/tubify'], start_new_session=True)
    return result


if __name__ == '__main__':
    raise SystemExit(install_linux(int(sys.argv[1]), sys.argv[2], sys.argv[3], *sys.argv[4:5], downgrade=sys.argv[5:6] == ['downgrade']))
