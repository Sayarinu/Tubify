#!/usr/bin/env python3
"""Choose the version every native package in this CI run is built and released as.

Every push to main is a release. Its version bumps the latest native-vX.Y.Z tag
already on main, by the largest change merged since that tag:

* a PR labelled ``release:major`` bumps MAJOR (0.4.2 -> 1.0.0)
* a PR labelled ``release:feature`` bumps MINOR (0.1.7 -> 0.2.0)
* anything else is a small change and bumps PATCH (0.1.1 -> 0.1.2)

If native/pyproject.toml declares a higher version, that wins, so a series can
still be started by hand. A pushed native-vX.Y.Z tag builds exactly X.Y.Z, and
pull requests and local builds keep pyproject's version.

``--stamp VERSION`` writes the version into pyproject.toml and the Arch PKGBUILD
and commits it locally (never pushed): the package scripts refuse to build a
dirty checkout and the Arch source archive is taken from HEAD.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "native/pyproject.toml"
PKGBUILD = ROOT / "packaging/arch-native/PKGBUILD"
VERSION_LINE = re.compile(r'^version = "(\d+)\.(\d+)\.(\d+)"$', re.M)
TAG = re.compile(r"native-v(\d+)\.(\d+)\.(\d+)")
LEVELS = {"release:major": 3, "release:feature": 2, "release:minor": 2}
PATCH, MINOR, MAJOR = 1, 2, 3
NAMES = {PATCH: "patch", MINOR: "feature", MAJOR: "major"}


def declared():
    match = VERSION_LINE.search(PYPROJECT.read_text(encoding="utf-8"))
    if not match:
        raise SystemExit("native/pyproject.toml has no MAJOR.MINOR.PATCH version")
    return tuple(int(part) for part in match.groups())


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout


def previous_tag(ref="HEAD"):
    """The newest native-v release already contained in ``ref``."""
    tags = [(tuple(map(int, match.groups())), name) for name in git("tag", "--list", "native-v*", "--merged", ref).split()
            if (match := TAG.fullmatch(name))]
    return max(tags)[1] if tags else None


def bump(version, level):
    major, minor, patch = version
    if level >= MAJOR:
        return (major + 1, 0, 0)
    if level >= MINOR:
        return (major, minor + 1, 0)
    return (major, minor, patch + 1)


def github_labels(repository, token):
    """Return a function giving the labels of the PRs that merged a commit."""
    def labels(sha):
        request = Request(f"https://api.github.com/repos/{repository}/commits/{sha}/pulls",
                          headers={"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}",
                                   "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "tubify-release-version"})
        with urlopen(request, timeout=20) as response:
            pulls = json.load(response)
        return {label["name"] for pull in pulls for label in pull.get("labels", [])}
    return labels


def release_level(commits, labels):
    level = PATCH
    for sha in commits:
        level = max([level] + [LEVELS[name] for name in labels(sha) if name in LEVELS])
    return level


def next_version(base, level, floor):
    return max(bump(base, level), floor)


def text(version):
    return ".".join(map(str, version))


def release_version(environ=os.environ, labels=None):
    """Return (version, level name, previous tag) for this CI event."""
    floor = declared()
    ref, event = environ.get("GITHUB_REF", ""), environ.get("GITHUB_EVENT_NAME", "")
    if ref.startswith("refs/tags/native-v"):
        return ref.removeprefix("refs/tags/native-v"), "tag", ""
    if not (event == "push" and ref == "refs/heads/main"):
        return text(floor), "none", ""
    previous = previous_tag()
    # Every change merged since the last release decides how big this one is.
    commits = git("rev-list", "--no-merges", "--max-count=200", f"{previous}..HEAD").split() if previous else git("rev-list", "-1", "HEAD").split()
    if labels is None:
        labels = github_labels(environ["GITHUB_REPOSITORY"], environ["GH_TOKEN"])
    level = release_level(commits, labels)
    match = TAG.fullmatch(previous) if previous else None
    base = tuple(map(int, match.groups())) if match else floor
    return text(next_version(base, level, floor)), NAMES[level], previous or ""


def stamp(version):
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise SystemExit("Invalid release version: " + version)
    PYPROJECT.write_text(VERSION_LINE.sub(f'version = "{version}"', PYPROJECT.read_text(encoding="utf-8"), count=1), encoding="utf-8")
    PKGBUILD.write_text(re.sub(r"^pkgver=.*$", "pkgver=" + version, PKGBUILD.read_text(encoding="utf-8"), count=1, flags=re.M), encoding="utf-8")
    if subprocess.run(["git", "diff", "--quiet"], cwd=ROOT).returncode:
        subprocess.run(["git", "-c", "user.name=Tubify CI", "-c", "user.email=ci@localhost", "commit", "--quiet", "--no-verify",
                        "-m", "Release " + version, "--", str(PYPROJECT), str(PKGBUILD)], cwd=ROOT, check=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Choose or stamp the native release version.")
    parser.add_argument("--stamp", metavar="VERSION", help="write VERSION into the package files and commit it locally")
    args = parser.parse_args(argv)
    if args.stamp:
        stamp(args.stamp)
        print(args.stamp)
        return 0
    version, level, previous = release_version()
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"version={version}\nlevel={level}\nprevious={previous}\n")
    print(version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
