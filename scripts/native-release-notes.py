#!/usr/bin/env python3
"""Write short, readable release notes for a Tubify release.

The notes describe what changed since the previous native-v release, using the
titles of the pull requests merged since then. PRs labelled Feature or Major
Release are listed under "New", everything else under "Improvements and
fixes". A download table follows a "---" line; the in-app update popup shows
only the part above it.

Usage: native-release-notes.py VERSION PREVIOUS_TAG OUTPUT
(GITHUB_REPOSITORY and GH_TOKEN must be set; PREVIOUS_TAG may be empty.)
"""
import importlib.util
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("native_release_version", ROOT / "scripts/native-release-version.py")
assert spec and spec.loader
versioning = importlib.util.module_from_spec(spec)
spec.loader.exec_module(versioning)

FEATURE_LABELS = {"feature", "major release", "release:feature", "release:minor", "release:major"}


def clean_title(title):
    """'LUNE-433 - Rank artists properly (#84)' -> 'Rank artists properly'."""
    title = re.sub(r"^\s*[A-Z]+-\d+\s*[-–:]\s*", "", title.strip())
    title = re.sub(r"\s*\(#\d+\)\s*$", "", title)
    return title[:1].upper() + title[1:] if title else ""


def changes(commits, pulls_for):
    """Return (new, improvements) as lists of unique, cleaned PR titles in merge order."""
    new, improvements, seen = [], [], set()
    for sha, subject in commits:
        pulls = pulls_for(sha)
        if not pulls:
            pulls = [{"number": None, "title": subject, "labels": []}]
        for pull in pulls:
            key = pull.get("number") or pull["title"]
            title = clean_title(pull["title"])
            if key in seen or not title:
                continue
            seen.add(key)
            labels = {(label["name"] if isinstance(label, dict) else label).casefold() for label in pull.get("labels", [])}
            (new if labels & FEATURE_LABELS else improvements).append(title)
    return new, improvements


def downloads(version, repository):
    base = f"https://github.com/{repository}/releases/download/native-v{version}/"
    files = (("Windows", f"Tubify-{version}-windows-x64-setup.exe", "Windows 10 or 11, 64-bit"),
             ("macOS", f"Tubify-{version}-macos-arm64.dmg", "macOS 12 or later, Apple silicon"),
             ("Linux", f"Tubify-{version}-linux-x86_64.pkg.tar.zst", "x86_64 Linux with pacman (sudo pacman -U the file)"))
    rows = "\n".join(f"| {name} | [{file}]({base}{file}) | {needs} |" for name, file, needs in files)
    return f"| Platform | Download | Requirements |\n|---|---|---|\n{rows}"


def render(version, new, improvements, repository):
    lines = []
    if new:
        lines += ["### New", *[f"- {title}" for title in new], ""]
    if improvements:
        lines += ["### Improvements and fixes", *[f"- {title}" for title in improvements], ""]
    if not lines:
        lines = ["Maintenance release.", ""]
    lines += ["---", "", "### Download", "", downloads(version, repository), "",
              "Already using Tubify? It updates itself; look for the update icon in the top right."]
    return "\n".join(lines) + "\n"


def main(argv):
    version, previous, output = argv[1], argv[2], Path(argv[3])
    repository, token = os.environ["GITHUB_REPOSITORY"], os.environ["GH_TOKEN"]
    span = [f"{previous}..HEAD"] if previous else ["-n", "20", "HEAD"]
    log = subprocess.run(["git", "log", "--no-merges", "--format=%H%x09%s", *span], cwd=ROOT, check=True, capture_output=True, text=True).stdout
    # Oldest first, so the notes read in the order changes landed.
    commits = [tuple(line.split("\t", 1)) for line in log.splitlines() if "\t" in line][::-1]
    new, improvements = changes(commits, versioning.github_pulls(repository, token))
    output.write_text(render(version, new, improvements, repository), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
