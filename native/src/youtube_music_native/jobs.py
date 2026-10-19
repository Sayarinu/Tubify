"""Asynchronous provider-process transport shared by account and catalog jobs."""

from collections import deque
import json
import os
import signal

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from .launcher import process_command


class Worker(QObject):
    succeeded = Signal(int, dict)
    failed = Signal(int, dict)
    progress = Signal(int, dict)

    def __init__(self, parent=None, idle_ms=0):
        super().__init__(parent)
        self.process = QProcess(self)
        if os.name == "posix":
            self.process.setUnixProcessParameters(QProcess.UnixProcessFlag.CreateNewSession)
        command = process_command("provider")
        self.process.setProgram(command[0])
        self.process.setArguments(command[1:])
        self.process.started.connect(self._pump)
        self.process.readyReadStandardOutput.connect(self._read)
        self.process.readyReadStandardError.connect(lambda: self.process.readAllStandardError())
        self.process.errorOccurred.connect(self._error)
        self.process.finished.connect(self._finished)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._timeout)
        self.idle_timer = QTimer(self)
        self.idle_timer.setSingleShot(True)
        self.idle_timer.setInterval(idle_ms)
        self.idle_timer.timeout.connect(self._hibernate)
        self._idle_ms, self._hibernating = idle_ms, False
        self._queue = deque()
        self._active = None
        self._buffer = b""
        self._counter = 0
        self._closed = False

    def request(self, operation, payload=None):
        if self._closed:
            raise RuntimeError("The provider worker is closed")
        self._counter += 1
        self._queue.append({"id": self._counter, "operation": operation, "payload": payload or {}})
        self._pump()
        return self._counter

    def cancelQueued(self, identifier):
        self._queue = deque(request for request in self._queue if request["id"] != identifier)

    def _pump(self):
        if self._closed or self._hibernating or self._active or not self._queue:
            return
        self.idle_timer.stop()
        if self.process.state() == QProcess.ProcessState.NotRunning:
            self._buffer = b""
            self.process.start()
        elif self.process.state() == QProcess.ProcessState.Running:
            self._active = self._queue.popleft()
            self.process.write((json.dumps(self._active) + "\n").encode("utf-8"))
            self.timer.start(60000)

    def _read(self):
        incoming = bytes(self.process.readAllStandardOutput())
        if self._closed or self._hibernating:
            return
        self._buffer += incoming
        if len(self._buffer) > 32 * 1024 * 1024:
            self._protocol_error()
            return
        while b"\n" in self._buffer:
            line, self._buffer = self._buffer.split(b"\n", 1)
            try:
                response = json.loads(line)
                if not self._active or response.get("id") != self._active["id"]:
                    raise ValueError()
                if isinstance(response.get("progress"), dict):
                    self.timer.start(60000)
                    self.progress.emit(self._active["id"], response["progress"])
                    continue
                success = response.get("ok") and isinstance(response.get("result"), dict)
                failure = not response.get("ok") and isinstance(response.get("error"), dict)
                if not success and not failure:
                    raise ValueError()
                identifier = self._active["id"]
                self._active = None
                self.timer.stop()
                if success:
                    self.succeeded.emit(identifier, response["result"])
                else:
                    self.failed.emit(identifier, response["error"])
                QTimer.singleShot(0, self._pump)
                if self._idle_ms:
                    self.idle_timer.start()
            except (ValueError, TypeError, AttributeError):
                self._protocol_error()
                return

    def _fail_all(self, code, message):
        self.timer.stop()
        pending = ([self._active] if self._active else []) + list(self._queue)
        self._active = None
        self._queue.clear()
        for request in pending:
            self.failed.emit(request["id"], {"code": code, "message": message})

    def _protocol_error(self):
        self._abort("provider_error", "This request could not be completed. Retry the operation.")

    def _timeout(self):
        self._abort("timeout", "The request timed out. Check your connection or unlock your system keyring.")

    def _error(self, error):
        if not self._closed and not self._hibernating:
            self._abort("provider_error", "This request stopped. Retry the operation.")

    def _finished(self, exit_code, exit_status):
        self.timer.stop()
        if self._hibernating:
            self._hibernating = False
            QTimer.singleShot(0, self._pump)
            return
        if not self._closed:
            self._abort("provider_error", "This request stopped. Retry the operation.")

    def _signal_process(self, force=False):
        pid = self.process.processId()
        if os.name == "posix" and pid:
            try:
                os.killpg(pid, signal.SIGKILL if force else signal.SIGTERM)
                return
            except ProcessLookupError:
                return
        self.process.kill() if force else self.process.terminate()

    def _abort(self, code, message):
        self._hibernating = True
        running = self.process.state() != QProcess.ProcessState.NotRunning
        self._fail_all(code, message)
        if running:
            self._signal_process(force=True)
        else:
            QTimer.singleShot(0, self._restart_if_stopped)

    def _restart_if_stopped(self):
        if self.process.state() == QProcess.ProcessState.NotRunning:
            self._hibernating = False
            self._pump()

    def _hibernate(self):
        if not self._active and not self._queue and self.process.state() == QProcess.ProcessState.Running:
            self._hibernating = True
            self._signal_process()
            QTimer.singleShot(1000, self._kill_idle)

    def _kill_idle(self):
        if self._hibernating and self.process.state() != QProcess.ProcessState.NotRunning:
            self._signal_process(force=True)

    def reset(self):
        self._abort("cancelled", "The account connection changed. Retry this request.")

    def close(self):
        self._closed = True
        self.timer.stop()
        self.idle_timer.stop()
        self._queue.clear()
        self._active = None
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self._signal_process()
            if not self.process.waitForFinished(500):
                self._signal_process(force=True)
                self.process.waitForFinished(500)
