from urllib.parse import parse_qs

import pytest
from PySide6.QtCore import QCoreApplication, QSettings

from tubify.integrations.lounge import FrameParser, Lounge, LoungeSession, encode_messages


def frame(payload):
    return f"{len(payload)}\n{payload}"


def test_frames_split_across_reads_and_keep_partial_data():
    parser = FrameParser()
    stream = frame('[[0,["c","SID-SECRET","",8]],[1,["S","GS-SECRET"]]]') + frame('[[2,["setPlaylist",{"videoId":"abcdefghijk"}]],[3,["noop"]]]')
    cut = len(stream) - 9
    first = parser.feed(stream[:cut])
    second = parser.feed(stream[cut:])
    assert first == [(0, "c", ["SID-SECRET", "", 8]), (1, "S", "GS-SECRET")]
    assert second == [(2, "setPlaylist", {"videoId": "abcdefghijk"}), (3, "noop", None)]
    assert parser.buffer == ""


def test_frames_ignore_malformed_entries_and_reject_runaway_buffers():
    parser = FrameParser()
    assert parser.feed(frame('[[0,["play"]],["bad"],[1,[]],[2,[7]],{"x":1}]')) == [(0, "play", None)]
    assert parser.feed("not a frame") == []
    with pytest.raises(ValueError):
        FrameParser().feed("5\n[" + "x" * (1 << 20))


def test_messages_encode_in_one_batch_with_offsets():
    form = encode_messages(7, [("nowPlaying", {"videoId": "abcdefghijk", "state": "1"}), ("onVolumeChanged", {"volume": "40"})])
    assert form == {"count": 2, "ofs": 7, "req0__sc": "nowPlaying", "req0_videoId": "abcdefghijk", "req0_state": "1", "req1__sc": "onVolumeChanged", "req1_volume": "40"}


def test_session_tracks_bind_values_and_returns_only_commands():
    session = LoungeSession("00000000-0000-4000-8000-000000000000", "Tubify")
    session.token = "TOKEN"
    commands = session.absorb([(0, "c", ["SID", "", 8]), (1, "S", "GS"), (4, "noop", None), (5, "pause", None), (3, "seekTo", {"newTime": "9"})])
    assert session.bound and session.sid == "SID" and session.gsessionid == "GS" and session.aid == 5
    assert commands == [("pause", {}), ("seekTo", {"newTime": "9"})]

    init = parse_qs(session.query("init"))
    assert init["device"] == ["LOUNGE_SCREEN"] and init["theme"] == ["m"] and "deviceInfo" in init and "SID" not in init
    rid = int(init["RID"][0])
    send = parse_qs(session.query("send"))
    assert send["SID"] == ["SID"] and send["gsessionid"] == ["GS"] and send["AID"] == ["5"] and int(send["RID"][0]) == rid + 1
    poll = parse_qs(session.query("poll"))
    assert poll["RID"] == ["rpc"] and poll["TYPE"] == ["xmlhttp"] and poll["CI"] == ["0"]

    session.reset()
    assert not session.bound and session.token == "TOKEN" and session.ofs == 0 and session.aid == 0


def test_forgetting_drops_the_screen_and_its_token_then_reconnects(tmp_path):
    QCoreApplication.instance() or QCoreApplication([])
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings.setValue("cast/screenId", "old-screen-identity")
    lounge = Lounge(settings, "Tubify")
    connects = []
    lounge._connect = lambda: connects.append(lounge.screen_id)
    lounge.start()
    assert connects == ["old-screen-identity"]
    lounge.session.token, lounge.session.token_expiry = "TOKEN", 9e12
    lounge.forget()
    assert connects[-1] == "" and not settings.contains("cast/screenId") and lounge.session.token == ""
    lounge.stop()
    lounge.forget()
    assert len(connects) == 2


def test_a_remote_session_binds_without_screen_capabilities():
    session = LoungeSession("00000000-0000-4000-8000-000000000000", "Tubify", role="remote")
    session.token = "TOKEN"
    init = parse_qs(session.query("init"))
    assert init["device"] == ["REMOTE_CONTROL"] and init["app"] == ["tubify-listen-along"] and init["mdx-version"] == ["3"]
    assert "deviceInfo" not in init and "capabilities" not in init and init["loungeIdToken"] == ["TOKEN"]


def test_prefixes_keep_screens_apart_and_cast_keeps_its_keys(tmp_path):
    QCoreApplication.instance() or QCoreApplication([])
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings.setValue("cast/screenId", "cast-screen-identity")
    cast = Lounge(settings, "Tubify")
    host = Lounge(settings, "Tubify", prefix="listenAlong")
    assert cast.screen_id == "cast-screen-identity" and host.screen_id == ""
    assert settings.contains("cast/deviceId") and settings.contains("listenAlong/deviceId")
    assert settings.value("cast/deviceId") != settings.value("listenAlong/deviceId")
    host.forget()
    assert settings.value("cast/screenId") == "cast-screen-identity"


def test_a_remote_uses_its_given_screen_and_stops_when_the_host_retires_it(tmp_path):
    QCoreApplication.instance() or QCoreApplication([])
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    remote = Lounge(settings, "Tubify", prefix="listenAlongRemote", role="remote", screen_id="host-screen-identity")
    assert remote.screen_id == "host-screen-identity" and not settings.contains("listenAlongRemote/screenId")
    posts, states = [], []
    remote._post = lambda url, form, done, track=True: posts.append((url, form, done))
    remote.stateChanged.connect(states.append)
    remote.start()
    assert posts[0][0].endswith("/pairing/get_lounge_token_batch") and posts[0][1] == {"screen_ids": "host-screen-identity"}
    posts[0][2](404, "")
    assert states[-1] == "unavailable" and not remote._running and not remote.retry.isActive()
    assert Lounge(settings, "Tubify", role="remote", screen_id="bad id!").screen_id == ""
