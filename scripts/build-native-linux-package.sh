#!/usr/bin/env bash
set -euo pipefail

native_repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$native_repo_root"
if [[ -n "$(git status --porcelain)" ]]; then
  printf '%s\n' 'Refusing to package a dirty checkout. Commit or stash changes first.' >&2
  exit 1
fi
native_version="$(python -c 'import pathlib,tomllib; print(tomllib.loads(pathlib.Path("native/pyproject.toml").read_text())["project"]["version"])')"
native_pkgver="$(awk -F= '/^pkgver=/{print $2; exit}' packaging/linux/PKGBUILD)"
if [[ "$native_version" != "$native_pkgver" ]]; then
  printf '%s\n' 'The Python and Linux package versions differ.' >&2
  exit 1
fi
native_build_root="$(mktemp -d "${TMPDIR:-/tmp}/tubify-build.XXXXXX")"
trap 'rm -rf "$native_build_root"' EXIT
native_output="$native_repo_root/dist/native"
mkdir -p "$native_output"
cp packaging/linux/PKGBUILD "$native_build_root/PKGBUILD"
git archive --format=tar.gz --prefix="tubify-${native_version}/" \
  --output="$native_build_root/tubify-${native_version}.tar.gz" HEAD native packaging/linux packaging/bundle_contents.py scripts/native-appcast.py
# The update helper's trust anchor comes from the TUBIFY_UPDATE_PUBLIC_KEY GitHub variable.
[[ "${TUBIFY_UPDATE_PUBLIC_KEY:-}" =~ ^[A-Za-z0-9+/]{43}=$ ]] || { printf '%s\n' 'Set TUBIFY_UPDATE_PUBLIC_KEY: gh variable get TUBIFY_UPDATE_PUBLIC_KEY' >&2; exit 1; }
printf "\n_update_public_key='%s'\n" "$TUBIFY_UPDATE_PUBLIC_KEY" >> "$native_build_root/PKGBUILD"
# CI supplies the newest stable release. A local build leaves it out, so it allows no password-free switch back.
if [[ "${TUBIFY_OLDEST_SWITCH_VERSION:-}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  printf "\n_oldest_switch_version='%s'\n" "$TUBIFY_OLDEST_SWITCH_VERSION" >> "$native_build_root/PKGBUILD"
fi
native_digest="$(sha256sum "$native_build_root/tubify-${native_version}.tar.gz" | cut -d' ' -f1)"
printf '\nsha256sums=(%s)\n' "$native_digest" >> "$native_build_root/PKGBUILD"
export PKGDEST="$native_output" SRCPKGDEST="$native_output"
cd "$native_build_root"
makepkg --cleanbuild "$@"
makepkg --allsource --force
