#!/usr/bin/env bash
set -euo pipefail

native_repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$native_repo_root"
if [[ "${1:-}" != "--allow-dirty" && -n "$(git status --porcelain)" ]]; then
  printf '%s\n' 'Refusing to package a dirty checkout. Commit or stash changes first (or pass --allow-dirty for a local test build).' >&2
  exit 1
fi
if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  printf '%s\n' 'The native macOS build targets Apple Silicon; run it on an arm64 Mac.' >&2
  exit 1
fi
command -v brew >/dev/null || { printf '%s\n' 'Homebrew is required for libmpv, FFmpeg and Deno.' >&2; exit 1; }
command -v uv >/dev/null || { printf '%s\n' 'uv is required: brew install uv' >&2; exit 1; }
for formula in mpv ffmpeg deno; do
  brew list --versions "$formula" >/dev/null || brew install "$formula"
done
export HOMEBREW_PREFIX="$(brew --prefix)"
native_version="$(python3 -c 'import pathlib,re; print(re.search(r"^version = \"(.+)\"", pathlib.Path("native/pyproject.toml").read_text(), re.M)[1])')"
# Resolve /var -> /private/var so PyInstaller recognises Qt as bundled with PySide6.
native_build_root="$(cd "$(mktemp -d "${TMPDIR:-/tmp}/tubify-macos-build.XXXXXX")" && pwd -P)"
[[ -n "${TUBIFY_KEEP_BUILD:-}" ]] || trap 'rm -rf "$native_build_root"' EXIT
native_output="$native_repo_root/dist/native"
mkdir -p "$native_output"

uv venv --quiet --python 3.13 "$native_build_root/venv"
VIRTUAL_ENV="$native_build_root/venv" uv pip install --quiet "./native[macos-build]"
native_python="$native_build_root/venv/bin/python"

# The app icon is rendered from the same SVG the Linux package installs.
iconset="$native_build_root/Tubify.iconset"
mkdir -p "$iconset"
QT_QPA_PLATFORM=offscreen "$native_python" - "native/src/youtube_music_native/assets/music.svg" "$iconset" <<'PY'
import sys
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

app = QGuiApplication([])
renderer = QSvgRenderer(sys.argv[1])
for size in (16, 32, 128, 256, 512):
    for scale in (1, 2):
        image = QImage(size * scale, size * scale, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        renderer.render(painter)
        painter.end()
        image.save(f"{sys.argv[2]}/icon_{size}x{size}{'@2x' if scale == 2 else ''}.png")
PY
iconutil -c icns "$iconset" -o "$native_build_root/Tubify.icns"

TUBIFY_ICON="$native_build_root/Tubify.icns" "$native_python" -m PyInstaller --noconfirm --clean \
  --distpath "$native_build_root/dist" --workpath "$native_build_root/work" packaging/macos-native/Tubify.spec

app="$native_build_root/dist/Tubify.app"
[[ "$(lipo -archs "$app/Contents/MacOS/Tubify")" == "arm64" ]] || { printf '%s\n' 'Tubify executable is not arm64.' >&2; exit 1; }
# python-mpv looks up libmpv.dylib; PyInstaller only ships the versioned install name.
ln -sf libmpv.2.dylib "$app/Contents/Frameworks/libmpv.dylib"
# Pin and verify the framework distribution before bundling its executable helpers.
sparkle="$native_build_root/sparkle"
mkdir -p "$sparkle"
curl --fail --location --silent --show-error https://github.com/sparkle-project/Sparkle/releases/download/2.10.1/Sparkle-2.10.1.tar.xz -o "$sparkle/archive.tar.xz"
printf '%s  %s\n' 1a856d2a9edb8e628de88121d7be04cf0e2167f8641650b78fca00b14244cf27 "$sparkle/archive.tar.xz" | shasum -a 256 --check
tar -xf "$sparkle/archive.tar.xz" -C "$sparkle"
ditto "$sparkle/Sparkle.framework" "$app/Contents/Frameworks/Sparkle.framework"
cp "$sparkle/LICENSE" "$app/Contents/Resources/Sparkle-LICENSE.txt"
# Local builds are ad-hoc signed; Gatekeeper accepts them on the machine that built them.
codesign --force --deep --sign - "$app"
codesign --verify --deep --strict "$app"

rm -rf "$native_output/Tubify-macos-arm64.app" "$native_output/Tubify-${native_version}-macos-arm64.dmg"
ditto "$app" "$native_output/Tubify-macos-arm64.app"
staging="$native_build_root/dmg"
mkdir -p "$staging"
ditto "$app" "$staging/Tubify.app"
ln -s /Applications "$staging/Applications"
hdiutil create -quiet -volname "Tubify" -srcfolder "$staging" -ov -format UDZO "$native_output/Tubify-${native_version}-macos-arm64.dmg"
printf 'Built %s and %s\n' "$native_output/Tubify-macos-arm64.app" "$native_output/Tubify-${native_version}-macos-arm64.dmg"

if [[ -n "${TUBIFY_SPARKLE_PRIVATE_KEY:-}" ]]; then
  # Fail closed if a secret was rotated without updating the bundled trust anchor.
  swift scripts/check-sparkle-key.swift packaging/macos-native/sparkle-public-key.txt
  signature="$(printf '%s' "$TUBIFY_SPARKLE_PRIVATE_KEY" | tr -d '[:space:]' | "$sparkle/bin/sign_update" --ed-key-file - -p "$native_output/Tubify-${native_version}-macos-arm64.dmg")"
  "$native_python" scripts/native-appcast.py "$native_version" "$native_output/Tubify-${native_version}-macos-arm64.dmg" "$signature" "$native_output/appcast.xml"
fi
