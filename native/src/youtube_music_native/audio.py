"""Small asynchronous libmpv interface; no catalog code is imported here."""

import locale

from PySide6.QtCore import QObject, Signal, Slot


from .speaker_fill import SpeakerFill


class Audio(QObject):
    updated = Signal(dict)
    ended = Signal(bool)
    deviceFailed = Signal()
    outputChanged = Signal()
    optionsChanged = Signal(dict)
    fileLoaded = Signal()
    fileEnded = Signal()

    def __init__(self, parent=None, output=None):
        super().__init__(parent)
        locale.setlocale(locale.LC_NUMERIC, "C")
        import mpv

        options = dict(vid="no", vo="null", ytdl=False, load_scripts=False, config=False, terminal=False, msg_level="all=no", idle=True, audio_client_name="Tubify")
        if output:
            options["ao"] = output
        self.player = mpv.MPV(**options)
        self._speaker_fill = SpeakerFill(self.player)
        self._fill_requested, self._ready = False, False
        self.outputChanged.connect(self._refresh_options)
        self.fileLoaded.connect(self._file_loaded)
        self.fileEnded.connect(self._reset_options)
        @self.player.event_callback("file-loaded")
        def loaded(event):
            self.fileLoaded.emit()
        @self.player.event_callback("audio-reconfig")
        def reconfigured(event):
            self.outputChanged.emit()
        for name in ("time-pos", "duration", "pause", "volume", "paused-for-cache"):
            self.player.observe_property(name, lambda key, value: self.updated.emit({key: value}))

        @self.player.event_callback("end-file")
        def ended(event):
            self.fileEnded.emit()
            reason = event.data.reason
            if reason == 0:
                self.ended.emit(False)
            elif reason == 4:
                if event.data.error == -14:  # MPV_ERROR_AO_INIT_FAILED is not a corrupt download.
                    self.deviceFailed.emit()
                else:
                    self.ended.emit(True)

    @Slot()
    def _file_loaded(self):
        self._ready = True
        self._refresh_options()

    @Slot()
    def _refresh_options(self):
        self.optionsChanged.emit(self._speaker_fill.refresh(self._fill_requested, self._ready))

    def setSpeakerFill(self, enabled):
        self._fill_requested = bool(enabled)
        self._speaker_fill.failed = False
        self._refresh_options()

    @Slot()
    def _reset_options(self):
        self._ready = False
        self._speaker_fill.failed = False
        self._refresh_options()

    def load(self, source, position=0, paused=False):
        self._reset_options()
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
        self._reset_options()
        self.player.stop()

    def close(self):
        self.player.terminate()
