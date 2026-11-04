"""The root-owned Arch update helper that polkit allows without a password."""
import base64
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
import sys
from types import SimpleNamespace

from Cryptodome.PublicKey import ECC
import pytest

from youtube_music_native.updates import package_signature

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="The helper is only installed by the Arch package")

HELPER = Path(__file__).resolve().parents[2] / "packaging" / "arch-native" / "apply-update"


def load(tmp_path, monkeypatch, name="youtube-music-native", version="0.3.0-1", installed="0.2.0-1"):
    loader = SourceFileLoader("apply_update", str(HELPER))
    module = module_from_spec(spec_from_loader("apply_update", loader))
    loader.exec_module(module)
    key = ECC.generate(curve="ed25519")
    public = key.public_key().export_key(format="raw")
    pair = base64.b64encode(key.seed + public).decode()
    key_file = tmp_path / "update-public-key"
    key_file.write_text(base64.b64encode(public).decode())
    monkeypatch.setattr(module, "PUBLIC_KEY", key_file)
    calls = []

    def run(command, **kwargs):
        calls.append((command, Path(command[-1]).read_bytes() if command[:2] == ["/usr/bin/pacman", "-U"] else None))
        if command[:2] == ["/usr/bin/pacman", "-Qip"]:
            return SimpleNamespace(returncode=0, stdout=f"Name            : {name}\nVersion         : {version}\n")
        if command[:2] == ["/usr/bin/pacman", "-Q"]:
            return SimpleNamespace(returncode=0 if installed else 1, stdout=f"youtube-music-native {installed}\n")
        if command[0] == "/usr/bin/vercmp":
            order = (command[1] > command[2]) - (command[1] < command[2])
            return SimpleNamespace(returncode=0, stdout=f"{order}\n")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module.subprocess, "run", run)
    package = tmp_path / "Tubify-0.3.0-linux-x86_64.pkg.tar.zst"
    package.write_bytes(b"signed package")
    signature = tmp_path / (package.name + ".sig")
    signature.write_text(package_signature.sign(b"signed package", pair))
    return module, package, signature, calls


def test_signed_newer_package_installs_from_a_private_copy(tmp_path, monkeypatch):
    module, package, signature, calls = load(tmp_path, monkeypatch)
    assert module.main(["apply-update", str(package), str(signature)]) == 0
    install = calls[-1]
    assert install[0][:3] == ["/usr/bin/pacman", "-U", "--noconfirm"] and install[1] == b"signed package"
    assert Path(install[0][-1]).parent != package.parent


def test_unsigned_changed_foreign_or_older_packages_are_refused(tmp_path, monkeypatch):
    module, package, signature, calls = load(tmp_path, monkeypatch)
    package.write_bytes(b"changed package")
    assert module.main(["apply-update", str(package), str(signature)]) == 3
    assert not calls
    for options, code in (({"name": "other-package"}, 4), ({"version": "0.2.0-1", "installed": "0.3.0-1"}, 5), ({"version": "0.3.0-1", "installed": "0.3.0-1"}, 5)):
        folder = tmp_path / str(code) / options.get("name", options.get("version", ""))
        folder.mkdir(parents=True)
        module, package, signature, calls = load(folder, monkeypatch, **options)
        assert module.main(["apply-update", str(package), str(signature)]) == code
        assert not any(command[:2] == ["/usr/bin/pacman", "-U"] for command, _ in calls)


def test_links_and_wrong_arguments_are_refused(tmp_path, monkeypatch):
    module, package, signature, calls = load(tmp_path, monkeypatch)
    link = tmp_path / "link.pkg.tar.zst"
    link.symlink_to(package)
    assert module.main(["apply-update", str(link), str(signature)]) == 3
    assert module.main(["apply-update", str(signature), str(signature)]) == 2
    assert module.main(["apply-update", str(package)]) == 2
    assert not calls
