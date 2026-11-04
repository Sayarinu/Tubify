import base64

from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QImage

from youtube_music_native.integrations.deep_links import parse_link, share_url
from youtube_music_native.integrations.handoff import Handoff, handoff_url, qr_data_url
from youtube_music_native.integrations.qrcodegen import QrCode


def test_share_url_builds_song_list_and_position_links():
    assert share_url("abcdefghijk") == "https://music.youtube.com/watch?v=abcdefghijk"
    assert share_url("abcdefghijk", "PLfixture123", 95.8) == "https://music.youtube.com/watch?v=abcdefghijk&list=PLfixture123&t=95"
    assert share_url("abcdefghijk", "", 0.6) == "https://music.youtube.com/watch?v=abcdefghijk"
    assert parse_link(share_url("abcdefghijk", "PLfixture123", 30))["id"] == "abcdefghijk"


def test_share_url_rejects_invalid_ids_and_positions():
    for video in ("", "short", "abcdefghijk&x=1", None, 12345678901):
        assert share_url(video) == ""
    assert share_url("abcdefghijk", "bad list!") == "https://music.youtube.com/watch?v=abcdefghijk"
    assert share_url("abcdefghijk", "", float("nan")) == "https://music.youtube.com/watch?v=abcdefghijk"
    assert share_url("abcdefghijk", "", -5) == "https://music.youtube.com/watch?v=abcdefghijk"
    assert share_url("abcdefghijk", "", 10 ** 6) == "https://music.youtube.com/watch?v=abcdefghijk"


def test_handoff_url_keeps_lists_only_for_playlists_and_albums():
    track = {"videoId": "abcdefghijk"}
    assert handoff_url(track, {"kind": "playlist", "playlistId": "PLfixture123"}, 12) == "https://music.youtube.com/watch?v=abcdefghijk&list=PLfixture123&t=12"
    assert handoff_url(track, {"kind": "album", "playlistId": "OLAK5uy_fixture"}, 0) == "https://music.youtube.com/watch?v=abcdefghijk&list=OLAK5uy_fixture"
    for context in ({"kind": "radio"}, {"kind": "artist", "playlistId": "RDfixture"}, {}, None):
        assert handoff_url(track, context, 0) == "https://music.youtube.com/watch?v=abcdefghijk"
    assert handoff_url({}, {"kind": "playlist", "playlistId": "PLfixture123"}, 12) == ""


def test_qr_image_matches_the_encoded_symbol():
    url = "https://music.youtube.com/watch?v=abcdefghijk&list=PLfixture123&t=95"
    data = qr_data_url(url)
    assert data.startswith("data:image/png;base64,")
    image = QImage.fromData(base64.b64decode(data.split(",", 1)[1]), "PNG")
    code = QrCode.encode_text(url, QrCode.Ecc.MEDIUM)
    assert image.width() == image.height() == code.get_size() + 8
    for x, y in ((0, 0), (code.get_size() // 2, code.get_size() // 2), (code.get_size() - 1, 0)):
        assert (image.pixelColor(x + 4, y + 4).value() < 128) == code.get_module(x, y)
    assert image.pixelColor(0, 0).value() == 255


class Player:
    def __init__(self, track, context=None, position=0.0):
        self.currentTrack, self._context, self.position, self.paused = track, context or {}, position, 0

    def current_context(self):
        return dict(self._context)

    def pause(self):
        self.paused += 1


def test_handoff_opens_only_with_a_valid_song_and_pauses_on_request():
    app = QCoreApplication.instance() or QCoreApplication([])
    player = Player({"videoId": "abcdefghijk"}, {"kind": "playlist", "playlistId": "PLfixture123"}, 42.4)
    handoff, opened = Handoff(player), []
    handoff.requested.connect(lambda: opened.append(True))
    handoff.open()
    assert opened == [True]
    assert handoff.url == "https://music.youtube.com/watch?v=abcdefghijk&list=PLfixture123&t=42"
    assert handoff.qrImage.startswith("data:image/png;base64,")
    handoff.finish(False)
    assert player.paused == 0
    handoff.finish(True)
    assert player.paused == 1

    player.currentTrack = {"title": "No video id"}
    handoff.open()
    assert opened == [True] and handoff.url == "" and handoff.qrImage == ""
    handoff.finish(True)
    assert player.paused == 1
    assert app
