from datetime import datetime, timedelta, timezone

from PySide6.QtCore import QByteArray, QCoreApplication, QDateTime, QEventLoop, QTimer, QUrl
from PySide6.QtNetwork import QNetworkCacheMetaData, QNetworkRequest

from youtube_music_native.artwork import ArtworkCache


def test_artwork_survives_restart_without_reaching_the_network(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    factory = ArtworkCache(tmp_path / "artwork")
    manager = factory.create(None)
    url = QUrl("https://fixture.invalid/artwork.png")
    metadata = QNetworkCacheMetaData()
    metadata.setUrl(url)
    metadata.setSaveToDisk(True)
    metadata.setExpirationDate(QDateTime.fromSecsSinceEpoch(int((datetime.now(timezone.utc) + timedelta(days=1)).timestamp())))
    metadata.setRawHeaders([(QByteArray(b"Content-Type"), QByteArray(b"image/png")), (QByteArray(b"Cache-Control"), QByteArray(b"max-age=86400"))])
    device = manager.cache().prepare(metadata)
    assert device is not None
    device.write(b"fixture artwork")
    manager.cache().insert(device)
    manager.deleteLater()
    app.processEvents()
    restarted = factory.create(None)
    loop = QEventLoop()
    reply = restarted.get(QNetworkRequest(url))
    reply.finished.connect(loop.quit)
    QTimer.singleShot(3000, loop.quit)
    loop.exec()
    assert reply.isFinished()
    assert reply.attribute(QNetworkRequest.Attribute.SourceIsFromCacheAttribute)
    assert bytes(reply.readAll()) == b"fixture artwork"
    assert restarted.cache().maximumCacheSize() == 128 * 1024 * 1024
    reply.deleteLater()
    restarted.deleteLater()
    app.processEvents()
