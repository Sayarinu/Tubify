#!/usr/bin/env bash
set -euo pipefail

native_repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
native_package="$1"
native_source_package="$2"
native_test_user=builder
native_test_root="$(mktemp -d /tmp/youtube-music-native-install.XXXXXX)"
native_upgrade_root="$(mktemp -d /tmp/youtube-music-native-upgrade.XXXXXX)"
trap 'rm -rf "$native_test_root" "$native_upgrade_root"' EXIT
chown "$native_test_user" "$native_test_root" "$native_upgrade_root"

pacman -U --noconfirm "$native_package"
pacman -Qk youtube-music-native
desktop-file-validate /usr/share/applications/youtube-music-native.desktop
test -r /usr/share/licenses/youtube-music-native/LICENSE
test -r /usr/share/licenses/youtube-music-native/Roboto-OFL.txt
runuser -u "$native_test_user" -- env -u PYTHONPATH youtube-music-native-check --help
runuser -u "$native_test_user" -- env -u PYTHONPATH QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software \
  youtube-music-native --fixture --smoke-test --data-dir "$native_test_root/window"
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
pacman -Qk youtube-music-native
runuser -u "$native_test_user" -- env -u PYTHONPATH python "$native_repo_root/native/tests/smoke_package.py" verify "$native_test_root/data"
printf '%s\n' 'Clean native install, launch and upgrade preservation passed.'
