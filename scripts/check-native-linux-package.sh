#!/usr/bin/env bash
set -euo pipefail

native_repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
native_package="$1"
native_source_package="$2"
native_test_user=builder
native_test_root="$(mktemp -d /tmp/tubify-install.XXXXXX)"
native_upgrade_root="$(mktemp -d /tmp/tubify-upgrade.XXXXXX)"
native_legacy_root="$(mktemp -d /tmp/tubify-legacy.XXXXXX)"
trap 'rm -rf "$native_test_root" "$native_upgrade_root" "$native_legacy_root"' EXIT
chown "$native_test_user" "$native_test_root" "$native_upgrade_root" "$native_legacy_root"

# Before 1.0 the package was youtube-music-native. A stand-in owning files Tubify also ships
# checks that installing Tubify over it removes it in the same transaction.
cat > "$native_legacy_root/PKGBUILD" <<'PKG'
pkgname=youtube-music-native
pkgver=0.9.0
pkgrel=1
pkgdesc='Stand-in for a release from before the rename'
arch=('any')
license=('MIT')
package() {
  install -Dm755 /dev/null "$pkgdir/usr/bin/youtube-music-native"
  install -Dm644 /dev/null "$pkgdir/usr/share/icons/hicolor/scalable/apps/tubify.svg"
  install -Dm644 /dev/null "$pkgdir/usr/share/polkit-1/actions/studio.nouvellelune.tubify.update.policy"
}
PKG
chown "$native_test_user" "$native_legacy_root/PKGBUILD"
runuser -u "$native_test_user" -- bash -c 'cd "$1"; makepkg --nodeps --force --noconfirm' _ "$native_legacy_root"
native_legacy=("$native_legacy_root"/youtube-music-native-*.pkg.tar.zst)
pacman -U --noconfirm "${native_legacy[0]}"
# --noconfirm declines pacman's "Remove youtube-music-native?" conflict question; --ask=4
# (ALPM_QUESTION_CONFLICT_PKG, 1 << 2 in alpm.h) inverts that answer so the old package is removed.
pacman -U --noconfirm --ask=4 "$native_package"
if pacman -Q youtube-music-native >/dev/null 2>&1; then
  printf '%s\n' 'Installing Tubify left the old youtube-music-native package installed.' >&2
  exit 1
fi
test ! -e /usr/bin/youtube-music-native
pacman -Qk tubify
desktop-file-validate /usr/share/applications/tubify.desktop
test -r /usr/share/licenses/tubify/LICENSE
test -r /usr/lib/tubify/oldest-switch-version
test "$(stat -c '%U %a' /usr/lib/tubify/oldest-switch-version)" = 'root 644'
test -r /usr/share/licenses/tubify/Roboto-OFL.txt
test -r /usr/share/licenses/tubify/lucide-NOTICE.txt
runuser -u "$native_test_user" -- env -u PYTHONPATH tubify-check --help
runuser -u "$native_test_user" -- env -u PYTHONPATH QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software \
  tubify --fixture --smoke-test --data-dir "$native_test_root/window"
runuser -u "$native_test_user" -- env -u PYTHONPATH python "$native_repo_root/native/tests/smoke_package.py" prepare "$native_test_root/data"

# Rebuild a temporary package revision to exercise a real pacman upgrade transaction.
runuser -u "$native_test_user" -- bsdtar -xf "$native_source_package" -C "$native_upgrade_root"
native_recipes=("$native_upgrade_root"/*/PKGBUILD)
native_recipe="${native_recipes[0]}"
runuser -u "$native_test_user" -- python - "$native_recipe" <<'PY'
from pathlib import Path
import re
import sys
p = Path(sys.argv[1])
p.write_text(re.sub(r'^pkgrel=(\d+)$', lambda m: 'pkgrel=' + str(int(m[1]) + 1), p.read_text(), flags=re.M))
PY
runuser -u "$native_test_user" -- bash -c 'cd "$1"; makepkg --nodeps --nocheck --force --noconfirm' _ "$(dirname "$native_recipe")"
native_upgrades=("$(dirname "$native_recipe")"/*.pkg.tar.zst)
pacman -U --noconfirm "${native_upgrades[0]}"
pacman -Qk tubify
runuser -u "$native_test_user" -- env -u PYTHONPATH python "$native_repo_root/native/tests/smoke_package.py" verify "$native_test_root/data"
printf '%s\n' 'Replacing the old package, clean native install, launch and upgrade preservation passed.'
