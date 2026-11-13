"""Show a file in the system file manager, selected where the platform allows."""

import os
import subprocess
import sys

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices


def _show_items_over_dbus(path):
    """Ask the freedesktop file manager to select the file. Most Linux file managers implement this."""
    from jeepney import DBusAddress, new_method_call
    from jeepney.io.blocking import open_dbus_connection
    from jeepney.wrappers import unwrap_msg

    address = DBusAddress("/org/freedesktop/FileManager1", bus_name="org.freedesktop.FileManager1", interface="org.freedesktop.FileManager1")
    with open_dbus_connection("SESSION") as connection:
        unwrap_msg(connection.send_and_get_reply(new_method_call(address, "ShowItems", "ass", ([QUrl.fromLocalFile(path).toString()], "")), timeout=3))


def _open_folder(folder):
    return QDesktopServices.openUrl(QUrl.fromLocalFile(folder))


def reveal(path, platform=None, launch=subprocess.Popen, show_items=_show_items_over_dbus, open_folder=_open_folder):
    """Select the file in the file manager, or open its folder when the file is gone or selecting fails."""
    if not isinstance(path, str) or not os.path.isabs(path):
        return False
    folder = os.path.dirname(path)
    platform = platform or sys.platform
    if os.path.isfile(path):
        try:
            if platform == "win32":
                launch(["explorer", "/select,", os.path.normpath(path)])
                return True
            if platform == "darwin":
                launch(["open", "-R", path])
                return True
            if platform.startswith("linux"):
                show_items(path)
                return True
        except Exception:
            pass
    return bool(os.path.isdir(folder) and open_folder(folder))
