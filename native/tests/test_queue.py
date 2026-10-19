from copy import deepcopy

import pytest

from youtube_music_native.queue import Queue


def tracks(*names):
    return [{"videoId": "same-song" if name in {"A", "B"} else name, "title": name} for name in (names or ("A", "B", "C"))]


def names(entries):
    return [entry["track"]["title"] for entry in entries]


def test_fifo_play_next_and_context_replacement_preserve_pending_manual_entries():
    queue = Queue()
    queue.replace(tracks())
    queue.append(tracks("M", "N"))
    queue.append(tracks("X", "Y"), next=True)
    queue.append_context(tracks("D"))
    assert names(queue.entries) == ["A", "X", "Y", "M", "N", "B", "C", "D"]
    assert queue.advance()["track"]["title"] == "X"
    queue.replace(tracks("E", "F"))
    assert not queue.history
    assert names(queue.entries) == ["E", "Y", "M", "N", "F"]
    assert [queue.advance()["track"]["title"] for _ in range(4)] == ["Y", "M", "N", "F"]
    assert queue.advance() is None


def test_selection_history_and_removal_are_occurrence_based():
    queue = Queue()
    queue.replace(tracks())
    original = queue.current["key"]
    queue.append(tracks("M", "M", "N"))
    duplicate = queue.manual[1]["key"]
    queue.select(2)
    assert queue.current["key"] == duplicate and names(queue.manual) == ["N"]
    queue.select(2)  # B, while preserving N.
    assert names(queue.manual) == ["N"]
    assert queue.previous()["key"] == duplicate
    assert queue.previous()["key"] == original
    assert not queue.previous()
    assert names(queue.manual) == ["N"]  # Played entries never return to pending.
    assert queue.advance()["track"]["title"] == "N"
    assert queue.remove(0)
    assert queue.current["track"]["title"] == "B"


def test_reorder_only_within_pending_groups_and_clear_keeps_current_and_source():
    queue = Queue()
    queue.replace(tracks())
    queue.append(tracks("M", "N"))
    queue.move(1, 2)
    assert names(queue.manual) == ["N", "M"]
    queue.move(3, 4)
    assert names(queue.remaining) == ["C", "B"]
    before = queue.snapshot()
    queue.move(0, 1)
    queue.move(2, 3)
    assert queue.snapshot() == before
    queue.remove(2)
    assert names(queue.manual) == ["N"]
    queue.clear_manual()
    assert names(queue.entries) == ["A", "C", "B"]


def test_shuffle_repeat_source_and_manual_one_time(monkeypatch):
    monkeypatch.setattr("youtube_music_native.queue.random.shuffle", lambda values: values.reverse())
    queue = Queue()
    queue.replace(tracks())
    queue.append(tracks("M", "N"))
    queue.toggle_shuffle()
    assert names(queue.entries) == ["A", "M", "N", "C", "B"]
    queue.toggle_shuffle()
    assert names(queue.entries) == ["A", "M", "N", "B", "C"]
    queue.advance()
    queue.repeat = "one"
    assert queue.peek(automatic=True) is queue.current
    assert queue.advance(automatic=True)["track"]["title"] == "M"
    assert queue.advance()["track"]["title"] == "N"
    queue.repeat = "all"
    assert [queue.advance()["track"]["title"] for _ in range(5)] == ["B", "C", "A", "B", "C"]
    assert not queue.manual


def test_shuffle_all_and_context_pagination_do_not_touch_manual_order(monkeypatch):
    monkeypatch.setattr("youtube_music_native.queue.random.shuffle", lambda values: values.reverse())
    queue = Queue()
    queue.replace(tracks())
    queue.append(tracks("M", "N"))
    queue.shuffle_all()
    assert queue.current["track"]["title"] == "C"
    queue.append_context(tracks("D"))
    queue.toggle_shuffle()
    assert names(queue.entries) == ["C", "M", "N", "A", "B", "D"]


def test_empty_enqueue_selects_first_and_repeat_all_does_not_replay_manual_only_queue():
    queue = Queue()
    queue.append(tracks("M", "N"))
    assert names(queue.entries) == ["M", "N"] and not queue.source
    queue.repeat = "all"
    assert queue.advance()["track"]["title"] == "N"
    assert queue.peek() is None and queue.advance() is None
    assert queue.remove(0) and queue.current is None


def test_version_two_roundtrip_preserves_groups_history_keys_and_position():
    queue = Queue()
    queue.replace(tracks(), source_label="Evening mix")
    queue.append(tracks("M", "N"))
    queue.advance()
    queue.repeat, queue.shuffled = "all", True
    saved = queue.snapshot(73.5)
    restored = Queue()
    assert restored.restore(deepcopy(saved)) == 73.5
    assert restored.snapshot(73.5) == saved
    assert restored.previous()["track"]["title"] == "A"
    assert names(restored.manual) == ["N"]


def test_legacy_queue_migrates_as_source_without_changing_occurrences_or_settings():
    entries = [{"key": str(index), "track": track} for index, track in enumerate(tracks())]
    saved = {"version": 1, "entries": entries, "index": 1, "position": 24.5, "repeat": "one", "shuffled": True, "original": ["2", "0", "1"]}
    restored = Queue()
    assert restored.restore(saved) == 24.5
    assert restored.source == entries and not restored.manual
    assert restored.current == entries[1]
    assert restored._original == saved["original"] and restored.shuffled and restored.repeat == "one"
    assert restored.snapshot()["version"] == 2
    restored.repeat = "all"
    restored.advance()
    assert restored.advance()["key"] == "0"


@pytest.mark.parametrize("mutate", [
    lambda state: state.update(version=3),
    lambda state: state.update(position=float("nan")),
    lambda state: state.update(current="missing"),
    lambda state: state.update(source_index=999),
    lambda state: state["manual"].append(state["source"][0]),
    lambda state: state["entries"].append(state["entries"][0]),
    lambda state: state.update(history=[{}]),
])
def test_invalid_state_is_rejected_atomically(mutate):
    queue = Queue()
    queue.replace(tracks())
    before = deepcopy(queue.snapshot())
    invalid = deepcopy(before)
    mutate(invalid)
    assert queue.restore(invalid) == 0 and queue.snapshot() == before


def test_previous_next_replays_source_without_reinserting_consumed_manual():
    queue = Queue()
    queue.replace(tracks())
    queue.advance()
    queue.previous()
    assert names(queue.remaining) == ["B", "C"]
    assert queue.advance()["track"]["title"] == "B"
    queue.append(tracks("M"))
    queue.advance()
    queue.advance()
    assert queue.current["track"]["title"] == "C"
    queue.previous()
    assert queue.current["track"]["title"] == "M" and not queue.manual
    assert queue.advance()["track"]["title"] == "C"


def test_removing_source_anchor_keeps_history_continuation_valid():
    queue = Queue()
    queue.replace(tracks())
    queue.append(tracks("M"))
    queue.advance()
    queue.advance()
    queue.previous()
    queue.previous()
    assert queue.current["track"]["title"] == "A"
    queue.remove(0)
    restored = Queue()
    restored.restore(queue.snapshot())
    assert restored.snapshot() == queue.snapshot()
