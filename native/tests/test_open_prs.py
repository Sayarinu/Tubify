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


def test_fork_pull_requests_skip_the_naming_rules():
    assert open_prs.pr_problems("patch-1", "experimental", "Fix a typo", fork=True) == []
    assert open_prs.pr_problems("patch-1", "main", "Fix a typo", fork=True) == []
    assert "Base" in open_prs.pr_problems("patch-1", "LUNE-1", "Fix a typo", fork=True)[0]
    # The same names on a branch in this repository are still rejected.
    assert open_prs.pr_problems("patch-1", "experimental", "Fix a typo")


def test_commit_message_becomes_title_and_description():
    assert open_prs.split_message("LUNE-1 - Change\n\n## Why\n\nBecause.\n") == ("LUNE-1 - Change", "## Why\n\nBecause.")
    assert open_prs.split_message("LUNE-1 - Change") == ("LUNE-1 - Change", "")


@pytest.mark.parametrize("email", [
    "12345+name@users.noreply.github.com",
    "name@users.noreply.github.com",
    "dependabot[bot]@users.noreply.github.com",
    "noreply@github.com",
])
def test_github_private_addresses_are_allowed(email):
    assert open_prs.exposed_email_commits(f"abc123 {email} noreply@github.com\n") == []


@pytest.mark.parametrize("email", [
    "someone@example.com",
    "noreply@users.noreply.github.com.example.com",
    "x@github.com",
])
def test_other_addresses_are_rejected_for_author_or_committer(email):
    assert open_prs.exposed_email_commits(f"abc123 {email} noreply@github.com\n") == ["abc123"]
    assert open_prs.exposed_email_commits(f"def456 noreply@github.com {email}\n") == ["def456"]


def test_email_check_never_prints_the_address(monkeypatch, capsys):
    monkeypatch.setattr(open_prs, "output", lambda *command: "abc123 someone@example.com noreply@github.com")
    monkeypatch.setenv("PR_HEAD", "LUNE-1")
    monkeypatch.setenv("PR_BASE", "experimental")
    monkeypatch.setenv("PR_TITLE", "LUNE-1 - Change")
    monkeypatch.setenv("PR_BASE_SHA", "base")
    monkeypatch.setenv("PR_HEAD_SHA", "head")
    assert open_prs.main(["--check-pr"]) == 1
    printed = capsys.readouterr().out
    assert "abc123" in printed and "someone@example.com" not in printed


def test_fork_pull_requests_skip_the_email_check(monkeypatch):
    monkeypatch.setattr(open_prs, "output", lambda *command: pytest.fail("a fork's commits are not checked"))
    monkeypatch.setenv("PR_HEAD", "patch-1")
    monkeypatch.setenv("PR_BASE", "experimental")
    monkeypatch.setenv("PR_TITLE", "Fix a typo")
    monkeypatch.setenv("PR_FORK", "true")
    assert open_prs.main(["--check-pr"]) == 0


def test_check_pr_reports_through_the_exit_code(monkeypatch, capsys):
    monkeypatch.setattr(open_prs, "output", lambda *command: "")
    monkeypatch.setenv("PR_BASE_SHA", "base")
    monkeypatch.setenv("PR_HEAD_SHA", "head")
    monkeypatch.setenv("PR_HEAD", "someone/branch")
    monkeypatch.setenv("PR_BASE", "experimental")
    monkeypatch.setenv("PR_TITLE", "Change")
    assert open_prs.main(["--check-pr"]) == 1
    assert "::error" in capsys.readouterr().out
    monkeypatch.setenv("PR_HEAD", "LUNE-1")
    monkeypatch.setenv("PR_TITLE", "LUNE-1 - Change")
    assert open_prs.main(["--check-pr"]) == 0
