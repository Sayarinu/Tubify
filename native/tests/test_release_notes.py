import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/native-release-notes.py"
if not SCRIPT.exists():
    pytest.skip("release tooling is not part of this source tree", allow_module_level=True)
spec = importlib.util.spec_from_file_location("native_release_notes", SCRIPT)
notes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notes)


def test_notes_group_cleaned_pr_titles_and_link_each_download():
    pulls = {
        "a": [{"number": 85, "title": "LUNE-434 - Play music videos inline in the expanded player", "labels": [{"name": "Feature"}]}],
        "b": [{"number": 88, "title": "LUNE-438 - point update URLs at the renamed repository", "labels": []}],
        "c": [],
    }
    new, improvements = notes.changes([("a", "x"), ("b", "y"), ("c", "Fix typo (#90)"), ("a", "dup")], pulls.get)
    assert new == ["Play music videos inline in the expanded player"]
    assert improvements == ["Point update URLs at the renamed repository", "Fix typo"]
    text = notes.render("0.2.1", new, improvements, "Sayarinu/Tubify")
    above, below = text.split("\n---\n")
    assert "### New\n- Play music videos" in above and "### Improvements and fixes" in above
    assert "native-v0.2.1/Tubify-0.2.1-linux-x86_64.pkg.tar.zst" in below and "windows-x64-setup.exe" in below


def test_popup_shows_only_the_changes_without_markdown_headings():
    from youtube_music_native.updates.maintenance import release_notes

    text = notes.render("0.2.1", ["Music videos"], ["Faster start"], "Sayarinu/Tubify")
    assert release_notes(text) == "New\n- Music videos\n\nImprovements and fixes\n- Faster start"
