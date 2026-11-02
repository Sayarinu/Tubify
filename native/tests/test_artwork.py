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


def test_google_artwork_is_resized_without_lookups():
    from youtube_music_native.artwork_sources import choose, with_resized

    values = [{"url": "https://lh3.googleusercontent.com/abc123=w544-h544-l90-rj", "width": 544, "height": 544}]
    chosen = choose(with_resized(values, 1200), 1200)
    assert chosen == {"url": "https://lh3.googleusercontent.com/abc123=w1440-h1440-l90-rj", "width": 1440, "height": 1440}
    assert with_resized(values, 300) == values
    video = [{"url": "https://i.ytimg.com/vi/abcdefghijk/hqdefault.jpg", "width": 480, "height": 360}]
    assert with_resized(video, 1200) == video


def test_artwork_sizes_snap_to_shared_buckets():
    from youtube_music_native.artwork_sources import bucket, resized

    assert [bucket(value) for value in (1, 256, 257, 544, 545, 900, 1081, 1500, 4096)] == [256, 256, 544, 544, 1080, 1080, 1440, 2048, 2048]
    values = [{"url": "https://lh3.googleusercontent.com/abc123=w120-h120"}]
    # Different windows and scales request the same URL, so the disk cache answers.
    assert resized(values, 601) == resized(values, 1000) == [{"url": "https://lh3.googleusercontent.com/abc123=w1080-h1080-l90-rj", "width": 1080, "height": 1080}]
