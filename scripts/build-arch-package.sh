#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
pkgname='youtube-music-app'
cd "$repo_root"

if [[ -n "$(git status --porcelain)" ]]; then
  printf '%s\n' 'Refusing to package a dirty checkout. Commit or stash changes first.' >&2
  exit 1
fi

version="$(node -p "require('./package.json').version")"
pkgver="$(awk -F= '/^pkgver=/{gsub(/['\'' \t]/, "", $2); print $2; exit}' packaging/arch/PKGBUILD)"

if [[ "$version" != "$pkgver" ]]; then
  printf 'Version mismatch: package.json is %s but PKGBUILD is %s.\n' "$version" "$pkgver" >&2
  exit 1
fi

archive_path="$repo_root/packaging/arch/${pkgname}-${version}.tar.gz"
build_root="$(mktemp -d "${TMPDIR:-/tmp}/${pkgname}-makepkg.XXXXXX")"
trap 'rm -f "$archive_path"; rm -rf "$build_root"' EXIT

git archive --format=tar.gz --prefix="${pkgname}-${version}/" --output="$archive_path" HEAD
mkdir -p "$repo_root/dist"

(
  cd "$repo_root/packaging/arch"
  BUILDDIR="$build_root" PKGDEST="$repo_root/dist" makepkg --cleanbuild "$@"
)
