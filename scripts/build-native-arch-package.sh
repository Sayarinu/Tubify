#!/usr/bin/env bash
set -euo pipefail

native_repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$native_repo_root"
if [[ -n "$(git status --porcelain)" ]]; then
  printf '%s\n' 'Refusing to package a dirty checkout. Commit or stash changes first.' >&2
  exit 1
fi
native_version="$(python -c 'import pathlib,tomllib; print(tomllib.loads(pathlib.Path("native/pyproject.toml").read_text())["project"]["version"])')"
native_pkgver="$(awk -F= '/^pkgver=/{print $2; exit}' packaging/arch-native/PKGBUILD)"
if [[ "$native_version" != "$native_pkgver" ]]; then
  printf '%s\n' 'Native Python and Arch package versions differ.' >&2
  exit 1
fi
native_build_root="$(mktemp -d "${TMPDIR:-/tmp}/youtube-music-native-build.XXXXXX")"
trap 'rm -rf "$native_build_root"' EXIT
native_output="$native_repo_root/dist/native"
mkdir -p "$native_output"
cp packaging/arch-native/PKGBUILD "$native_build_root/PKGBUILD"
git archive --format=tar.gz --prefix="youtube-music-native-${native_version}/" \
  --output="$native_build_root/youtube-music-native-${native_version}.tar.gz" HEAD native packaging/arch-native scripts/native-appcast.py
native_digest="$(sha256sum "$native_build_root/youtube-music-native-${native_version}.tar.gz" | cut -d' ' -f1)"
printf '\nsha256sums=(%s)\n' "$native_digest" >> "$native_build_root/PKGBUILD"
export PKGDEST="$native_output" SRCPKGDEST="$native_output"
cd "$native_build_root"
makepkg --cleanbuild "$@"
makepkg --allsource --force
