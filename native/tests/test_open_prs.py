import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/open-prs.py"
if not SCRIPT.exists():
    # The Linux source package runs these tests without the repository's scripts.
    pytest.skip("repository tooling is not part of this source tree", allow_module_level=True)
spec = importlib.util.spec_from_file_location("open_prs", SCRIPT)
open_prs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(open_prs)


@pytest.mark.parametrize("head, base, title", [
    ("LUNE-12", "experimental", "LUNE-12 - Fix the thing"),
    ("LUNE-12", "main", "LUNE-12 - Urgent fix"),
    ("LUNE-13", "LUNE-12", "LUNE-13 - Next change in the stack"),
    ("experimental", "main", "Release experimental to stable"),
    ("main", "experimental", "Merge main back"),
])
def test_allowed_pull_requests(head, base, title):
    assert open_prs.pr_problems(head, base, title) == []


@pytest.mark.parametrize("head, base, title, expected", [
    ("LUNE-12-fix", "experimental", "LUNE-12 - Fix", "must be exactly a ticket"),
    ("agent/LUNE-12", "experimental", "LUNE-12 - Fix", "must be exactly a ticket"),
    ("LUNE-12", "experimental", "Fix the thing", "Title"),
    ("LUNE-12", "experimental", "LUNE-13 - Another ticket", "Title"),
    ("LUNE-12", "experimental", "LUNE-12 - ", "Title"),
    ("LUNE-12", "feature/x", "LUNE-12 - Fix", "Base"),
])
def test_rejected_pull_requests(head, base, title, expected):
    problems = open_prs.pr_problems(head, base, title)
    assert problems and expected in problems[0]


def test_commit_message_becomes_title_and_description():
    assert open_prs.split_message("LUNE-1 - Change\n\n## Why\n\nBecause.\n") == ("LUNE-1 - Change", "## Why\n\nBecause.")
    assert open_prs.split_message("LUNE-1 - Change") == ("LUNE-1 - Change", "")


def test_check_pr_reports_through_the_exit_code(monkeypatch, capsys):
    monkeypatch.setenv("PR_HEAD", "someone/branch")
    monkeypatch.setenv("PR_BASE", "experimental")
    monkeypatch.setenv("PR_TITLE", "Change")
    assert open_prs.main(["--check-pr"]) == 1
    assert "::error" in capsys.readouterr().out
    monkeypatch.setenv("PR_HEAD", "LUNE-1")
    monkeypatch.setenv("PR_TITLE", "LUNE-1 - Change")
    assert open_prs.main(["--check-pr"]) == 0
