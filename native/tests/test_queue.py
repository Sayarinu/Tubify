from youtube_music_native.queue import Queue


def tracks():
    return [{"videoId": "same-song", "title": "First"}, {"videoId": "same-song", "title": "Duplicate"}, {"videoId": "third-song", "title": "Third"}]


def test_duplicate_entries_move_and_removal_preserve_selected_occurrence():
    queue = Queue()
    queue.replace(tracks(), 1)
    selected = queue.current["key"]
    queue.move(1, 2)
    assert queue.index == 2 and queue.current["key"] == selected
    assert not queue.remove(0)
    assert queue.index == 1 and queue.current["key"] == selected
    assert queue.remove(1)
    assert queue.current["track"]["title"] == "Third"


def test_repeat_shuffle_play_next_and_paused_restart_snapshot():
    queue = Queue()
    queue.replace(tracks())
    first = queue.current["key"]
    queue.toggle_shuffle()
    assert queue.current["key"] == first
    assert len({entry["key"] for entry in queue.entries}) == 3
    queue.toggle_shuffle()
    assert [entry["track"]["title"] for entry in queue.entries] == ["First", "Duplicate", "Third"]
    queue.append([{"videoId": "inserted", "title": "Play next"}], next=True)
    assert queue.advance()["track"]["title"] == "Play next"
    queue.repeat = "one"
    assert queue.advance(automatic=True)["track"]["title"] == "Play next"
    assert queue.advance()["track"]["title"] == "Duplicate"
    queue.repeat = "all"
    queue.select(3)
    assert queue.advance()["key"] == first
    restored = Queue()
    assert restored.restore(queue.snapshot(position=73.5)) == 73.5
    assert restored.current["key"] == first and restored.repeat == "all"


def test_last_track_stays_selected_at_end_and_bad_state_is_ignored():
    queue = Queue()
    queue.replace(tracks(), 2)
    assert queue.advance(automatic=True) is None
    assert queue.current["track"]["title"] == "Third"
    assert Queue().restore({"entries": [{"key": "broken"}]}) == 0
