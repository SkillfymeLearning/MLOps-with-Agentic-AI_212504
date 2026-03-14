#!/usr/bin/env bash
# scripts/trigger-ci-curl.sh
#
# Trigger the ML Canary Pipeline workflow via GitHub REST API (curl)
#
# Usage:
#   ./scripts/trigger-ci-curl.sh staging              # Deploy to staging
#   ./scripts/trigger-ci-curl.sh rollback             # Force rollback (clear canary)
#   ./scripts/trigger-ci-curl.sh prod                 # Promote to production
#   ./scripts/trigger-ci-curl.sh staging --dry-run   # Dry run (no apply)
#
# Environment:
#   GITHUB_TOKEN  - Personal Access Token with 'repo' and 'workflow' scopes
#                   Create at: https://github.com/settings/tokens
#
# Prerequisites:
#   export GITHUB_TOKEN="ghp_xxxxxxxxxxxx"

set -euo pipefail

# ── Parse arguments ──────────────────────────────────────────────────────────
ACTION="${1:-staging}"
DRY_RUN="false"

for arg in "$@"; do
  case "${arg}" in
    --dry-run) DRY_RUN="true" ;;
    staging|rollback|prod) ACTION="${arg}" ;;
  esac
done

# ── Check for token ──────────────────────────────────────────────────────────
if [[ -z "${GITHUB_TOKEN:-}" ]]; then
  echo "ERROR: GITHUB_TOKEN environment variable not set"
  echo ""
  echo "Create a token at: https://github.com/settings/tokens"
  echo "Required scopes: repo, workflow"
  echo ""
  echo "Then run:"
  echo "  export GITHUB_TOKEN='ghp_xxxxxxxxxxxx'"
  echo "  $0 $*"
  exit 1
fi

# ── Get repo info from git remote ────────────────────────────────────────────
REMOTE_URL=$(git remote get-url origin 2>/dev/null || echo "")
if [[ -z "${REMOTE_URL}" ]]; then
  echo "ERROR: Could not determine repository from git remote"
  exit 1
fi

# Extract owner/repo from various URL formats
# https://github.com/owner/repo.git
# git@github.com:owner/repo.git
REPO=$(echo "${REMOTE_URL}" | sed -E 's#.*github.com[:/]([^/]+/[^/.]+)(\.git)?#\1#')
OWNER=$(echo "${REPO}" | cut -d'/' -f1)
REPO_NAME=$(echo "${REPO}" | cut -d'/' -f2)
BRANCH=$(git branch --show-current)

echo "═══════════════════════════════════════════════════════════════════════"
echo " Triggering ML Canary Pipeline (curl)"
echo "═══════════════════════════════════════════════════════════════════════"
echo ""
echo "  Repository : ${OWNER}/${REPO_NAME}"
echo "  Branch     : ${BRANCH}"
echo "  Action     : ${ACTION}"
echo "  Dry Run    : ${DRY_RUN}"
echo ""

# ── Trigger workflow via REST API ────────────────────────────────────────────
HTTP_CODE=$(curl -s -o /tmp/gh-response.json -w "%{http_code}" \
  -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer ${GITHUB_TOKEN}" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  "https://api.github.com/repos/${OWNER}/${REPO_NAME}/actions/workflows/ci.yaml/dispatches" \
  -d "{
    \"ref\": \"${BRANCH}\",
    \"inputs\": {
      \"action\": \"${ACTION}\",
      \"dry_run\": \"${DRY_RUN}\"
    }
  }")

if [[ "${HTTP_CODE}" == "204" ]]; then
  echo "✓ Workflow triggered successfully!"
  echo ""
  echo "  View runs:"
  echo "    curl -s -H \"Authorization: Bearer \${GITHUB_TOKEN}\" \\"
  echo "      \"https://api.github.com/repos/${OWNER}/${REPO_NAME}/actions/runs?event=workflow_dispatch\" \\"
  echo "      | jq '.workflow_runs[0] | {id, status, conclusion, html_url}'"
  echo ""
  echo "  Or visit: https://github.com/${OWNER}/${REPO_NAME}/actions/workflows/ci.yaml"
else
  echo "ERROR: Failed to trigger workflow (HTTP ${HTTP_CODE})"
  echo ""
  cat /tmp/gh-response.json 2>/dev/null | jq . 2>/dev/null || cat /tmp/gh-response.json
  exit 1
fi
