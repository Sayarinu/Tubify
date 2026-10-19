"""Small asynchronous libmpv interface; no catalog code is imported here."""

import locale

from PySide6.QtCore import QObject, Signal


class Audio(QObject):
    updated = Signal(dict)
    ended = Signal(bool)

    def __init__(self, parent=None, output=None):
        super().__init__(parent)
        locale.setlocale(locale.LC_NUMERIC, "C")
        import mpv

        options = dict(vid="no", vo="null", ytdl=False, load_scripts=False, config=False, terminal=False, msg_level="all=no", idle=True)
        if output:
            options["ao"] = output
        self.player = mpv.MPV(**options)
        for name in ("time-pos", "duration", "pause", "volume", "paused-for-cache"):
            self.player.observe_property(name, lambda key, value: self.updated.emit({key: value}))

        @self.player.event_callback("end-file")
        def ended(event):
            reason = event.data.reason
            if reason == 0:
                self.ended.emit(False)
            elif reason == 4:
                self.ended.emit(True)

    def load(self, source, position=0, paused=False):
        self.player.http_header_fields = source.get("headers", [])
        self.player.pause = paused
        self.player.loadfile(source["source"], start=str(max(0, position)))

    def pause(self, value):
        self.player.pause = bool(value)

    def seek(self, position):
        self.player.seek(max(0, float(position)), reference="absolute", precision="exact")

    def volume(self, value):
        self.player.volume = max(0, min(100, float(value)))

    def stop(self):
        self.player.stop()

    def close(self):
        self.player.terminate()
