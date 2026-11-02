import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/native-release-version.py"
if not SCRIPT.exists():
    # The Arch source package runs these tests without the repository's CI scripts.
    pytest.skip("release tooling is not part of this source tree", allow_module_level=True)
spec = importlib.util.spec_from_file_location("native_release_version", SCRIPT)
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def test_small_changes_bump_patch_features_bump_minor_and_major_resets():
    assert release.bump((0, 1, 1), release.PATCH) == (0, 1, 2)
    assert release.bump((0, 1, 7), release.MINOR) == (0, 2, 0)
    assert release.bump((0, 4, 2), release.MAJOR) == (1, 0, 0)


def test_largest_labelled_change_since_the_last_release_wins():
    labels = {"a": {"bug"}, "b": {"release:feature"}, "c": set()}.get
    assert release.release_level(["a", "c"], labels) == release.PATCH
    assert release.release_level(["a", "b", "c"], labels) == release.MINOR
    assert release.release_level(["a"], lambda sha: {"release:major"}) == release.MAJOR


def test_declared_version_wins_when_started_by_hand():
    assert release.next_version((0, 1, 7), release.PATCH, (0, 1, 2)) == (0, 1, 8)
    assert release.next_version((0, 1, 7), release.PATCH, (0, 3, 0)) == (0, 3, 0)


def test_main_push_bumps_the_previous_tag_and_other_events_keep_their_version(monkeypatch):
    monkeypatch.setattr(release, "declared", lambda: (0, 1, 2))
    monkeypatch.setattr(release, "previous_tag", lambda ref="HEAD": "native-v0.1.7")
    monkeypatch.setattr(release, "git", lambda *args: "a\nb\n")
    main = {"GITHUB_EVENT_NAME": "push", "GITHUB_REF": "refs/heads/main"}
    assert release.release_version(main, labels=lambda sha: set()) == ("0.1.8", "patch", "native-v0.1.7")
    assert release.release_version(main, labels=lambda sha: {"release:feature"} if sha == "b" else set()) == ("0.2.0", "feature", "native-v0.1.7")
    assert release.release_version({"GITHUB_EVENT_NAME": "push", "GITHUB_REF": "refs/tags/native-v0.3.0"})[0] == "0.3.0"
    assert release.release_version({"GITHUB_EVENT_NAME": "pull_request", "GITHUB_REF": "refs/pull/9/merge"})[0] == "0.1.2"
