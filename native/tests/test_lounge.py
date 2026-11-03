from urllib.parse import parse_qs

import pytest

from youtube_music_native.lounge import FrameParser, LoungeSession, encode_messages


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
