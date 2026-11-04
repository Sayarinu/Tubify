# Releases

`.github/workflows/native.yml` tests and packages Linux x86_64, Windows x64 and macOS arm64.

## Channels

| Branch | Publishes | Version | Tag | In-app channel |
|---|---|---|---|---|
| `experimental` | a GitHub prerelease on every push, never marked Latest | `X.Y.ZbN` | `Tubify-Experimental-X.Y.ZbN` | Experimental |
| `main` | the full release on every push | `X.Y.Z` | `Tubify-X.Y.Z` | Stable |

Version numbers start from the version in `native/pyproject.toml`, which is above every release published before the repository moved. `updates.release_tag` is the one rule CI, the appcast and the app share for tags.

Ticket PRs target `experimental` and are squash-merged; each merge ships an experimental build. When experimental is ready, open a PR from `experimental` into `main` and merge it with a **merge commit** (not squash or rebase) so both branches keep the same commits; that push publishes the stable release. Urgent fixes may target `main` directly; merge `main` back into `experimental` afterwards.

`scripts/open-prs.py` opens all of these. With one branch it opens one PR; with several it opens a GitHub stack, bottom first; with `--into stable` and no branch it opens the release PR. It waits for the PR checks and exits non-zero if any fail. The "PR policy" check runs on every PR. It enforces the branch name, title, base and GitHub noreply commit emails on this repository's branches, and only the base on PRs from forks. Stacked PRs run the same checks as any other PR. Tubify checks are path-filtered, so a PR that only changes docs runs only PR policy and Release size. No check is required by branch protection today; merging on green is a rule in `AGENTS.md`.

An experimental build's `X.Y.Z` is the stable version its changes are heading for: the newest stable tag bumped by the largest label among commits on `experimental` but not yet on `main`. `N` counts the builds of that version (0.7.0b1, 0.7.0b2, …). PEP 440, pacman's `vercmp` and Sparkle all sort `0.7.0 < 0.7.1b1 < 0.7.1b2 < 0.7.1`, so an experimental build updates to its stable release automatically. Apps and release titles show stable builds as "Tubify 0.7.1" and experimental builds as "Tubify Experimental 0.7.1b2". Experimental notes list the changes since the previous experimental build.

In **Settings → Updates**, the Update Channel chooses what Tubify offers. Stable only ever sees stable releases. Experimental offers the newest of either channel. Choosing Stable on an experimental build offers **Switch to Stable**, which installs the latest stable release even though it is older. On Linux the switch asks for a password, because the password-free helper only installs newer builds. On macOS, Sparkle cannot install an older build, so the switch opens the release download.

## Versions and publishing

**Every push to main or experimental is a release, versioned by the size of its changes.** A `version` job in the workflow finds the newest stable release tag on main and bumps it by the largest change merged since:

| Label on a merged PR | Bump | Example |
|---|---|---|
| none (default) | small change, patch | 0.1.1 → 0.1.2 |
| **Feature** | feature, minor | 0.1.7 → 0.2.0 |
| **Major Release** | major | 0.4.2 → 1.0.0 |

The "Release size" check on every PR shows the bump it will cause. It warns, without blocking, when a title that reads like a feature has no label. `scripts/native-release-version.py` stamps the chosen version into `native/pyproject.toml` and the Linux PKGBUILD in a local, unpushed CI commit, so every package is built as that version. Main and experimental runs are serialized so each bumps the version the previous one published. After all builds and tests pass, the pipeline publishes the release tag (`Tubify-<version>`, or `Tubify-Experimental-<version>` for experimental builds) with the Windows, macOS and Linux app packages, `SHA256SUMS` and the signed macOS `appcast.xml`. `scripts/native-release-notes.py` writes short notes from the titles of the PRs merged since the previous release: **New** for Feature and Major Release PRs, **Improvements and fixes** for the rest, then a download table. The in-app update popup shows only the changes. The pacman package is published as `Tubify-<version>-linux-x86_64.pkg.tar.zst`. It is signed with the same Ed25519 update key as the appcast, and the signature is published beside it as `Tubify-<version>-linux-x86_64.pkg.tar.zst.sig`. The Linux package's `apply-update` helper installs an update without a password only when this signature verifies and the version is newer than the installed one. Releases include only the desktop app builds; the source package is built only to test upgrades in CI. Published releases are never overwritten.

To jump to a specific version, raise it in `native/pyproject.toml` and the PKGBUILD together; a declared version higher than the computed one wins. Pushing a tag does not build a release; releases only come from pushes to `main` or `experimental`.

The macOS build pins Sparkle 2.10.1 and verifies its distribution SHA-256. `TUBIFY_SPARKLE_PRIVATE_KEY` is a GitHub Actions secret; only its public key is shared, as the `TUBIFY_UPDATE_PUBLIC_KEY` variable. Published builds (stable and experimental) fail without the private key. Keep a secure backup of this key before rotating or deleting it; existing clients trust the embedded public key. The secret stores a 64-byte seed/public-key pair. `native/sign_update.py` extracts the 32-byte seed expected by Sparkle's `sign_update --ed-key-file -`, passes it only on stdin and verifies the generated signature before returning it. The actual vendor tool is checked against RFC 8032 before packaging. Update signatures do not provide Apple notarization.

## Signing keys

Three secrets sign releases: `TUBIFY_SPARKLE_PRIVATE_KEY` (macOS updates, the Linux package and the Windows installer), and `TUBIFY_MACOS_SIGNING_P12` with `TUBIFY_MACOS_SIGNING_PASSWORD` (the macOS app). They live only in the protected `release` environment, which `scripts/setup-release-protection.sh` sets up.

- **Who can reach them:** only runs on `main` or `experimental`, which sign and publish automatically. A branch that edits a workflow can't enter the environment.
- **Who can merge:** changes reach those branches only through PRs, and only people with write access can merge, which today is just the owner. Contributors work from forks, so the owner's merge is their approval. Giving someone write access would let them merge, and so publish a signed release.
- **Where they're used:** only the `sign` job. It runs on a fresh machine, installs only a dependency pinned by hash, and never runs what the build jobs made. A separate `macos-verify` job with no keys runs the signed app. `native/tests/test_release_security.py` fails if this stops being true.
- **Other protection:** third-party actions are pinned to commits, release branches and tags can't be force-pushed or deleted, and GitHub secret scanning blocks pushes containing known secret formats.
- **What this can't stop:** the repository owner's GitHub account can change all of this, so protect it with two-factor authentication. Anything built from malicious code that reaches a release branch still gets signed, which is why changes arrive through PRs.

The macOS identity is self-signed. macOS ties keychain approvals to it, so "Always Allow" survives updates, but it doesn't satisfy Gatekeeper. Gatekeeper needs a paid Apple Developer ID and Windows SmartScreen needs an Authenticode signature, so both still warn on first open.

Tubify moved to a new repository with new signing keys in November 2026. Earlier releases were removed, and builds from before the move can't verify newer updates, so they need one manual install.

Two public values are GitHub variables, so they can change without a commit. They aren't secret, and builds read them when they run:

- `TUBIFY_UPDATE_PUBLIC_KEY`: the key that apps and the Linux update helper trust. A release fails if it doesn't match the Sparkle key.
- `TUBIFY_MACOS_SIGNING_CERT`: the macOS certificate's SHA-1 fingerprint. A release fails if the app was signed by anything else.

Unlike a file in the repository, these change without a PR or any history in git. Treat changing `TUBIFY_UPDATE_PUBLIC_KEY` like changing the key itself. For a local package build, run `export TUBIFY_UPDATE_PUBLIC_KEY="$(gh variable get TUBIFY_UPDATE_PUBLIC_KEY)"` first.

### If a key leaks

Replacing a key is not enough on its own: Macs that approved the old certificate keep trusting it.

**macOS identity**

1. Run `scripts/setup-release-protection.sh --new-identity`.
2. On each Mac, sign out of Tubify, which deletes the saved session, then sign in again and remove any saved Last.fm and Better Lyrics credentials before adding them again.
3. Revoke your Google sessions and change your Last.fm credentials.

**Sparkle key**

Treat this as urgent, because it signs updates: Windows runs what it signs, and Linux packages install as root without a password.

1. Generate a new key.
2. Replace the secret and the public key variable with `--sparkle-key-file`.
3. Publish a release. Installed apps still trust the old key, so they can't verify it: tell people to install it by hand.

Source launches and unsupported installations use release links. Automatic checks can be disabled; downloads require an explicit update action. Linux installation errors and cancelled authorization are reported on relaunch. Windows displays native installer errors. Sparkle provides native macOS update progress and recovery. All platforms preserve application data and restore playback paused.
