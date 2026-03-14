#!/usr/bin/env bash
# scripts/trigger-ci.sh
#
# Trigger the ML Canary Pipeline workflow manually via GitHub CLI
#
# Usage:
#   ./scripts/trigger-ci.sh staging              # Deploy to staging
#   ./scripts/trigger-ci.sh rollback             # Force rollback (clear canary)
#   ./scripts/trigger-ci.sh prod                 # Promote to production
#   ./scripts/trigger-ci.sh staging --dry-run   # Dry run (no apply)
#
# Prerequisites:
#   - GitHub CLI installed: brew install gh
#   - Authenticated: gh auth login

set -euo pipefail

ACTION="${1:-staging}"
DRY_RUN="false"

for arg in "$@"; do
  case "${arg}" in
    --dry-run) DRY_RUN="true" ;;
    staging|rollback|prod) ACTION="${arg}" ;;
  esac
done

# Get repo from git remote
REPO=$(gh repo view --json nameWithOwner -q '.nameWithOwner' 2>/dev/null || git remote get-url origin | sed -E 's#.*github.com[:/]([^/]+/[^/.]+)(\.git)?#\1#')

echo "═══════════════════════════════════════════════════════════════════════"
echo " Triggering ML Canary Pipeline"
echo "═══════════════════════════════════════════════════════════════════════"
echo ""
echo "  Repository : ${REPO}"
echo "  Action     : ${ACTION}"
echo "  Dry Run    : ${DRY_RUN}"
echo ""

# Trigger the workflow
gh workflow run ci.yaml \
  --repo "${REPO}" \
  --ref "$(git branch --show-current)" \
  -f action="${ACTION}" \
  -f dry_run="${DRY_RUN}"

echo "✓ Workflow triggered!"
echo ""
echo "  View runs: gh run list --workflow=ci.yaml --repo ${REPO}"
echo "  Or visit:  https://github.com/${REPO}/actions/workflows/ci.yaml"
