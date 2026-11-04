#!/usr/bin/env python3
"""Open ticket PRs, or a GitHub stack of them, and wait for their checks.

  scripts/open-prs.py                                 this branch into experimental
  scripts/open-prs.py LUNE-1 LUNE-2 LUNE-3            a stack into experimental, bottom first
  scripts/open-prs.py --into stable                   release experimental into main
  scripts/open-prs.py --into stable LUNE-1            urgent fix into main

Each PR takes its title from the subject of its branch's first commit and its description from
that commit's body. --check-pr applies the same naming and commit email rules in CI.
"""

import argparse
import os
import re
import subprocess
import sys
import time

TRUNKS = {"experimental": "experimental", "stable": "main"}
TICKET = re.compile(r"LUNE-\d+")
# Commit identities are public, so only GitHub's private addresses are allowed.
PRIVATE_EMAIL = re.compile(r"noreply@github\.com|(?:\d+\+)?[\w-]+(?:\[bot\])?@users\.noreply\.github\.com")
# Checks can take a moment to appear on a new PR.
CHECKS_APPEAR_TRIES = 20
CHECKS_APPEAR_WAIT = 15


def subject_problem(branch, subject):
    if not re.fullmatch(re.escape(branch) + r" - \S.*", subject):
        return f'"{subject}" must look like "{branch} - Change-specific message".'
    return None


def pr_problems(head, base, title, fork=False):
    """What a PR breaks in the branch policy. The naming rules in AGENTS.md apply to this repository's branches, not to forks."""
    if fork:
        return [] if base in TRUNKS.values() else [f'Base "{base}" must be experimental or main.']
    if head == "experimental" and base == "main":
        return []
    if head == "main" and base == "experimental":
        return []
    problems = []
    if not TICKET.fullmatch(head):
        problems.append(f'Branch "{head}" must be exactly a ticket identifier such as LUNE-123.')
    elif problem := subject_problem(head, title):
        problems.append("Title " + problem)
    if base not in TRUNKS.values() and not TICKET.fullmatch(base):
        problems.append(f'Base "{base}" must be experimental, main or the ticket branch below it in a stack.')
    return problems


def exposed_email_commits(log):
    """Commits in `git log --format="%h %ae %ce"` output using an email outside GitHub's private addresses."""
    rows = (line.split() for line in log.splitlines() if line.strip())
    return [row[0] for row in rows if not all(PRIVATE_EMAIL.fullmatch(email) for email in row[1:])]


def email_problems(revisions):
    # Names the commits only: printing the address here would publish it in the CI log.
    commits = exposed_email_commits(output("git", "log", "--format=%h %ae %ce", revisions))
    return [f"Commit {commit} must use a GitHub noreply email address, not a personal one." for commit in commits]


def split_message(message):
    subject, _, body = message.strip().partition("\n")
    return subject.strip(), body.strip()


def run(*command, check=True):
    result = subprocess.run(command, capture_output=True, text=True)
    if check and result.returncode:
        raise SystemExit(f"{' '.join(command)} failed:\n{result.stderr.strip() or result.stdout.strip()}")
    return result


def output(*command):
    return run(*command).stdout.strip()


def describe(branch, parent):
    """Check a branch against the one below it and return its PR title and description."""
    if not TICKET.fullmatch(branch):
        raise SystemExit(f'Branch "{branch}" must be exactly a ticket identifier such as LUNE-123.')
    if run("git", "merge-base", "--is-ancestor", parent, branch, check=False).returncode:
        raise SystemExit(f"{branch} is not based on {parent}. Rebase it first.")
    # Merges bring a fix up from the branch below; they squash away when the PR merges.
    commits = output("git", "rev-list", "--reverse", "--no-merges", f"{parent}..{branch}").split()
    if not commits:
        raise SystemExit(f"{branch} has no commits on top of {parent}.")
    if problems := email_problems(f"{parent}..{branch}"):
        raise SystemExit("\n".join(problems))
    for commit in commits:
        problem = subject_problem(branch, split_message(output("git", "log", "-1", "--format=%B", commit))[0])
        if problem:
            raise SystemExit(problem)
    return split_message(output("git", "log", "-1", "--format=%B", commits[0]))


def pr_number(branch):
    found = output("gh", "pr", "list", "--head", branch, "--state", "open", "--json", "number", "--jq", ".[0].number // empty")
    return int(found) if found else None


def open_single(branch, base, title, body):
    run("git", "push", "-u", "origin", branch)
    number = pr_number(branch)
    if number:
        run("gh", "pr", "edit", str(number), "--title", title, "--body", body, "--base", base)
    else:
        run("gh", "pr", "create", "--head", branch, "--base", base, "--title", title, "--body", body)
        number = pr_number(branch)
    return number


def open_stack(branches, trunk):
    # Creates the stack, or grows the one these branches are already in. Runs again safely.
    run("gh", "stack", "link", "--open", "--base", trunk, *branches)


def wait_for_checks(number):
    """Watch one PR's checks; True when they all pass."""
    for _ in range(CHECKS_APPEAR_TRIES):
        probe = run("gh", "pr", "checks", str(number), check=False)
        if "no checks reported" not in (probe.stderr + probe.stdout):
            break
        time.sleep(CHECKS_APPEAR_WAIT)
    else:
        print(f"#{number}: no checks appeared.", file=sys.stderr)
        return False
    return subprocess.run(["gh", "pr", "checks", str(number), "--watch", "--interval", "30"], stdout=subprocess.DEVNULL).returncode == 0


def main(arguments=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("branches", nargs="*", help="Ticket branches, bottom of the stack first; default: the current branch")
    parser.add_argument("--into", choices=sorted(TRUNKS), default="experimental", help="Release channel to target")
    parser.add_argument("--feature", action="append", default=[], metavar="BRANCH", help="Label this branch's PR as a Feature (minor version bump)")
    parser.add_argument("--no-wait", action="store_true", help="Don't wait for the PR checks")
    parser.add_argument("--check-pr", action="store_true", help="CI: check PR_HEAD, PR_BASE, PR_TITLE, PR_FORK and the commit emails against the branch policy")
    options = parser.parse_args(arguments)

    if options.check_pr:
        fork = os.environ.get("PR_FORK") == "true"
        problems = pr_problems(os.environ["PR_HEAD"], os.environ["PR_BASE"], os.environ["PR_TITLE"], fork)
        if not fork:
            problems += email_problems(f'{os.environ["PR_BASE_SHA"]}..{os.environ["PR_HEAD_SHA"]}')
        for problem in problems:
            print(f"::error title=PR policy::{problem}")
        return 1 if problems else 0

    trunk = TRUNKS[options.into]
    run("git", "fetch", "origin")
    if output("git", "status", "--porcelain", "--untracked-files=no"):
        raise SystemExit("Commit or stash your changes first.")

    if options.into == "stable" and not options.branches:
        version_note = "Merge with a merge commit, never squash or rebase, so both branches keep the same history."
        number = pr_number("experimental")
        if not number:
            run("gh", "pr", "create", "--head", "experimental", "--base", "main", "--title", "Release experimental to stable", "--body", version_note)
            number = pr_number("experimental")
        numbers = [number]
    else:
        branches = options.branches or [output("git", "branch", "--show-current")]
        details = {}
        parent = "origin/" + trunk
        for branch in branches:
            details[branch] = describe(branch, parent)
            parent = branch
        if len(branches) == 1:
            numbers = [open_single(branches[0], trunk, *details[branches[0]])]
        else:
            open_stack(branches, trunk)
            numbers = []
            for branch in branches:
                number = pr_number(branch)
                if not number:
                    raise SystemExit(f"{branch} has no PR after submitting the stack.")
                # gh stack writes its own titles; the release notes read these.
                run("gh", "pr", "edit", str(number), "--title", details[branch][0], "--body", details[branch][1])
                numbers.append(number)
        for branch in options.feature:
            run("gh", "pr", "edit", str(numbers[branches.index(branch)]), "--add-label", "Feature")

    for number in numbers:
        print(output("gh", "pr", "view", str(number), "--json", "url", "--jq", ".url"))
    if options.no_wait:
        return 0
    failed = [number for number in numbers if not wait_for_checks(number)]
    for number in numbers:
        print(f"#{number}: {'checks failed' if number in failed else 'checks passed'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
