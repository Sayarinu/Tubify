"""Per-user login registration; no launch, shell, or administrator privileges."""

import os
from pathlib import Path
import plistlib
import subprocess
import sys

from ..launcher import application_command
from ..util import atomic_write


APP_ID = "studio.nouvellelune.tubify"
# Login items from earlier builds. move_old_item replaces one so the person's choice carries over.
OLD_APP_ID = "com.carter.youtube-music-native"
# Before 1.0 the Linux autostart entry had the old package name and marked itself with this key.
OLD_DESKTOP_FILE = "youtube-music-native.desktop"
OLD_DESKTOP_KEY = "X-YouTube-Music-Native"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


class StartupError(Exception):
    """An actionable message suitable for the settings UI."""


def desktop_exec(command):
    """Quote argv for Desktop Entry Exec, including its preceding string unescape."""
    if not command or "=" in command[0]:
        raise StartupError("The executable path cannot be registered with this desktop.")
    quoted = []
    for argument in command:
        if any(ord(char) < 32 for char in argument):
            raise StartupError("The application path contains an unsupported character.")
        argument = argument.replace("%", "%%")
        argument = "".join("\\" + char if char in '\\"`$' else char for char in argument)
        quoted.append('"' + argument.replace("\\", "\\\\") + '"')
    return " ".join(quoted)


class StartupRegistration:
    def __init__(self, command=None, platform=None, home=None, config=None, registry=None, disabled_reason=""):
        self.command = list(command or application_command())
        self.platform = platform or sys.platform
        self.home = Path(home) if home is not None else Path.home()
        configured = config if config is not None else os.environ.get("XDG_CONFIG_HOME", "")
        self.config = Path(configured) if configured and Path(configured).is_absolute() else self.home / ".config"
        self.registry = registry
        self.disabled_reason = disabled_reason

    @property
    def supported(self):
        return not self.disabled_reason and self.platform in {"linux", "darwin", "win32"}

    @property
    def path(self):
        if self.platform == "linux":
            return self.config / "autostart" / "tubify.desktop"
        return self.home / "Library" / "LaunchAgents" / (APP_ID + ".plist")

    def _registry(self):
        if self.registry is None:
            import winreg
            self.registry = winreg
        return self.registry

    def _check(self):
        if not self.supported:
            raise StartupError(self.disabled_reason or "Login startup is not supported on this platform.")

    def _content(self):
        if self.platform == "darwin":
            return plistlib.dumps({"Label": APP_ID, "ProgramArguments": self.command, "RunAtLoad": True})
        return ("[Desktop Entry]\nType=Application\nName=Tubify\n"
                f"X-Tubify={APP_ID}\nExec={desktop_exec(self.command)}\nTerminal=false\n").encode()

    def _owned(self, content):
        if self.platform == "darwin":
            try:
                value = plistlib.loads(content)
                return isinstance(value, dict) and value.get("Label") == APP_ID
            except (ValueError, plistlib.InvalidFileException):
                return False
        return f"X-Tubify={APP_ID}\n".encode() in content

    def move_old_item(self):
        """Re-register a login item an earlier build made under the old identifier; True if one was moved."""
        if not self.supported:
            return False
        if self.platform == "win32":
            return self._move_old_registry_value()
        if self.platform == "linux":
            old = self.path.with_name(OLD_DESKTOP_FILE)
            if not old.is_file():
                return False
            content = old.read_bytes()
            if not any(f"{OLD_DESKTOP_KEY}={value}\n".encode() in content for value in (APP_ID, OLD_APP_ID)):
                return False
            self.set_enabled(True)
            old.unlink()
            return True
        old = self.path.with_name(OLD_APP_ID + ".plist")
        try:
            if plistlib.loads(old.read_bytes()).get("Label") != OLD_APP_ID:
                return False
        except (OSError, ValueError, AttributeError, plistlib.InvalidFileException):
            return False
        self.set_enabled(True)
        old.unlink()
        return True

    def _move_old_registry_value(self):
        registry = self._registry()
        with registry.CreateKey(registry.HKEY_CURRENT_USER, RUN_KEY) as key:
            try:
                registry.QueryValueEx(key, OLD_APP_ID)
            except FileNotFoundError:
                return False
            registry.DeleteValue(key, OLD_APP_ID)
        self.set_enabled(True)
        return True

    def is_enabled(self):
        self._check()
        if self.platform == "win32":
            registry = self._registry()
            try:
                with registry.OpenKey(registry.HKEY_CURRENT_USER, RUN_KEY) as key:
                    value, kind = registry.QueryValueEx(key, APP_ID)
                return kind == registry.REG_SZ and value == subprocess.list2cmdline(self.command)
            except FileNotFoundError:
                return False
        try:
            content = self.path.read_bytes()
            if self.platform == "linux":
                content = content.replace(b"\nName=YouTube Music\n", b"\nName=Tubify\n")
            return content == self._content()
        except FileNotFoundError:
            return False

    def set_enabled(self, enabled):
        self._check()
        if self.platform == "win32":
            registry = self._registry()
            command = subprocess.list2cmdline(self.command)
            if enabled and len(command) > 260:
                raise StartupError("The login command is too long for Windows. Install the app in a shorter path and retry.")
            with registry.CreateKey(registry.HKEY_CURRENT_USER, RUN_KEY) as key:
                if enabled:
                    registry.SetValueEx(key, APP_ID, 0, registry.REG_SZ, command)
                else:
                    try:
                        registry.DeleteValue(key, APP_ID)
                    except FileNotFoundError:
                        pass
            return
        path = self.path
        if path.exists() and not self._owned(path.read_bytes()):
            raise StartupError("A different login item uses this name. Remove or rename it in your system startup settings and retry.")
        if not enabled:
            path.unlink(missing_ok=True)
            return
        content = self._content()
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(path, content)
