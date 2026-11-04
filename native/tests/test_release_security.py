"""The release workflow's isolation of the signing keys must not quietly regress."""
from pathlib import Path
import re

import pytest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github/workflows"
if not WORKFLOWS.exists():
    # The Linux source package runs these tests without the repository's workflows.
    pytest.skip("workflows are not part of this source tree", allow_module_level=True)


def jobs():
    """Each job's text in native.yml, by job id."""
    text = (WORKFLOWS / "native.yml").read_text()
    body = text[text.index("\njobs:\n"):]
    parts = re.split(r"(?m)^  ([a-z][a-z-]*):\n", body)
    return dict(zip(parts[1::2], parts[2::2]))


def test_only_the_sign_job_can_reach_secrets():
    assert [name for name, body in jobs().items() if "secrets." in body] == ["sign"]
    others = [path for path in WORKFLOWS.glob("*.yml") if path.name != "native.yml"]
    assert not [path.name for path in others if "secrets." in path.read_text()]


def test_signing_job_uses_the_protected_environment_and_runs_no_build_tools():
    sign = jobs()["sign"]
    assert "environment: ${{ needs.version.outputs.publish == 'true' && 'release' || '' }}" in sign
    assert "persist-credentials: false" in sign
    assert "--require-hashes" in sign
    for tool in ("setup-uv", "uv pip", "brew install", "--smoke-test", "--player-worker", "build-native"):
        assert tool not in sign, tool
    script = (ROOT / "scripts/sign-native-macos.sh").read_text()
    for tool in (r"\buv\b", r"\bpip\b", "brew install", "PyInstaller", "--smoke-test"):
        assert not re.search(tool, script), tool


def test_keys_are_only_handed_to_steps_that_need_them():
    sign = jobs()["sign"]
    steps = re.split(r"(?m)^      - ", sign)
    with_keys = [step.splitlines()[0] for step in steps if "secrets." in step]
    assert with_keys == ["name: Sign the macOS app and make its disk image", "name: Sign the Linux package and Windows installer"]


def test_every_third_party_action_is_pinned_to_a_commit():
    for path in WORKFLOWS.glob("*.yml"):
        for used in re.findall(r"uses:\s*(\S+)", path.read_text()):
            assert used.startswith("./") or re.fullmatch(r"[\w./-]+@[0-9a-f]{40}", used), (path.name, used)


def test_tags_cannot_trigger_a_signed_release():
    on = (WORKFLOWS / "native.yml").read_text().split("\npermissions:", 1)[0]
    assert "tags:" not in on


def test_signing_material_is_ignored():
    ignored = (ROOT / ".gitignore").read_text().split()
    for pattern in ("*.p12", "*.pem", "*.key", "tubify-signing.*", ".env"):
        assert pattern in ignored


def test_public_signing_values_come_from_variables():
    assert not (ROOT / "packaging/macos/sparkle-public-key.txt").exists()
    text = (WORKFLOWS / "native.yml").read_text()
    assert "vars.TUBIFY_UPDATE_PUBLIC_KEY" in jobs()["sign"]
    assert "vars.TUBIFY_MACOS_SIGNING_CERT" in jobs()["macos-verify"]
    # The placeholder is only for builds that won't be published.
    assert "vars.TUBIFY_UPDATE_PUBLIC_KEY ||" in text and "'AAAA" not in jobs()["sign"]
    assert "publish != 'true' && 'AAAA" in text


def test_every_windows_and_linux_download_is_signed_and_published_with_its_signature():
    sign = jobs()["sign"]
    assert "windows-app" in sign.split("runs-on", 1)[0] and "tubify-windows-x64-installer" in sign
    assert 'for file in "$package" "$installer"' in sign and "dist/native/*.exe.sig" in sign
    assert 'test -s "$installer.sig"' in jobs()["release-assets"]
    assert "*.exe.sig" in jobs()["release"]
    assert 'cp "$package.sig" "$package.ed25519"' in sign and "dist/native/*.pkg.tar.zst.ed25519" in sign
    assert 'test -s "$package.ed25519"' in jobs()["release-assets"]
    # 0.8.1 installs only look for .sig, so it stays published for now.
    assert "*.pkg.tar.zst.sig" in jobs()["release"] and "*.pkg.tar.zst.ed25519" in jobs()["release"]
    assert "TUBIFY_UPDATE_PUBLIC_KEY" in jobs()["windows-app"]
    assert "update-public-key" in (ROOT / "packaging/windows/Tubify.spec").read_text()


def test_release_builds_use_pinned_inputs():
    # A release is signed and shipped automatically, so nothing it installs may float.
    for script in ("build-native-macos.sh", "build-native-windows.ps1"):
        text = (ROOT / "scripts" / script).read_text()
        assert "--frozen" in text and "--require-hashes" in text and "--build-constraints" in text
        assert not re.search(r"\./native\[", text), script
    assert (ROOT / "native/uv.lock").exists()
    assert re.fullmatch(r"setuptools==\d[\d.]*", (ROOT / "packaging/build-constraints.txt").read_text().splitlines()[-1])
    linux = (WORKFLOWS / "native-linux-build.yml").read_text()
    assert "archlinux:latest" not in linux and re.search(r"archlinux@sha256:[0-9a-f]{64}", linux)
    assert re.search(r"archive\.archlinux\.org/repos/\d{4}/\d{2}/\d{2}/", linux)
    assert re.search(r"deno-version: v\d+\.\d+\.\d+", (WORKFLOWS / "native.yml").read_text())


def test_a_failing_check_blocks_merging_and_skipped_jobs_do_not():
    gate = jobs()["checks-passed"]
    assert "if: always()" in gate and "needs.*.result, 'failure'" in gate and "needs.*.result, 'cancelled'" in gate
    needed = re.search(r"needs: \[(.*?)\]", gate).group(1).split(", ")
    # Every job that tests or builds something counts, and only publishing is left out.
    assert set(needed) == set(jobs()) - {"checks-passed", "release"}
    setup = (ROOT / "scripts/setup-release-protection.sh").read_text()
    assert '{"context": "Tubify checks passed"}' in setup and '{"context": "Branch, title and base"}' in setup


def test_release_inputs_cannot_skip_the_checks():
    pattern = re.search(r"BUILD_INPUTS: '(.*)'", jobs()["changes"]).group(1)
    for path in ("native/uv.lock", "native/src/youtube_music_native/app.py", "packaging/windows/Tubify.spec", "packaging/build-constraints.txt",
                 "packaging/signing-requirements.txt", ".github/workflows/native.yml", ".github/workflows/native-linux-build.yml",
                 "scripts/sign-native-macos.sh", "scripts/open-prs.py", "scripts/setup-release-protection.sh"):
        assert re.search(pattern, path), path
    for path in ("docs/releases.md", "README.md", "AGENTS.md"):
        assert not re.search(pattern, path), path
