from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer
import sys

from youtube_music_native.download_view import DownloadView
from youtube_music_native.downloads import DownloadStore

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
        if view.collections and view.collections[0]["state"] == "complete":
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
    from youtube_music_native import download_view
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
from youtube_music_native.auth import AuthService
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
