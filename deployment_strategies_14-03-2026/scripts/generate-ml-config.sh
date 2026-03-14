#!/usr/bin/env bash
# scripts/generate-ml-config.sh
#
# Called by pre-commit framework at pre-push stage on dev branch.
#
# What it does:
#   1. Fetches live canary-state ConfigMap from cluster (readonly kubectl get)
#   2. Reads current stable.*, canary.*, last_rollback.* from it
#   3. Merges with current HEAD sha (the new dev.*)
#   4. Writes the complete config/ml-model-versions.yaml in one shot
#   5. Stages it so it commits alongside the model code
#
# CI never writes this file — it only reads it to pick + render templates.
# Requires: kubectl configured with readonly access to kubeflow namespace
#           jq installed locally (for ConfigMap JSON parsing)

set -euo pipefail

CONFIG="config/ml-model-versions.yaml"
NS="kubeflow"
CM_NAME="canary-state"

# ── Guard: only on dev branch ─────────────────────────────────────────────────
CURRENT_BRANCH=$(git symbolic-ref --short HEAD 2>/dev/null || echo "")
if [[ "${CURRENT_BRANCH}" != "dev" ]]; then
  echo "[generate-ml-config] Not on dev branch (${CURRENT_BRANCH}), skipping."
  exit 0
fi

# ── Guard: only if model files are staged ────────────────────────────────────
CHANGED=$(git diff --cached --name-only 2>/dev/null || true)
if ! echo "${CHANGED}" | grep -qE '^(model/|Dockerfile\.model)'; then
  echo "[generate-ml-config] No model file changes staged, skipping."
  exit 0
fi

# ── Fetch live ConfigMap from cluster (readonly) ──────────────────────────────
echo "[generate-ml-config] Fetching ConfigMap ${CM_NAME} from ${NS}..."

FETCH_OK=true
if ! kubectl get configmap "${CM_NAME}" -n "${NS}" &>/dev/null; then
  echo "[generate-ml-config] WARNING: ConfigMap '${CM_NAME}' not found in namespace '${NS}'."
  echo "  This is expected on first ever deploy — stable/canary fields will be empty."
  STATE_YAML=""
  FETCH_OK=false
else
  # Extract the nested YAML from state.yaml key
  STATE_YAML=$(kubectl get configmap "${CM_NAME}" -n "${NS}" -o jsonpath='{.data.state\.yaml}')
fi

# ── Helper: extract a simple key: value from YAML using grep/sed ──────────────
# Works for flat values like "sha: abc123" or "weight: 20"
cm_val() {
  local key="$1"
  if [[ -z "${STATE_YAML}" ]]; then
    echo ""
  else
    echo "${STATE_YAML}" | grep -E "^\s*${key}:" | sed -E 's/^[^:]+:\s*//' | tr -d '"' | head -1
  fi
}

# ── Read stable block from ConfigMap ─────────────────────────────────────────
STABLE_BLOCK=$(echo "${STATE_YAML}" | sed -n '/^stable:/,/^[a-z]/p')
STABLE_SHA=$(echo "${STABLE_BLOCK}" | grep -E "^\s*sha:" | sed -E 's/^[^:]+:\s*//' | tr -d '"' | xargs || true)
STABLE_TAG=$(echo "${STABLE_BLOCK}" | grep -E "^\s*tag:" | sed -E 's/^[^:]+:\s*//' | tr -d '"' | xargs || true)
STABLE_PROMOTED_AT=$(echo "${STABLE_BLOCK}" | grep -E "^\s*promoted_at:" | sed -E 's/^[^:]+:\s*//' | tr -d '"' | xargs || true)
STABLE_PROMOTED_BY=$(echo "${STABLE_BLOCK}" | grep -E "^\s*promoted_by:" | sed -E 's/^[^:]+:\s*//' | tr -d '"' | xargs || true)

# ── Read canary block from ConfigMap ─────────────────────────────────────────
CANARY_BLOCK=$(echo "${STATE_YAML}" | sed -n '/^canary:/,/^[a-z]/p')
CANARY_SHA=$(echo "${CANARY_BLOCK}" | grep -E "^\s*sha:" | sed -E 's/^[^:]+:\s*//' | tr -d '"' | xargs || true)
CANARY_TAG=$(echo "${CANARY_BLOCK}" | grep -E "^\s*tag:" | sed -E 's/^[^:]+:\s*//' | tr -d '"' | xargs || true)
CANARY_WEIGHT=$(echo "${CANARY_BLOCK}" | grep -E "^\s*weight:" | sed -E 's/^[^:]+:\s*//' | tr -d '"' | xargs || true)

# ── Read last_stable block from ConfigMap ────────────────────────────────────
LAST_STABLE_BLOCK=$(echo "${STATE_YAML}" | sed -n '/^last_stable:/,/^[a-z]/p')
LAST_STABLE_SHA=$(echo "${LAST_STABLE_BLOCK}" | grep -E "^\s*sha:" | sed -E 's/^[^:]+:\s*//' | tr -d '"' | xargs || true)
LAST_STABLE_TAG=$(echo "${LAST_STABLE_BLOCK}" | grep -E "^\s*tag:" | sed -E 's/^[^:]+:\s*//' | tr -d '"' | xargs || true)
LAST_STABLE_PROMOTED_AT=$(echo "${LAST_STABLE_BLOCK}" | grep -E "^\s*promoted_at:" | sed -E 's/^[^:]+:\s*//' | tr -d '"' | xargs || true)
LAST_STABLE_PROMOTED_BY=$(echo "${LAST_STABLE_BLOCK}" | grep -E "^\s*promoted_by:" | sed -E 's/^[^:]+:\s*//' | tr -d '"' | xargs || true)

# ── New dev values from HEAD ──────────────────────────────────────────────────
SHORT_SHA=$(git rev-parse --short HEAD)
NOW=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
AUTHOR=$(git config user.name || echo "unknown")

echo "[generate-ml-config] Cluster state read:"
echo "  stable.sha      = '${STABLE_SHA}'"
echo "  last_stable.sha = '${LAST_STABLE_SHA}'"
echo "  canary.sha      = '${CANARY_SHA}'"
echo "  canary.weight   = '${CANARY_WEIGHT}'"
echo "[generate-ml-config] New dev.sha = ${SHORT_SHA}"

# ── Write complete config file in one shot ────────────────────────────────────
mkdir -p "$(dirname "${CONFIG}")"

cat > "${CONFIG}" <<EOF
# config/ml-model-versions.yaml
#
# SOURCE OF TRUTH for ML model deployment state.
# Generated by scripts/generate-ml-config.sh via pre-commit hook.
# Do not edit manually.
#
# stable.*        fetched from live ConfigMap '${CM_NAME}' (${NS})
# canary.*        fetched from live ConfigMap '${CM_NAME}' (${NS})
# dev.*           set from git HEAD at push time
# last_rollback.* fetched from live ConfigMap '${CM_NAME}' (${NS})
#
# Deploy canary : merge dev → staging  (CI applies canary-20.yaml.tpl)
# Rollback      : git revert this file's canary commit → merge to staging (CI applies rollback.yaml.tpl)
# Promote       : merge staging → prod (CI applies promote.yaml.tpl)
#
# Full history  : git log --follow -p -- config/ml-model-versions.yaml

stable:
  sha: "${STABLE_SHA}"
  tag: "${STABLE_TAG}"
  promoted_at: "${STABLE_PROMOTED_AT}"
  promoted_by: "${STABLE_PROMOTED_BY}"

last_stable:
  sha: "${LAST_STABLE_SHA}"
  tag: "${LAST_STABLE_TAG}"
  promoted_at: "${LAST_STABLE_PROMOTED_AT}"
  promoted_by: "${LAST_STABLE_PROMOTED_BY}"

canary:
  sha: "${CANARY_SHA}"
  tag: "${CANARY_TAG}"
  weight: ${CANARY_WEIGHT:-0}

dev:
  sha: "${SHORT_SHA}"
  tag: "sha-${SHORT_SHA}"
updated_at: "${NOW}"

EOF

# ── Stage the config file so it commits with the model code ──────────────────
git add "${CONFIG}"

if git diff --cached --quiet -- "${CONFIG}"; then
  echo "[generate-ml-config] Config file unchanged — nothing new to stage."
else
  echo "[generate-ml-config] Config file staged successfully."
  echo "  dev.sha    = ${SHORT_SHA}"
  echo "  stable.sha = ${STABLE_SHA:-'(empty — first deploy)'}"
  echo "  canary.sha = ${CANARY_SHA:-'(none running)'}"
fi