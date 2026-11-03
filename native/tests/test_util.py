import errno
import os

import pytest

from youtube_music_native.util import atomic_write, needs_reconnect, parse_duration, prepend_paths


def test_atomic_write_creates_the_folder_and_replaces_text_or_bytes(tmp_path):
    target = tmp_path / "state" / "queue.json"
    atomic_write(target, "first")
    atomic_write(target, b"second")
    assert target.read_bytes() == b"second"
    assert [path.name for path in target.parent.iterdir()] == ["queue.json"]


def test_atomic_write_keeps_the_old_file_and_no_temporary_when_replacing_fails(tmp_path, monkeypatch):
    target = tmp_path / "queue.json"
    target.write_text("kept")

    def refuse(*args):
        raise OSError(errno.EACCES, "denied")

    monkeypatch.setattr(os, "replace", refuse)
    with pytest.raises(OSError):
        atomic_write(target, "lost")
    assert target.read_text() == "kept"
    assert [path.name for path in tmp_path.iterdir()] == ["queue.json"]


@pytest.mark.parametrize(("value", "seconds"), [
    (221, 221.), ("3:41", 221.), ("1:02:03", 3723.), ("2.5", 2.5), (None, 0.), ("", 0.),
    ("live", 0.), (-4, 0.), (float("nan"), 0.), (float("inf"), 0.), ([], 0.),
])
def test_parse_duration_accepts_numbers_and_labels(value, seconds):
    assert parse_duration(value) == seconds


def test_prepend_paths_adds_only_missing_entries_in_front():
    environ = {"PATH": "b;c"}
    prepend_paths(environ, "PATH", ["a", "b"], ";")
    assert environ["PATH"] == "a;b;c"
    prepend_paths(environ, "PATH", ["a"], ";")
    assert environ["PATH"] == "a;b;c"
    empty = {}
    prepend_paths(empty, "LIBS", ["x"])
    assert empty["LIBS"] == "x"


def test_needs_reconnect_reads_the_worker_error_code():
    assert needs_reconnect({"code": "reconnect"}) and needs_reconnect({"code": "AuthError"})
    assert not needs_reconnect({"code": "offline"}) and not needs_reconnect({})
