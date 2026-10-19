"""Asynchronous provider-process transport shared by account and catalog jobs."""

from collections import deque
import json

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from .launcher import process_command


class Worker(QObject):
    succeeded = Signal(int, dict)
    failed = Signal(int, dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = QProcess(self)
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
        if self._closed or self._active or not self._queue:
            return
        if self.process.state() == QProcess.ProcessState.NotRunning:
            self._buffer = b""
            self.process.start()
        elif self.process.state() == QProcess.ProcessState.Running:
            self._active = self._queue.popleft()
            self.process.write((json.dumps(self._active) + "\n").encode("utf-8"))
            self.timer.start(60000)

    def _read(self):
        incoming = bytes(self.process.readAllStandardOutput())
        if self._closed:
            return
        self._buffer += incoming
        if len(self._buffer) > 1024 * 1024:
            self._protocol_error()
            return
        while b"\n" in self._buffer:
            line, self._buffer = self._buffer.split(b"\n", 1)
            try:
                response = json.loads(line)
                if not self._active or response.get("id") != self._active["id"]:
                    raise ValueError()
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
        self._fail_all("provider_error", "The account helper could not complete this request. Retry the operation.")
        self.process.kill()

    def _timeout(self):
        self._fail_all("timeout", "The request timed out. Check your connection or unlock your system keyring.")
        self.process.kill()

    def _error(self, error):
        if not self._closed:
            self._fail_all("provider_error", "The account helper stopped. Retry the operation.")

    def _finished(self, exit_code, exit_status):
        self.timer.stop()
        if not self._closed:
            self._fail_all("provider_error", "The account helper stopped. Retry the operation.")

    def close(self):
        self._closed = True
        self.timer.stop()
        self._queue.clear()
        self._active = None
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.terminate()
            if not self.process.waitForFinished(500):
                self.process.kill()
                self.process.waitForFinished(500)
