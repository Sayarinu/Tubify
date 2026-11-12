"""The root-owned Linux update helper that polkit allows without a password."""
import base64
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
import sys
from types import SimpleNamespace

from Cryptodome.PublicKey import ECC
import pytest

from tubify.updates import package_signature

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="The helper is only installed by the Linux package")

HELPER = Path(__file__).resolve().parents[2] / "packaging" / "linux" / "apply-update"


def load(tmp_path, monkeypatch, name="tubify", version="0.3.0-1", installed="0.2.0-1"):
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
            return SimpleNamespace(returncode=0 if installed else 1, stdout=f"tubify {installed}\n")
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


@pytest.mark.parametrize("version,installed,oldest,code", [
    # An experimental build switches back as far as the stable release recorded when it was built.
    ("0.8.2-1", "0.8.3b4-1", "0.8.2", 0),
    ("0.8.3-1", "0.8.4b1-1", "0.8.2", 0),
    # Nothing older than that, and nothing at all without a valid record.
    ("0.8.1-1", "0.8.3b4-1", "0.8.2", 5),
    ("0.8.2-1", "0.8.3b4-1", "", 5),
    ("0.8.2-1", "0.8.3b4-1", "not-a-version", 5),
    ("0.8.2-1", "0.8.3b4-1", None, 5),
    # A stable install never goes back, and neither do experimental builds.
    ("0.8.1-1", "0.8.2-1", "0.8.0", 5),
    ("0.8.3b1-1", "0.8.3b4-1", "0.8.0", 5),
    ("0.8.3b1-1", "0.8.4-1", "0.8.0", 5),
])
def test_only_a_recent_stable_release_can_replace_an_experimental_build(tmp_path, monkeypatch, version, installed, oldest, code):
    module, package, signature, calls = load(tmp_path, monkeypatch, version=version, installed=installed)
    record = tmp_path / "oldest-switch-version"
    if oldest is not None:
        record.write_text(oldest + "\n")
    monkeypatch.setattr(module, "OLDEST_SWITCH", record)
    assert module.main(["apply-update", str(package), str(signature)]) == code
    assert any(command[:2] == ["/usr/bin/pacman", "-U"] for command, _ in calls) == (code == 0)


def test_unsigned_older_stable_release_is_still_refused(tmp_path, monkeypatch):
    module, package, signature, calls = load(tmp_path, monkeypatch, version="0.8.2-1", installed="0.8.3b4-1")
    record = tmp_path / "oldest-switch-version"
    record.write_text("0.8.2\n")
    monkeypatch.setattr(module, "OLDEST_SWITCH", record)
    package.write_bytes(b"changed package")
    assert module.main(["apply-update", str(package), str(signature)]) == 3
    assert not calls


def test_links_and_wrong_arguments_are_refused(tmp_path, monkeypatch):
    module, package, signature, calls = load(tmp_path, monkeypatch)
    link = tmp_path / "link.pkg.tar.zst"
    link.symlink_to(package)
    assert module.main(["apply-update", str(link), str(signature)]) == 3
    assert module.main(["apply-update", str(signature), str(signature)]) == 2
    assert module.main(["apply-update", str(package)]) == 2
    assert not calls
