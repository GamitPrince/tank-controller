#!/usr/bin/env bash
# One-time (and safe to re-run) GitHub configuration for tank-controller.
#
# Prerequisites:
#   - the repo exists and main and develop have been pushed (docs/github-setup.md steps 1-3)
#   - GitHub CLI installed and logged in as the repository OWNER: gh auth login
#
# Usage: scripts/setup-github.sh OWNER/REPO "PERSON1,PERSON2,PERSON3"
#   PERSON1..3 = the three people who must all review changes to interfaces/
#   e.g. scripts/setup-github.sh GamitPrince/tank-controller "GamitPrince,ArkinGamit,SHINE-18"
set -euo pipefail

REPO="${1:?usage: setup-github.sh OWNER/REPO \"PERSON1,PERSON2,PERSON3\"}"
REVIEWERS="$(printf '%s' "${2:?the three interface reviewers, comma-separated}" | tr -d ' ')"
HERE="$(cd "$(dirname "$0")/.." && pwd)"

# Exactly three different people, or the interfaces-review check cannot work.
distinct="$(printf '%s' "$REVIEWERS" | tr ',' '\n' | tr 'A-Z' 'a-z' | sed '/^$/d' | sort -u | wc -l | tr -d ' ')"
if [ "$distinct" != "3" ]; then
  echo "ERROR: give exactly three different usernames, comma-separated (got: $REVIEWERS)." >&2
  exit 1
fi

step() { printf '\n== %s\n' "$*"; }

step "Repository settings: squash-only, develop as default, auto-delete branches, secret scanning"
gh api -X PATCH "repos/$REPO" --input - >/dev/null <<'JSON'
{
  "default_branch": "develop",
  "has_issues": true,
  "has_projects": true,
  "has_wiki": false,
  "allow_squash_merge": true,
  "allow_merge_commit": false,
  "allow_rebase_merge": false,
  "allow_auto_merge": false,
  "allow_update_branch": true,
  "delete_branch_on_merge": true,
  "squash_merge_commit_title": "PR_TITLE",
  "squash_merge_commit_message": "BLANK",
  "security_and_analysis": {
    "secret_scanning": { "status": "enabled" },
    "secret_scanning_push_protection": { "status": "enabled" }
  }
}
JSON

step "Dependabot alerts and private vulnerability reporting"
gh api -X PUT "repos/$REPO/vulnerability-alerts" >/dev/null || echo "WARN: enable Dependabot alerts in Settings > Code security"
gh api -X PUT "repos/$REPO/private-vulnerability-reporting" >/dev/null || echo "WARN: enable private vulnerability reporting in Settings > Code security"

step "Actions: GitHub-owned actions only, read-only token, approval for outside contributors"
gh api -X PUT "repos/$REPO/actions/permissions" -F enabled=true -f allowed_actions=selected >/dev/null
gh api -X PUT "repos/$REPO/actions/permissions/selected-actions" -F github_owned_allowed=true -F verified_allowed=false >/dev/null
gh api -X PUT "repos/$REPO/actions/permissions/workflow" -f default_workflow_permissions=read -F can_approve_pull_request_reviews=false >/dev/null
gh api -X PUT "repos/$REPO/actions/permissions/fork-pr-contributor-approval" -f approval_policy=all_external_contributors >/dev/null \
  || echo "WARN: set Settings > Actions > General > 'Approval for running fork pull request workflows' to 'Require approval for all outside collaborators'"

step "Variable INTERFACE_REVIEWERS (the three developers who must review interfaces/)"
gh variable set INTERFACE_REVIEWERS --repo "$REPO" --body "$REVIEWERS"

step "Rulesets (create, or update if the name already exists)"
for file in "$HERE"/.github/rulesets/*.json; do
  name="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["name"])' "$file")"
  id="$(gh api "repos/$REPO/rulesets" --jq ".[] | select(.name==\"$name\") | .id")"
  if [ -n "$id" ]; then
    gh api -X PUT "repos/$REPO/rulesets/$id" --input "$file" >/dev/null && echo "updated $name"
  else
    gh api -X POST "repos/$REPO/rulesets" --input "$file" >/dev/null && echo "created $name"
  fi
done

step "Labels"
label() { gh label create "$1" --repo "$REPO" --color "$2" --description "$3" --force >/dev/null; }
label firmware  1d76db "Component: firmware"
label gateway   0e8a16 "Component: gateway"
label dashboard 5319e7 "Component: dashboard"
label hardware  fbca04 "Component: hardware"
label docs      0075ca "Component: docs"
label simulator c5def5 "Component: simulator"
label interfaces d4c5f9 "Component: interfaces (all three developers review)"
label story     ededed "Type: story card"
label bug       d73a4a "Type: bug"
label chore     cfd3d7 "Type: chore"
label must      b60205 "Priority: must"
label should    e99695 "Priority: should"
label could     f9d0c4 "Priority: could"
label safety    ff0000 "Touches a safety function: EE must approve"
label blocked   000000 "Blocked: say who or what you are waiting for"
label sev-critical b60205 "Bug severity: fix within 4 hours"
label sev-high     d93f0b "Bug severity: fix within 1 day"
label sev-medium   fbca04 "Bug severity: fix this sprint"
label sev-low      0e8a16 "Bug severity: fix next sprint"

step "Milestones (2-week sprints; the Phase 1 plan has four)"
for n in 1 2 3 4; do
  gh api -X POST "repos/$REPO/milestones" -f title="Sprint $n" >/dev/null 2>&1 || echo "Sprint $n already exists"
done

echo
echo "Done. Next: docs/github-setup.md step 7 (verify the rules with a practice PR)."
