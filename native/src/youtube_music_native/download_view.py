"""Local download controls stay independent of online planning and transfers."""

from pathlib import Path
import json

from PySide6.QtCore import QObject, Property, QProcess, QTimer, Signal, Slot

from .jobs import Worker


class DownloadView(QObject):
    changed = Signal()
    collectionReady = Signal(dict)
    collectionFound = Signal(int, dict)
    playRequested = Signal(dict, bool)

    def __init__(self, data_dir, fixture=False, parent=None):
        super().__init__(parent)
        self.data_dir, self.fixture = str(Path(data_dir)), fixture
        self.control = None if fixture else Worker(self, idle_ms=30000)
        self.planner = None if fixture else Worker(self, idle_ms=1000)
        self.transfer = None if fixture else Worker(self, idle_ms=1000)
        self._planning = set()
        self._collections, self._pending, self._stopped = [], {}, []
        self._track_states, self._open_request = {}, None
        self._artwork, self._initialized = {}, fixture
        self._fixture_bodies = {}
        self._active, self._transfer_request, self._next = None, None, None
        self._bytes, self._free, self._message = 0, 0, ""
        self._minimum_request, self._status_pending = 0, False
        self._allow_network, self._resetting, self._closed = False, False, False
        if fixture:
            tracks = json.loads((Path(__file__).parent / "assets" / "visual-fixture.json").read_text())["shelves"][0]["items"]
            for index, (kind, title, state) in enumerate((("playlist", "Evening focus", "complete"), ("album", "Somewhere quiet", "downloading"), ("playlist", "Long way home", "damaged"), ("song", "A familiar tune", "cancelled"))):
                key = kind + ":fixture-" + str(index)
                values = [{**track, "kind": "song", "duration": 180, "downloadState": "ready" if state == "complete" else "missing"} for track in tracks[:1 if kind == "song" else 6]]
                self._fixture_bodies[key] = {"kind": kind, "id": key.split(":", 1)[1], "title": title, "items": values, "downloadKey": key, "cursor": None, "trackCount": len(values), "duration": sum(track["duration"] for track in values)}
                self._collections.append({"key": key, "id": key.split(":", 1)[1], "kind": kind, "title": title, "state": state, "ready": len(values) if state == "complete" else 1, "total": len(values), "progress": 0.42 if state == "downloading" else 1., "error": ""})
            self._bytes, self._free = 127000000, 32000000000
        self.poll = QTimer(self)
        self.poll.setInterval(2000)
        self.poll.timeout.connect(self.refresh)
        if self.control:
            self.control.succeeded.connect(self._result)
            self.control.failed.connect(self._failed)
            self.planner.succeeded.connect(self._scheduled)
            self.planner.failed.connect(self._schedule_failed)
            self.transfer.succeeded.connect(self._transferred)
            self.transfer.failed.connect(self._transfer_failed)
            self.transfer.progress.connect(self._progress)
            self.transfer.process.finished.connect(self._flush_stopped)
            QTimer.singleShot(0, lambda: self._send("initialize"))

    @Property("QVariantList", notify=changed)
    def collections(self):
        return self._collections

    @Property("QVariantMap", notify=changed)
    def trackStates(self):
        return self._track_states

    @Property("QVariantMap", notify=changed)
    def artwork(self):
        return self._artwork

    @Property(bool, notify=changed)
    def initialized(self):
        return self._initialized

    @Property(str, notify=changed)
    def message(self):
        return self._message

    @Property(str, notify=changed)
    def activeCollection(self):
        return self._active or ""

    @Property(float, notify=changed)
    def usedBytes(self):
        return float(self._bytes)

    @Property(float, notify=changed)
    def freeBytes(self):
        return float(self._free)

    @Slot(bool)
    def setAccountAvailable(self, available):
        self._allow_network = available
        self._pump()

    def _send(self, operation, payload=None, authoritative=False):
        if not self.control or self._closed:
            return None
        request = self.control.request("downloads_" + operation, {"data_dir": self.data_dir, **(payload or {})})
        self._pending[request] = operation
        if operation == "status":
            self._status_pending = True
        if authoritative:
            self._minimum_request = request
        return request

    @Slot("QVariantMap")
    def download(self, media):
        if self.fixture:
            self._message = "Download preview"
            self.changed.emit()
            return
        self._message = "Preparing download…"
        self._planning.add(self.planner.request("downloads_schedule", {"data_dir": self.data_dir, "media": dict(media)}))
        self.changed.emit()

    def _scheduled(self, identifier, result):
        if identifier not in self._planning:
            return
        self._planning.remove(identifier)
        self._send("status", authoritative=True)

    def _schedule_failed(self, identifier, error):
        if identifier not in self._planning:
            return
        self._planning.remove(identifier)
        if not self._resetting:
            self._message = error.get("message", "This download could not be prepared. Retry.")
            self.changed.emit()

    @Slot()
    def refresh(self):
        if not self._status_pending:
            self._send("status")

    @Slot(str)
    def open(self, identifier):
        if self.fixture:
            if identifier in self._fixture_bodies:
                self.collectionReady.emit(self._fixture_bodies[identifier])
            return
        if self._open_request is not None:
            self.control.cancelQueued(self._open_request)
        self._open_request = self._send("collection", {"id": identifier})

    @Slot(str, bool)
    def play(self, identifier, shuffle):
        kind, _, media_id = identifier.partition(":")
        self.playRequested.emit({"kind": kind, "id": media_id}, shuffle)

    def lookup(self, kind, identifier):
        return self._send("lookup", {"kind": kind, "id": identifier})

    def cancelLookup(self, request):
        if self.control and request is not None:
            self.control.cancelQueued(request)

    def cancelOpen(self):
        self.cancelLookup(self._open_request)
        self._open_request = None

    @Slot(str)
    def retry(self, identifier):
        if self.fixture:
            self._fixture_update(identifier, "complete")
            return
        self._send("retry", {"id": identifier}, authoritative=True)

    @Slot(str)
    def cancel(self, identifier):
        if self.fixture:
            self._fixture_update(identifier, "cancelled")
            return
        self._stop_and_send("cancel", identifier)

    @Slot(str)
    def remove(self, identifier):
        if self.fixture:
            self._collections = [entry for entry in self._collections if entry["key"] != identifier]
            self._fixture_bodies.pop(identifier, None)
            self.changed.emit()
            return
        self._stop_and_send("remove", identifier)

    def _fixture_update(self, identifier, state):
        for entry in self._collections:
            if entry["key"] == identifier:
                entry.update(state=state, ready=entry["total"] if state == "complete" else entry["ready"])
        self.changed.emit()

    def _stop_and_send(self, operation, identifier):
        if self._active == identifier:
            self._active, self._transfer_request = None, None
            self._stopped.append((operation, {"id": identifier}))
            self.transfer.reset()
            self._flush_stopped()
        else:
            self._send(operation, {"id": identifier}, authoritative=True)

    def _flush_stopped(self, *args):
        if self.transfer.process.state() == QProcess.ProcessState.NotRunning:
            pending, self._stopped = self._stopped, []
            for operation, payload in pending:
                self._send(operation, payload, authoritative=True)

    @Slot(int, dict)
    def _result(self, identifier, result):
        operation = self._pending.pop(identifier, None)
        if operation == "status":
            self._status_pending = False
        if operation == "collection":
            if identifier == self._open_request:
                self._open_request = None
                self.collectionReady.emit(result)
            return
        if operation == "lookup":
            self.collectionFound.emit(identifier, result)
            return
        if identifier < self._minimum_request or operation is None:
            return
        self._message = "Preparing download…" if self._planning else ""
        self._collections = result.get("collections", [])
        self._track_states = result.get("trackStates", {})
        self._artwork, self._initialized = result.get("artwork", {}), True
        self._bytes, self._free, self._next = result.get("bytes", 0), result.get("freeBytes", 0), result.get("next")
        self.changed.emit()
        self._pump()

    def _pump(self):
        mutations = {"remove", "cancel", "retry", "initialize", "fail"}
        if self._closed or self._resetting or self._stopped or not self._allow_network or self._active or not self._next or any(op in mutations for op in self._pending.values()):
            return
        self._active, self._next = self._next, None
        self._transfer_request = self.transfer.request("downloads_run", {"data_dir": self.data_dir, "id": self._active})
        self.poll.start()
        self.changed.emit()

    @Slot(int, dict)
    def _progress(self, identifier, progress):
        if identifier != self._transfer_request:
            return
        for collection in self._collections:
            if collection["key"] == self._active:
                collection["state"] = "downloading"
                collection["progress"] = (progress.get("completed", 0) + progress.get("fraction", 0)) / max(1, progress.get("total", 1))
        self.changed.emit()

    @Slot(int, dict)
    def _transferred(self, identifier, result):
        if identifier != self._transfer_request:
            return
        self._active, self._transfer_request = None, None
        self.poll.stop()
        self._send("status", authoritative=True)

    @Slot(int, dict)
    def _transfer_failed(self, identifier, error):
        if identifier != self._transfer_request:
            return
        active = self._active
        self._active, self._transfer_request = None, None
        self.poll.stop()
        self._message = error.get("message", "Download stopped. Retry to continue.")
        self._send("fail", {"id": active}, authoritative=True)
        self.changed.emit()

    @Slot(int, dict)
    def _failed(self, identifier, error):
        operation = self._pending.pop(identifier, None)
        if operation == "initialize":
            self._initialized = True
        if operation == "lookup":
            self.collectionFound.emit(identifier, {})
        if operation == "status":
            self._status_pending = False
        if not self._resetting:
            self._message = error.get("message", "This download operation failed. Retry.")
            self.changed.emit()

    def resetSession(self):
        if not self.control:
            return
        self._resetting = True
        self._planning.clear()
        self.planner.reset()
        self._active, self._transfer_request, self._next = None, None, None
        self.poll.stop()
        self.control.reset()
        self._stopped.append(("initialize", {}))
        self.transfer.reset()
        self._resetting = False
        self._flush_stopped()

    def close(self):
        self._closed = True
        self.poll.stop()
        if self.control:
            self.control.close()
            self.planner.close()
            self.transfer.close()
