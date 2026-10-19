from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookiejar import CookieJar
import threading
from types import SimpleNamespace

import pytest
from yt_dlp import YoutubeDL

from youtube_music_native import downloads
from youtube_music_native.compat import QuietLogger
from youtube_music_native.downloads import DownloadCancelled, Downloads

from test_downloads import IDS, body, write_wave


def test_real_http_downloader_cancels_and_resumes_partial_audio_then_publishes(tmp_path, monkeypatch):
    original = tmp_path / "original.wav"
    write_wave(original, seconds=8)
    content = original.read_bytes()
    ranges = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            start = int(self.headers.get("Range", "bytes=0-").split("=", 1)[1].split("-", 1)[0])
            ranges.append(start)
            self.send_response(206 if start else 200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(content) - start))
            if start:
                self.send_header("Content-Range", f"bytes {start}-{len(content) - 1}/{len(content)}")
            self.end_headers()
            try:
                self.wfile.write(content[start:])
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/fixture.wav"

    class LocalExtractor(YoutubeDL):
        def extract_info(self, request_url, download):
            return self.process_ie_result({"id": IDS[0], "title": "Fixture", "url": url, "ext": "wav", "vcodec": "none", "acodec": "pcm_s16le", "extractor": "fixture", "extractor_key": "Fixture"}, download=download)

    monkeypatch.setattr(downloads, "extractor_options", lambda directory: {"quiet": True, "noprogress": True, "logger": QuietLogger(), "format": "bestaudio", "proxy": ""})
    auth = SimpleNamespace(session=SimpleNamespace(cookie_jar=CookieJar))
    service = Downloads(auth, tmp_path, extractor_factory=LocalExtractor, artwork_fetch=lambda url, folder: "")
    try:
        identifier = service.store.schedule(body("PLresume", IDS[:1]))
        staging = service.store.root / "staging"
        staging.mkdir()
        partial = staging / (IDS[0] + ".wav.part")
        partial.write_bytes(content[:4096])
        cancelled = [False]

        def cancel_after_first_progress(value):
            if value.get("bytes", 0) and not cancelled[0]:
                cancelled[0] = True
                service.store.cancel(identifier)

        service.notify = cancel_after_first_progress
        with pytest.raises(DownloadCancelled):
            service.run(identifier)
        assert partial.is_file() and not service.store.media.ready(IDS[0])
        service.notify = lambda value: None
        service.store.retry(identifier)
        service.run(identifier)
        complete = service.store.media.ready(IDS[0])
        assert len(ranges) == 2 and ranges[0] == 4096 and ranges[1] > 4096
        assert complete is not None and complete.read_bytes() == content
        assert not partial.exists()
    finally:
        service.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
