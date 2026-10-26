from contextlib import nullcontext
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys

import pytest

from youtube_music_native import launcher
from youtube_music_native.startup import APP_ID, RUN_KEY, StartupError, StartupRegistration, desktop_exec


@pytest.mark.parametrize("platform", ["linux", "darwin"])
def test_file_registration_is_per_user_atomic_and_idempotent(tmp_path, platform):
    command = ["/Synthetic App/python", "/Synthetic App/launcher.py"]
    registration = StartupRegistration(command, platform, home=tmp_path, config=tmp_path / "config")
    assert registration.supported and not registration.is_enabled()
    registration.set_enabled(True)
    assert registration.is_enabled()
    content = registration.path.read_bytes()
    assert len(list(registration.path.parent.iterdir())) == 1
    if platform == "darwin":
        assert registration.path == tmp_path / "Library/LaunchAgents" / (APP_ID + ".plist")
        assert plistlib.loads(content) == {"Label": APP_ID, "ProgramArguments": command, "RunAtLoad": True}
    else:
        assert registration.path == tmp_path / "config/autostart/youtube-music-native.desktop"
        assert b'Exec="/Synthetic App/python" "/Synthetic App/launcher.py"' in content
    registration.set_enabled(True)
    assert registration.path.read_bytes() == content
    registration.command = ["/new app"]
    assert not registration.is_enabled()
    registration.set_enabled(True)
    assert registration.is_enabled()
    registration.set_enabled(False)
    registration.set_enabled(False)
    assert not registration.path.exists()


@pytest.mark.parametrize("platform", ["linux", "darwin"])
def test_file_registration_preserves_foreign_items_and_failed_replacements(tmp_path, platform, monkeypatch):
    registration = StartupRegistration(["/synthetic"], platform, home=tmp_path, config=tmp_path)
    registration.path.parent.mkdir(parents=True)
    registration.path.write_text("foreign item")
    for enabled in (True, False):
        with pytest.raises(StartupError, match="different login item"):
            registration.set_enabled(enabled)
        assert registration.path.read_text() == "foreign item"
    registration.path.unlink()
    registration.set_enabled(True)
    saved = registration.path.read_bytes()
    registration.command = ["/new"]
    def fail_replace(*args):
        raise OSError("synthetic disk error")
    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError):
        registration.set_enabled(True)
    assert registration.path.read_bytes() == saved
    assert len(list(registration.path.parent.iterdir())) == 1


def test_linux_exec_quoting_preserves_arguments_without_a_shell():
    arguments = ["/path with spaces/player", "back\\slash", 'say"hello', "a$b`c", "100%", "'quoted'"]
    line = desktop_exec(arguments)
    # The Desktop Entry general string unescape precedes Exec token unquoting.
    import shlex
    unescaped = line.replace("\\\\", "\\")
    assert shlex.split(unescaped.replace("\\$", "$" ).replace("\\`", "`")) == [arg.replace("%", "%%") for arg in arguments]
    with pytest.raises(StartupError):
        desktop_exec(["/bad\npath"])
    with pytest.raises(StartupError):
        desktop_exec(["/unsupported=executable"])
    fallback = StartupRegistration(["/synthetic"], "linux", home=Path("/home/synthetic"), config="relative")
    assert fallback.path == Path("/home/synthetic/.config/autostart/youtube-music-native.desktop")


class Registry:
    HKEY_CURRENT_USER, REG_SZ = 1, 2

    def __init__(self):
        self.values = {}
        self.calls = []

    def OpenKey(self, root, path):
        self.calls.append((root, path))
        return nullcontext(self)

    CreateKey = OpenKey

    def QueryValueEx(self, key, name):
        if name not in self.values:
            raise FileNotFoundError
        return self.values[name]

    def SetValueEx(self, key, name, reserved, kind, value):
        self.values[name] = (value, kind)

    def DeleteValue(self, key, name):
        if name not in self.values:
            raise FileNotFoundError
        del self.values[name]


def test_windows_registration_uses_current_user_and_windows_argv_quoting(tmp_path):
    registry = Registry()
    command = [r"C:\Synthetic App\player.exe", "quote\"inside", "trailing\\"]
    registration = StartupRegistration(command, "win32", registry=registry)
    assert not registration.is_enabled()
    registration.set_enabled(True)
    assert registration.is_enabled()
    assert registry.values[APP_ID] == (subprocess.list2cmdline(command), registry.REG_SZ)
    assert all(call == (registry.HKEY_CURRENT_USER, RUN_KEY) for call in registry.calls)
    registry.values["unrelated"] = ("other", registry.REG_SZ)
    registration.set_enabled(False)
    registration.set_enabled(False)
    assert not registration.is_enabled() and "unrelated" in registry.values
    registration.command = ["x" * 261]
    with pytest.raises(StartupError, match="too long"):
        registration.set_enabled(True)
    assert APP_ID not in registry.values


def test_unsupported_or_fixture_registration_never_writes(tmp_path):
    for registration in (StartupRegistration(["/test"], "unsupported", home=tmp_path), StartupRegistration(["/test"], "linux", home=tmp_path, disabled_reason="Fixture registration is disabled")):
        assert not registration.supported
        with pytest.raises(StartupError):
            registration.set_enabled(True)
    assert not list(tmp_path.iterdir())


def test_application_command_is_absolute_and_runs_outside_source_cwd(tmp_path, monkeypatch):
    command = launcher.application_command()
    assert command[0] == sys.executable and Path(command[1]).is_absolute()
    assert launcher.process_command("provider") == [*command, "--provider-worker"]
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    result = subprocess.run([*command, "--help"], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0 and "native Qt client" in result.stdout, result.stderr
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert launcher.application_command() == [sys.executable]
    assert launcher.process_command("player") == [sys.executable, "--player-worker"]


def test_provider_command_keeps_standard_library_imports_from_foreign_cwd(tmp_path):
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    # Missing data_dir enters safe_error, which imports requests/urllib3/stdlib queue.
    # AuthService creates no credential backend until an account operation needs it.
    requests = [{"id": identifier, "operation": "lyrics", "payload": {}} for identifier in (1, 2)]
    result = subprocess.run(launcher.process_command("provider"),
        input="".join(json.dumps(request) + "\n" for request in requests),
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    responses = [json.loads(line) for line in result.stdout.splitlines()]
    assert [response["id"] for response in responses] == [1, 2]
    assert all(not response["ok"] and response["error"]["code"] == "provider_error" for response in responses)
    assert not result.stderr


def test_legacy_linux_display_name_keeps_login_state_without_rewriting(tmp_path):
    registration = StartupRegistration(["/synthetic/player"], "linux", config=tmp_path)
    registration.path.parent.mkdir(parents=True)
    previous = registration._content().replace(b"\nName=Tubify\n", b"\nName=YouTube Music\n")
    registration.path.write_bytes(previous)
    assert registration.is_enabled()
    assert registration.path.read_bytes() == previous
    registration.command = ["/different/player"]
    assert not registration.is_enabled()
    assert registration.path.read_bytes() == previous
