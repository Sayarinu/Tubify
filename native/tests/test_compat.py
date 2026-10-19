import json
from types import SimpleNamespace

import pytest

from youtube_music_native import compat
from youtube_music_native.session import from_headers


def test_signed_sources_are_sent_through_stdin_and_child_output_is_not_forwarded(monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout="", stderr="private provider output")

    monkeypatch.setattr(compat.subprocess, "run", run)
    source = "https://media.example/audio?signature=private"
    compat.play_source(source, ["Authorization: private"])
    command, options = calls[0]
    assert all("private" not in part for part in command)
    assert json.loads(options["input"]) == {"source": source, "headers": ["Authorization: private"]}


def test_offline_replay_uses_a_new_network_namespace(monkeypatch, tmp_path):
    monkeypatch.setattr(compat.sys, "platform", "linux")
    monkeypatch.setattr(compat.shutil, "which", lambda name: "/usr/bin/" + name)
    commands = []
    monkeypatch.setattr(compat.subprocess, "run", lambda command, **kwargs: commands.append(command) or SimpleNamespace(returncode=0))
    media = tmp_path / "audio.webm"
    media.write_bytes(b"completed fixture")
    compat.play_source(media, offline=True)
    assert commands[0][:5] == ["unshare", "--user", "--map-root-user", "--net", compat.sys.executable]


def test_missing_local_download_never_starts_a_player(monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        pytest.fail("Missing local files must not fall back to remote playback in the offline proof")

    monkeypatch.setattr(compat.subprocess, "run", forbidden)
    with pytest.raises(compat.ProbeError):
        compat.play_source(tmp_path / "missing.webm", offline=True)


def test_provider_failure_report_does_not_serialize_secrets(monkeypatch, tmp_path):
    import ytmusicapi

    def broken(*args, **kwargs):
        raise RuntimeError("private-cookie and https://media.example/?signature=private")

    monkeypatch.setattr(ytmusicapi, "YTMusic", broken)
    monkeypatch.setattr(compat, "player_command", lambda offline=False: ["fixture"])
    monkeypatch.setattr(compat.shutil, "which", lambda name: name)
    report = compat.run_probe(from_headers({"cookie": "__Secure-3PAPISID=private"}), tmp_path)
    assert report["status"] == "failed"
    assert report["failed_stage"] == "account"
    assert "private" not in json.dumps(report)


def test_failed_player_cannot_pass_the_gate(monkeypatch):
    monkeypatch.setattr(compat.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=1))
    with pytest.raises(compat.ProbeError):
        compat.play_source("https://media.example/audio")
