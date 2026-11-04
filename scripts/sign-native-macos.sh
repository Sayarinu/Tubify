#!/usr/bin/env bash
# Sign dist/native/Tubify-macos-arm64.app and make its disk image; on release, also the signed appcast.
# Without TUBIFY_MACOS_SIGNING_P12 the app stays ad-hoc signed, for local builds.
# Runs next to the signing keys: it must not install anything unpinned or run the app.
set -euo pipefail
version="${1:?Usage: sign-native-macos.sh VERSION}"
cd "$(dirname "${BASH_SOURCE[0]}")/.."
output="$PWD/dist/native"
app="$output/Tubify-macos-arm64.app"
work="$(cd "$(mktemp -d "${TMPDIR:-/tmp}/tubify-macos-sign.XXXXXX")" && pwd -P)"
keychain="$work/signing.keychain-db"
trap 'security delete-keychain "$keychain" 2>/dev/null || true; rm -rf "$work"' EXIT

if [[ -n "${TUBIFY_MACOS_SIGNING_P12:-}" ]]; then
  password="$(uuidgen)"
  printf '%s' "$TUBIFY_MACOS_SIGNING_P12" | base64 -d > "$work/signing.p12"
  security create-keychain -p "$password" "$keychain"
  security set-keychain-settings "$keychain"
  security unlock-keychain -p "$password" "$keychain"
  security import "$work/signing.p12" -k "$keychain" -f pkcs12 -P "${TUBIFY_MACOS_SIGNING_PASSWORD:-}" -T /usr/bin/codesign >/dev/null
  rm -f "$work/signing.p12"
  security set-key-partition-list -S apple-tool:,apple: -s -k "$password" "$keychain" >/dev/null
  # codesign only finds identities in keychains on the search list.
  security list-keychains -d user -s "$keychain" $(security list-keychains -d user | tr -d '"')
  # Listed by hash: a self-signed certificate is not "valid" to find-identity -v, but it can sign.
  identity="$(security find-identity -p codesigning "$keychain" | awk '$2 ~ /^[0-9A-F]{40}$/ { print $2; exit }')"
  [[ -n "$identity" ]] || { printf '%s\n' 'The signing certificate has no usable identity.' >&2; exit 1; }
  codesign --force --deep --timestamp=none --keychain "$keychain" --sign "$identity" "$app"
  # A cdhash requirement would change with every build, and the keychain would forget its answers.
  codesign --display --requirements - "$app" 2>&1 | grep -q 'certificate' || { printf '%s\n' 'The app is not tied to its signing certificate.' >&2; exit 1; }
  codesign --verify --deep --strict "$app"
fi

image="$output/Tubify-${version}-macos-arm64.dmg"
rm -f "$image"
staging="$work/dmg"
mkdir -p "$staging"
ditto "$app" "$staging/Tubify.app"
ln -s /Applications "$staging/Applications"
hdiutil create -quiet -volname "Tubify" -srcfolder "$staging" -ov -format UDZO "$image"
printf 'Built %s\n' "$image"

if [[ -n "${TUBIFY_SPARKLE_PRIVATE_KEY:-}" ]]; then
  # Pinned and verified: this tool handles the update key.
  curl --fail --location --silent --show-error https://github.com/sparkle-project/Sparkle/releases/download/2.10.1/Sparkle-2.10.1.tar.xz -o "$work/sparkle.tar.xz"
  printf '%s  %s\n' 1a856d2a9edb8e628de88121d7be04cf0e2167f8641650b78fca00b14244cf27 "$work/sparkle.tar.xz" | shasum -a 256 --check
  mkdir "$work/sparkle"
  tar -xf "$work/sparkle.tar.xz" -C "$work/sparkle"
  # Fail closed if a secret was rotated without updating the bundled trust anchor.
  swift scripts/check-sparkle-key.swift packaging/macos-native/sparkle-public-key.txt
  signature="$(python3 -I native/sign_update.py "$work/sparkle/bin/sign_update" "$image")"
  python3 -I scripts/native-appcast.py "$version" "$image" "$signature" "$output/appcast.xml"
fi
