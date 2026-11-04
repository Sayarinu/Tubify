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
    assert with_keys == ["name: Sign the macOS app and make its disk image", "name: Sign the Linux package"]


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
