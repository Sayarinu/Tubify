from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer

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
