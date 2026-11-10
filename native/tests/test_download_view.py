from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer
import sys

from youtube_music_native.downloads.download_view import DownloadView
from youtube_music_native.downloads.downloads import DownloadStore

from test_downloads import IDS, body, write_wave


def test_download_control_and_progress_workers_finish_local_jobs_without_auth(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    store = DownloadStore(tmp_path)
    identifier = store.schedule(body("PLfixture", [IDS[0], IDS[0]]))
    folder = store.root / "audio"
    folder.mkdir()
    audio = folder / (IDS[0] + ".wav")
    write_wave(audio)
    store.media.publish(IDS[0], audio)
    store.close()
    view = DownloadView(tmp_path)
    loop = QEventLoop()
    progress = []
    view.transfer.progress.connect(lambda request, value: progress.append(value))

    def changed():
        # Its songs are already here, so it is complete before the transfer saves its cover.
        if view.collections and view.collections[0]["state"] == "complete" and progress and not view._active:
            loop.quit()

    view.changed.connect(changed)
    view.setAccountAvailable(True)
    QTimer.singleShot(15000, loop.quit)
    loop.exec()
    assert view.collections and view.collections[0]["state"] == "complete", view.message
    assert view.collections[0]["ready"] == 2 and progress
    assert audio.is_file()
    view.changed.disconnect(changed)
    view.changed.connect(lambda: loop.quit() if not view.collections else None)
    view.remove(identifier)
    QTimer.singleShot(10000, loop.quit)
    loop.exec()
    view.close()
    assert not view.collections and not audio.exists()


def test_local_collection_lookup_finishes_while_online_planning_is_blocked(tmp_path, monkeypatch):
    from youtube_music_native.downloads import download_view
    from youtube_music_native.jobs import Worker

    app = QCoreApplication.instance() or QCoreApplication([])
    store = DownloadStore(tmp_path)
    store.schedule(body("PLfixture", [IDS[0]]))
    store.close()
    marker = tmp_path / "planning-started"
    release = tmp_path / "release-planning"
    script = tmp_path / "provider.py"
    script.write_text('''import json,sys,time
from pathlib import Path
from youtube_music_native.account.auth import AuthService
from youtube_music_native.worker import handle
service=AuthService()
resources={}
for line in sys.stdin:
 request=json.loads(line)
 if request['operation']=='downloads_schedule':
  root=Path(request['payload']['data_dir']); (root/'planning-started').touch()
  while not (root/'release-planning').exists(): time.sleep(.01)
  result={}
 else: result=handle(service,request,resources)
 print(json.dumps({'id':request['id'],'ok':True,'result':result}),flush=True)
''')
    def worker_factory(*args, **kwargs):
        worker = Worker(*args, **kwargs)
        worker.process.setProgram(sys.executable)
        worker.process.setArguments([str(script)])
        return worker
    monkeypatch.setattr(download_view, "Worker", worker_factory)
    view = DownloadView(tmp_path)
    loop = QEventLoop()
    results = []
    view.collectionFound.connect(lambda request, result: (results.append(result), loop.quit()))
    requested = []
    def lookup():
        if marker.exists() and not requested:
            requested.append(view.lookup("playlist", "PLfixture"))
    poll = QTimer()
    poll.setInterval(10)
    poll.timeout.connect(lookup)
    poll.start()
    view.download({"kind": "playlist", "id": "PLslow"})
    QTimer.singleShot(5000, loop.quit)
    loop.exec()
    poll.stop()
    still_planning = bool(view._planning)
    release.touch()
    view.close()
    assert results and results[0]["items"] and still_planning


def test_refresh_if_stale_requests_status_only_when_stale(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    view = DownloadView(tmp_path, fixture=True)
    sent = []
    view._send = lambda operation, payload=None, authoritative=False: sent.append(operation)
    view.refreshIfStale()
    assert sent == ["status"]
    view._pending[7] = "status"
    view._result(7, {"collections": []})
    view.refreshIfStale()
    assert sent == ["status"]
    view.refresh()
    assert sent == ["status", "status"]
    view.setAccountAvailable(False)
    view.refreshIfStale()
    assert sent == ["status"] * 3
    view._pending[8] = "status"
    view._result(8, {"collections": []})
    view._pending[9] = "status"
    view._failed(9, {"message": "Failed"})
    view.refreshIfStale()
    assert sent == ["status"] * 4


def test_queued_collections_finish_in_one_transfer_process(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    store = DownloadStore(tmp_path)
    folder = store.root / "audio"
    folder.mkdir()
    for video_id in IDS[:2]:
        audio = folder / (video_id + ".wav")
        write_wave(audio)
        store.media.publish(video_id, audio)
    store.schedule(body("PLfirst", IDS[:1]))
    store.schedule(body("PLsecond", IDS[1:2]))
    store.close()
    view = DownloadView(tmp_path)
    loop = QEventLoop()
    processes, requests = set(), []
    view.transfer.process.started.connect(lambda: processes.add(view.transfer.process.processId()))
    original = view.transfer.request
    view.transfer.request = lambda operation, payload=None: (requests.append(operation), original(operation, payload))[1]

    def changed():
        if len(view.collections) == 2 and all(entry["state"] == "complete" for entry in view.collections) and not view._active:
            loop.quit()

    view.changed.connect(changed)
    view.setAccountAvailable(True)
    QTimer.singleShot(15000, loop.quit)
    loop.exec()
    view.close()
    assert [entry["state"] for entry in view.collections] == ["complete", "complete"], view.message
    assert requests == ["downloads_run"] and len(processes) == 1


def test_download_all_sends_every_playlist_in_one_planning_request(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    view = DownloadView(tmp_path)
    sent, refreshed = [], []
    view.planner.request = lambda operation, payload: sent.append((operation, payload)) or 41
    view.refresh = lambda: refreshed.append(True)
    view.downloadAll([{"id": "PLone", "title": "One", "owner": "Private"}, {"title": "No id"}, {"id": "PLtwo"}])
    assert [operation for operation, _ in sent] == ["downloads_schedule_all"]
    assert [media["id"] for media in sent[0][1]["playlists"]] == ["PLone", "PLtwo"] and "owner" not in sent[0][1]["playlists"][0]
    view._planned_one(41, {"scheduled": 1, "failed": 0})
    assert refreshed
    view._scheduled(41, {"scheduled": 1, "failed": 1})
    assert view._notice == "1 playlist could not be prepared. Download it from its menu to retry."
    view.close()


def test_song_progress_only_announces_progress_and_lookups_need_no_map_copies(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    view = DownloadView(tmp_path, fixture=True)
    emitted = []
    for name in ("changed", "statesChanged", "progressChanged", "artworkChanged", "storageChanged"):
        getattr(view, name).connect(lambda name=name: emitted.append(name))
    view._transfer_request = 5
    view._progress(5, {"videoId": IDS[0], "fraction": 0.25})
    view._progress(5, {"videoId": IDS[0], "fraction": 0.5})
    assert emitted == ["progressChanged", "statesChanged", "progressChanged"]
    assert view.songProgress(IDS[0]) == 0.5 and view.songState(IDS[0]) == "downloading"
    key = view.collections[0]["key"]
    assert view.collectionEntry(key)["state"] == "complete" and view.collectionEntry("playlist:missing") == {}
    assert view.known(*key.split(":", 1)) and not view.known("playlist", "missing")
    emitted.clear()
    status = {"collections": view.collections, "songs": [], "trackStates": view.trackStates, "trackProgress": view.trackProgress, "artwork": {}, "bytes": 1, "freeBytes": 2}
    view._pending[9] = "status"
    view._result(9, status)
    # Only storage moved, so lists, rows and covers are left alone.
    assert emitted == ["storageChanged"]
    view.close()
