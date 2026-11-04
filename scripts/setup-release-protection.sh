#!/usr/bin/env bash
# Owner-only repository setup for release signing. Safe to run again. Never prints a secret.
#
#   scripts/setup-release-protection.sh [--sparkle-key-file FILE]    before merging the signing change
#   scripts/setup-release-protection.sh --finish                     after it has merged
#   scripts/setup-release-protection.sh --new-identity               only after a leak; see docs/releases
set -euo pipefail
repo="$(gh repo view --json nameWithOwner --jq .nameWithOwner)"
sparkle_key_file=""
finish=false
new_identity=false
while (($#)); do
  case "$1" in
    --sparkle-key-file) sparkle_key_file="$2"; shift 2 ;;
    --finish) finish=true; shift ;;
    --new-identity) new_identity=true; shift ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; exit 2 ;;
  esac
done

if "$finish"; then
  # Every workflow on the release branches is pinned by now.
  gh api -X PUT "repos/$repo/actions/permissions" -F enabled=true -f allowed_actions=all -F sha_pinning_required=true >/dev/null
  environment_secrets="$(gh secret list --env release --repo "$repo" --json name --jq '.[].name')"
  for name in TUBIFY_MACOS_SIGNING_P12 TUBIFY_MACOS_SIGNING_PASSWORD TUBIFY_SPARKLE_PRIVATE_KEY; do
    if grep -qx "$name" <<< "$environment_secrets"; then
      gh secret delete "$name" --repo "$repo" 2>/dev/null || true
      printf 'Only the release environment holds %s now.\n' "$name"
    else
      printf 'NOT MOVED: %s is not in the release environment yet, so its repository copy stays.\n' "$name" >&2
    fi
  done
  exit 0
fi

# Releases are automatic: merging to a release branch is the approval, and only those branches can use the keys.
gh api -X PUT "repos/$repo/environments/release" --input - >/dev/null <<JSON
{"wait_timer": 0, "prevent_self_review": false,
 "reviewers": [],
 "deployment_branch_policy": {"protected_branches": false, "custom_branch_policies": true}}
JSON
existing="$(gh api "repos/$repo/environments/release/deployment-branch-policies" --jq '.branch_policies[].name')"
for branch in main experimental; do
  grep -qx "$branch" <<< "$existing" || gh api -X POST "repos/$repo/environments/release/deployment-branch-policies" -f "name=$branch" -f type=branch >/dev/null
done

# Created once. Replacing a shipped identity resets everyone's keychain approvals, so that takes --new-identity.
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
if "$new_identity" || ! gh secret list --env release --repo "$repo" --json name --jq '.[].name' | grep -qx TUBIFY_MACOS_SIGNING_P12; then
  "$(dirname "${BASH_SOURCE[0]}")/make-macos-signing-identity.sh" "$work/id"
  # The certificate is public. Recording its fingerprint lets CI reject any other signer.
  fingerprint="$(openssl x509 -in "$work/id/tubify-signing.crt" -noout -fingerprint -sha1 | cut -d= -f2 | tr -d ':' | tr 'A-F' 'a-f')"
  gh variable set TUBIFY_MACOS_SIGNING_CERT --repo "$repo" --body "$fingerprint"
  base64 < "$work/id/tubify-signing.p12" | tr -d '\n' | gh secret set TUBIFY_MACOS_SIGNING_P12 --env release --repo "$repo"
  gh secret set TUBIFY_MACOS_SIGNING_PASSWORD --env release --repo "$repo" < "$work/id/tubify-signing.password"
fi
if [[ -n "$sparkle_key_file" ]]; then
  gh secret set TUBIFY_SPARKLE_PRIVATE_KEY --env release --repo "$repo" < "$sparkle_key_file"
  # The key file is the 32-byte seed then the 32-byte public key.
  gh variable set TUBIFY_UPDATE_PUBLIC_KEY --repo "$repo" --body "$(base64 -d < "$sparkle_key_file" | tail -c 32 | base64 | tr -d '\n')"
else
  printf 'The Sparkle key was not moved. Rerun with --sparkle-key-file FILE using your backup.\n' >&2
fi

ruleset() {
  local name="$1" id
  id="$(gh api "repos/$repo/rulesets" --jq ".[] | select(.name == \"$name\") | .id")"
  if [[ -n "$id" ]]; then gh api -X PUT "repos/$repo/rulesets/$id" --input - >/dev/null
  else gh api -X POST "repos/$repo/rulesets" --input - >/dev/null; fi
}
ruleset "Release branches" <<'JSON'
{"name": "Release branches", "target": "branch", "enforcement": "active", "bypass_actors": [],
 "conditions": {"ref_name": {"include": ["refs/heads/main", "refs/heads/experimental"], "exclude": []}},
 "rules": [{"type": "deletion"}, {"type": "non_fast_forward"},
  {"type": "pull_request", "parameters": {"required_approving_review_count": 0, "dismiss_stale_reviews_on_push": false,
    "require_code_owner_review": false, "require_last_push_approval": false, "required_review_thread_resolution": false}},
  {"type": "required_status_checks", "parameters": {"strict_required_status_checks_policy": false,
    "required_status_checks": [{"context": "Branch, title and base"}, {"context": "Tubify checks passed"}]}}]}
JSON
ruleset "Release tags" <<'JSON'
{"name": "Release tags", "target": "tag", "enforcement": "active", "bypass_actors": [],
 "conditions": {"ref_name": {"include": ["refs/tags/Tubify-*"], "exclude": []}},
 "rules": [{"type": "deletion"}, {"type": "non_fast_forward"}, {"type": "update"}]}
JSON

gh api -X PUT "repos/$repo/actions/permissions/workflow" -f default_workflow_permissions=read -F can_approve_pull_request_reviews=false >/dev/null
gh api -X PATCH "repos/$repo" --input - >/dev/null <<'JSON'
{"security_and_analysis": {"secret_scanning": {"status": "enabled"}, "secret_scanning_push_protection": {"status": "enabled"}}}
JSON
# Dependabot raises PRs for vulnerable locked dependencies; merging them is still the owner's call.
gh api -X PUT "repos/$repo/vulnerability-alerts" --silent
gh api -X PUT "repos/$repo/automated-security-fixes" --silent
printf 'Done. After the signing change merges, run: %s --finish\n' "$0"
