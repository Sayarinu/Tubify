import json
from pathlib import Path
import subprocess
import shutil
import sys
import time
from types import SimpleNamespace
from urllib.parse import quote

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QObject, QUrl, Signal
from PySide6.QtNetwork import QLocalSocket
from PySide6.QtTest import QTest

from youtube_music_native.deep_links import DeepLinks, LinkError, parse_link
from youtube_music_native.link_instance import LinkInstance, MAX_MESSAGE

SONG = "https://music.youtube.com/watch?v=abcdefghijk"
ARTIST = "https://music.youtube.com/channel/UC" + "a" * 22
PLAYLIST = "https://music.youtube.com/playlist?list=PLfixture123"


def link(action, url=SONG):
    return "ytmusic-native://" + action + "?url=" + quote(url, safe="")


@pytest.mark.parametrize("url,kind,identifier", [(SONG + "&si=tracking", "song", "abcdefghijk"), ("https://youtu.be/abcdefghijk?si=tracking", "song", "abcdefghijk"), (SONG + "&list=PLfixture123", "song", "abcdefghijk"), (PLAYLIST, "playlist", "PLfixture123"), (ARTIST, "artist", "UC" + "a" * 22), ("https://music.youtube.com/browse/MPREfixture", "album", "MPREfixture")])
def test_supported_urls_default_to_safe_preview(url, kind, identifier):
    result = parse_link(url)
    assert result["action"] == "open" and result["kind"] == kind and result["id"] == identifier
    assert "tracking" not in result["url"] and "si=" not in result["url"]


@pytest.mark.parametrize("url", ["file:///tmp/music", "https://music.youtube.com.evil.invalid/watch?v=abcdefghijk", "https://music.youtube.com@evil.invalid/watch?v=abcdefghijk", "https://user@music.youtube.com/watch?v=abcdefghijk", "http://music.youtube.com/watch?v=abcdefghijk", SONG + "&v=another0001", SONG + "#fragment", "https://music.youtube.com:8443/watch?v=abcdefghijk", "https://music.youtube.com/channel/nested/UC" + "a" * 22, "ytmusic-native://shell?url=" + quote(SONG), link("open", "file:///tmp/private"), link("play") + "&command=run", "--provider-worker", "x" * 4097, "https://music.youtube.com/playlist?list=PLbad%0Avalue"])
def test_malformed_or_unsupported_urls_are_rejected(url):
    with pytest.raises(LinkError):
        parse_link(url)


@pytest.mark.parametrize("action", ["open", "play", "queue"])
def test_only_explicit_native_actions_change_link_action(action):
    assert parse_link(link(action))["action"] == action


class Worker(QObject):
    succeeded = Signal(int, dict)
    failed = Signal(int, dict)
    def __init__(self):
        super().__init__()
        self.requests, self.cancelled = [], []
    def request(self, operation, payload):
        self.requests.append((operation, payload))
        return len(self.requests)
    def cancelQueued(self, identifier):
        self.cancelled.append(identifier)


class Downloads(QObject):
    collectionFound = Signal(int, dict)
    def __init__(self):
        super().__init__()
        self.requests, self.cancelled = [], []
    def lookup(self, kind, identifier):
        self.requests.append((kind, identifier))
        return len(self.requests)
    def cancelLookup(self, identifier):
        self.cancelled.append(identifier)


class Browse:
    queueBusy = False
    def __init__(self):
        self.calls = []
    def open(self, media):
        self.calls.append(("open", media))
    def play(self, media):
        self.calls.append(("play", media))
    def enqueue(self, media):
        self.calls.append(("queue", media))


def controller(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    browse, worker, downloads, clock = Browse(), Worker(), Downloads(), [100.]
    service = DeepLinks(browse, SimpleNamespace(worker=worker), downloads, tmp_path / "cache.sqlite3", clock=lambda: clock[0])
    service._app = app
    return service, browse, worker, downloads, clock


TRACK = {"kind": "song", "videoId": "abcdefghijk", "title": "Synthetic track", "artist": "Fixture artist"}


def test_open_is_preview_and_offline_download_uses_no_catalog(tmp_path):
    service, browse, worker, downloads, clock = controller(tmp_path)
    service.receive(SONG)
    assert service.busy and not service.canPlay and not browse.calls
    downloads.collectionFound.emit(1, {"kind": "song", "items": [TRACK]})
    assert service.media == TRACK and not service.busy and service.canPlay
    assert not worker.requests and not browse.calls
    service.perform("queue")
    assert browse.calls == [("queue", TRACK)]


def test_explicit_actions_wait_for_valid_details_and_duplicate_launch_is_suppressed(tmp_path):
    service, browse, worker, downloads, clock = controller(tmp_path)
    service.receive(link("play"))
    service.receive(link("play"))
    assert len(downloads.requests) == 1
    downloads.collectionFound.emit(1, {})
    assert worker.requests[0][1]["route"] == "radio" and worker.requests[0][1]["params"]["radio"] is False
    worker.succeeded.emit(1, {"items": [TRACK]})
    assert browse.calls == [("play", TRACK)]
    clock[0] += 3
    service.receive(link("play"))
    assert len(downloads.requests) == 2


def test_stale_lookup_and_catalog_responses_cannot_play_wrong_link(tmp_path):
    service, browse, worker, downloads, clock = controller(tmp_path)
    service.receive(link("play"))
    downloads.collectionFound.emit(1, {})
    service.receive(PLAYLIST)
    worker.succeeded.emit(1, {"items": [TRACK]})
    downloads.collectionFound.emit(1, {"items": [TRACK]})
    assert not browse.calls and service.media["kind"] == "playlist"
    downloads.collectionFound.emit(2, {"title": "Offline playlist", "items": [TRACK]})
    assert not browse.calls and service.media["kind"] == "playlist"
    service.perform("open")
    assert browse.calls[-1][0] == "open"


def test_failed_details_remain_preview_and_artist_actions_are_explicit(tmp_path):
    service, browse, worker, downloads, clock = controller(tmp_path)
    service.receive(link("queue"))
    downloads.collectionFound.emit(1, {})
    worker.failed.emit(1, {"message": "private provider failure"})
    assert not browse.calls and not service.canPlay and "private" not in service.message
    service.perform("play")
    assert not browse.calls
    service.retry()
    worker.succeeded.emit(2, {"items": [TRACK]})
    assert not browse.calls, "Retrying a failed link must not auto-play"
    service.receive(link("play", ARTIST))
    worker.succeeded.emit(3, {"title": "Synthetic artist"})
    assert not browse.calls and "Open this artist" in service.message
    service.perform("open")
    assert browse.calls[-1][0] == "open"


def test_malformed_link_cancels_previous_pending_action(tmp_path):
    service, browse, worker, downloads, clock = controller(tmp_path)
    service.receive(link("play"))
    service.receive("file:///private")
    downloads.collectionFound.emit(1, {"items": [TRACK]})
    assert not browse.calls and not service.media and not service.canPlay


def wait_for(predicate, seconds=4):
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        QTest.qWait(5)
    assert predicate()


def test_second_process_forwards_to_one_instance_and_stale_lock_recovers(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    primary = LinkInstance(tmp_path)
    assert primary.claim_or_forward([SONG])
    received = []
    primary.linksReceived.connect(received.append)
    primary.ready()
    assert received == [[SONG]]
    code = "from pathlib import Path; from PySide6.QtCore import QCoreApplication; from youtube_music_native.link_instance import LinkInstance; import sys; app=QCoreApplication([]); item=LinkInstance(Path(sys.argv[1])); assert not item.claim_or_forward([sys.argv[2]]); item.close()"
    process = subprocess.Popen([sys.executable, "-c", code, str(tmp_path), link("queue")], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    wait_for(lambda: process.poll() is not None)
    stdout, stderr = process.communicate()
    assert process.returncode == 0, stderr.decode()
    assert received[-1] == [link("queue")]
    assert primary.lock.isLocked() and primary.server.isListening()
    primary.close()
    recovered = LinkInstance(tmp_path)
    assert recovered.claim_or_forward([])
    recovered.close()


def test_local_handoff_rejects_bad_tokens_oversize_and_unsupported_links(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    primary = LinkInstance(tmp_path)
    primary.claim_or_forward([])
    received = []
    primary.linksReceived.connect(received.append)
    primary.ready()
    for data in (json.dumps({"token": "incorrect", "links": [SONG]}).encode() + b"\n", b"x" * (MAX_MESSAGE + 1), json.dumps({"token": primary._token, "links": ["file:///private"]}).encode() + b"\n"):
        peer = QLocalSocket()
        peer.connectToServer(primary.name)
        wait_for(lambda: peer.state() == QLocalSocket.LocalSocketState.ConnectedState)
        peer.write(data)
        peer.flush()
        wait_for(lambda: peer.state() == QLocalSocket.LocalSocketState.UnconnectedState)
    assert not received
    primary.close()


def test_file_open_and_cold_start_are_deferred_until_ready(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    instance = LinkInstance(tmp_path)
    assert instance.claim_or_forward([])
    received = []
    instance.linksReceived.connect(received.append)
    event = SimpleNamespace(type=lambda: QEvent.Type.FileOpen, url=lambda: QUrl(SONG))
    assert instance.eventFilter(None, event)
    assert not received
    instance.ready()
    assert received == [[SONG]]
    instance.close()


def test_package_and_userscript_register_only_native_handler():
    root = Path(__file__).resolve().parents[2]
    desktop = (root / "packaging/arch-native/youtube-music-native.desktop").read_text()
    assert "Exec=youtube-music-native -- %u" in desktop and "MimeType=x-scheme-handler/ytmusic-native;" in desktop
    userscript = (root / "native/integrations/browser-handoff.user.js").read_text()
    assert "GM_getValue(preference, false)" in userscript and "GM_setValue(preference, enabled)" in userscript
    assert "location.replace" not in userscript and "fetch(" not in userscript


@pytest.mark.skipif(shutil.which("node") is None, reason="Optional userscript behavior check needs Node.js")
def test_userscript_requires_per_host_enable_and_only_creates_explicit_links():
    script = Path(__file__).resolve().parents[1] / "integrations/browser-handoff.user.js"
    code = r"""
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const source = fs.readFileSync(process.argv[1], 'utf8');
function setup(address) {
  let toggle; const saved = {}, events = {}, children = [];
  const document = {
    documentElement: {append(node) { children.push(node); }},
    addEventListener(name, fn) { events[name] = fn; },
    createElement(tag) { return {tag, style: {}, children: [], setAttribute() {}, addEventListener() {}, append(node) {this.children.push(node)}, remove() {const i=children.indexOf(this); if(i>=0)children.splice(i,1)}} }
  };
  const context = {URL, location: new URL(address), document, window: {addEventListener() {}}, GM_getValue(key, fallback) {return saved[key] ?? fallback}, GM_setValue(key, value) {saved[key]=value}, GM_registerMenuCommand(label, fn) {toggle=fn}};
  vm.runInNewContext(source, context);
  assert.equal(children.length, 0);
  toggle();
  assert.equal(saved['enabled:' + context.location.hostname], true);
  const links = children[0].children.filter(node => node.tag === 'a');
  assert(links.every(node => node.href.startsWith('ytmusic-native://')));
  assert.equal(new URL(links[0].href).searchParams.get('url'), address);
  toggle(); assert.equal(children.length, 0);
  return links.length;
}
assert.equal(setup('https://music.youtube.com/watch?v=abcdefghijk'),3);
assert.equal(setup('https://www.youtube.com/channel/UCaaaaaaaaaaaaaaaaaaaaaa'),1);
"""
    subprocess.run([shutil.which("node"), "-e", code, str(script)], check=True, capture_output=True, text=True)
