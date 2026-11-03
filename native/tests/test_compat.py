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


def test_node_solves_challenges_ahead_of_deno_when_both_are_installed(monkeypatch, tmp_path):
    pytest.importorskip("yt_dlp")
    from yt_dlp.extractor.youtube.jsc._builtin.deno import DenoJCP
    from yt_dlp.extractor.youtube.jsc._builtin.node import NodeJCP
    from yt_dlp.extractor.youtube.jsc._registry import _jsc_preferences

    monkeypatch.setattr(compat.shutil, "which", lambda name: "/opt/runtimes/" + name)
    options = compat.extractor_options(tmp_path)
    assert list(options["js_runtimes"]) == ["node", "deno"]
    registered = len(_jsc_preferences.value)
    compat.extractor_options(tmp_path)
    assert len(_jsc_preferences.value) == registered  # Registered once per process.

    def rank(provider_class):
        # yt-dlp ignores the option order and sorts solvers by their summed preferences.
        provider = object.__new__(provider_class)
        return sum(preference(provider, []) for preference in _jsc_preferences.value)

    assert rank(NodeJCP) > rank(DenoJCP) > 0


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


def test_video_only_media_cannot_be_published_as_downloaded_audio(monkeypatch, tmp_path):
    result = {"format": {"duration": "5.0"}, "streams": [{"codec_type": "video"}]}
    monkeypatch.setattr(compat.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout=json.dumps(result)))
    with pytest.raises(compat.ProbeError):
        compat.validate_media(tmp_path / "video.mp4")


def test_media_validation_never_opens_a_console_window_on_windows(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(compat.os, "name", "nt")
    monkeypatch.setattr(compat.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    monkeypatch.setattr(compat.subprocess, "run", lambda command, **kwargs: calls.append(kwargs) or SimpleNamespace(
        stdout='{"format": {"duration": "1"}, "streams": [{"codec_type": "audio"}]}'))
    compat.validate_media(tmp_path / "audio.opus")
    assert calls[0]["creationflags"] == 0x08000000
    monkeypatch.setattr(compat.os, "name", "posix")
    assert compat.hidden_window() == {}
