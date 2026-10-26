import pytest
from PySide6.QtCore import QCoreApplication

from youtube_music_native.playback import Playback
from youtube_music_native.playback_options import PlaybackOptions
from test_playback import FakeAudio


def track(identifier, rating=None):
    return {"videoId": identifier, "title": identifier, "duration": 100, "rating": rating}


def player_at(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    return Playback(tmp_path, None, fixture={"shelves": [{"items": [track("current")]}]})


@pytest.mark.parametrize("preset", PlaybackOptions.PRESETS)
def test_sleep_timer_pauses_at_deadline_and_never_resumes(tmp_path, preset):
    player = player_at(tmp_path)
    now = [1000.]
    options = PlaybackOptions(tmp_path / "settings.ini", player, clock=lambda: now[0])
    assert not options.timer.isActive() and not options.sleepRemaining
    options.startSleep(preset)
    assert options.sleepRemaining == preset * 60 and player.playing
    now[0] += preset * 60 - 0.2
    options.tick()
    assert options.sleepRemaining == 1 and player.playing
    now[0] += 0.3
    options.tick()
    assert options.sleepRemaining == 0 and not player.playing
    assert "Playback paused" in options.sleepStatus and not options.timer.isActive()
    options.tick()
    assert not player.playing
    options.close()
    player.close()


def test_timer_cancel_replace_invalid_preset_and_restart(tmp_path):
    player = player_at(tmp_path)
    now = [0.]
    path = tmp_path / "settings.ini"
    options = PlaybackOptions(path, player, clock=lambda: now[0])
    options.startSleep(5)
    options.startSleep(10)
    options.startSleep(7)
    assert options.sleepRemaining == 600
    options.cancelSleep()
    now[0] = 1000
    options.tick()
    assert player.playing and not options.sleepRemaining and not options.timer.isActive()
    options.startSleep(5)
    restored = PlaybackOptions(path, player)
    assert not restored.timer.isActive() and not restored.sleepRemaining
    options.close()
    restored.close()
    player.close()


def test_preferences_default_off_and_volume_mapping_preserves_slider_value(tmp_path):
    player = player_at(tmp_path)
    player.audio = FakeAudio()
    options = PlaybackOptions(tmp_path / "settings.ini", player)
    assert not options.nonlinearVolume and not options.skipDisliked
    player.setVolume(50)
    assert player.audio.level == 50
    options.setNonlinearVolume(True)
    assert player._volume == 50 and player.audio.level == 25
    for value in (0, 1, 20, 50, 100):
        player.setVolume(value)
        assert player.audio.level == value * value / 100
    options.setNonlinearVolume(False)
    assert player.audio.level == 100
    options.setSkipDisliked(True)
    restored = PlaybackOptions(tmp_path / "settings.ini", player)
    assert restored.skipDisliked and not restored.nonlinearVolume
    options.close()
    restored.close()
    player.close()


@pytest.mark.parametrize("repeat", ["off", "all", "one"])
def test_skip_disliked_forward_transitions_manual_source_and_safe_exhaustion(tmp_path, repeat):
    player = player_at(tmp_path)
    player.playTracks([track("a"), track("b", "DISLIKE"), track("c")])
    player.setRepeat(repeat)
    player.enqueue([track("manual", "DISLIKE")])
    player.setSkipDisliked(True)
    assert player.currentTrack["videoId"] == "a" and player.playing
    player.next()
    assert player.currentTrack["videoId"] == "c" and player.playing
    assert not player.queue.manual
    player.playTracks([track("a", "DISLIKE"), track("b", "DISLIKE")])
    player._advance(automatic=True)
    assert not player.playing and player.stopped and "No eligible" in player.message
    assert len(player.queue.history) <= 4
    player.close()


def test_skip_disabled_previous_and_paused_restore_keep_existing_behavior(tmp_path):
    player = player_at(tmp_path)
    player.playTracks([track("a", "DISLIKE"), track("b", "DISLIKE")])
    player.next()
    assert player.currentTrack["videoId"] == "b" and player.playing
    player.setSkipDisliked(True)
    player.previous()
    assert player.currentTrack["videoId"] == "a"
    player.pause()
    player._restore_current()
    assert player.currentTrack["videoId"] == "a" and not player.playing
    player.close()


def test_disliked_filter_applies_to_autoplay_and_failed_song_transitions(tmp_path):
    player = player_at(tmp_path)
    player.setSkipDisliked(True)
    player.playTracks([track("bad"), track("disliked", "DISLIKE"), track("good")])
    player._skip_failed()
    assert player.currentTrack["videoId"] == "good"
    player._radio_request = 17
    player._radio_result(17, {"items": [track("disliked-radio", "DISLIKE"), track("radio")]})
    assert player.currentTrack["videoId"] == "radio"
    assert all(entry["track"]["videoId"] != "disliked-radio" for entry in player.queue.source)
    player._radio_request = 18
    player._radio_result(18, {"items": [track("disliked-radio", "DISLIKE")]})
    assert not player.playing and player.stopped
    player.close()


def test_sleep_expiry_wins_over_pending_autoplay_and_failure_callbacks(tmp_path):
    player = player_at(tmp_path)
    now = [0.]
    options = PlaybackOptions(tmp_path / "settings.ini", player, clock=lambda: now[0])
    options.startSleep(5)
    player._radio_request, player._busy = 17, True
    now[0] = 301
    options.tick()
    player._radio_result(17, {"items": [track("late-radio")]})
    assert not player.playing and player._want_paused
    player.playTracks([track("failed"), track("next")])
    options.startSleep(5)
    now[0] += 301
    options.tick()
    player._skip_failed()
    assert player.currentTrack["videoId"] == "failed" and not player.playing
    options.close()
    player.close()


@pytest.mark.parametrize("paused", [False, True])
def test_remove_current_skips_disliked_and_preserves_pause_intent(tmp_path, paused):
    player = player_at(tmp_path)
    player.playTracks([track("a"), track("b", "DISLIKE"), track("c")])
    player.setSkipDisliked(True)
    if paused:
        player.pause()
    player.removeKey(player.queue.current["key"])
    assert player.currentTrack["videoId"] == "c"
    assert player.playing is not paused
    player.close()


def test_speaker_fill_defaults_off_persists_and_reaches_existing_or_later_audio(tmp_path):
    from test_playback import FakeWorker, TRACKS
    app = QCoreApplication.instance() or QCoreApplication([])
    worker = FakeWorker()
    player = Playback(tmp_path, worker, audio_factory=FakeAudio)
    options = PlaybackOptions(tmp_path / "settings.ini", player)
    assert not options.speakerFill and player.audio is None
    options.setSpeakerFill(True)
    player.playTracks(TRACKS[:1])
    worker.succeeded.emit(1, {"kind": "local", "source": "/fixture/track.wav"})
    assert player.audio.speaker_fill
    player.audio.optionsChanged.emit({"available": True, "active": True})
    assert player.audioOptions["active"]
    restored = PlaybackOptions(tmp_path / "settings.ini", player)
    assert restored.speakerFill
    restored.setSpeakerFill(False)
    assert not player.audio.speaker_fill
    options.close()
    restored.close()
    player.close()
